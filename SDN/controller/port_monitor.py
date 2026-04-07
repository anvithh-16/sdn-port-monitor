"""
SDN Port Monitor Controller - Orange Problem
Monitors switch port status changes, detects port up/down events,
logs changes, generates alerts, and displays status.
"""

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, ether_types
from ryu.lib import hub

import logging
import datetime
import json
import os

# ── Logging Setup ─────────────────────────────────────────────────────────────
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(f"{LOG_DIR}/port_monitor.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("PortMonitor")


class PortMonitorController(app_manager.RyuApp):
    """
    Ryu SDN Controller that:
      1. Handles packet_in events (learning switch logic)
      2. Monitors port up/down events
      3. Logs all changes with timestamps
      4. Generates alerts on port failures
      5. Periodically polls port statistics
    """
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # MAC learning table: {dpid: {mac: port}}
        self.mac_to_port = {}

        # Port state tracking: {dpid: {port_no: state}}
        self.port_states = {}

        # Alert log (in-memory for demo)
        self.alerts = []

        # Statistics log: {dpid: {port_no: {tx_bytes, rx_bytes}}}
        self.port_stats = {}

        # Start background stats polling thread
        self.monitor_thread = hub.spawn(self._monitor_loop)

        logger.info("=" * 60)
        logger.info("  SDN Port Monitor Controller Started")
        logger.info("=" * 60)

    # ── Switch Handshake ───────────────────────────────────────────────────────

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Install table-miss flow entry on switch connect."""
        datapath = ev.msg.datapath
        ofproto  = datapath.ofproto
        parser   = datapath.ofproto_parser
        dpid     = datapath.id

        logger.info(f"[CONNECT] Switch connected: DPID={dpid:#x}")

        # Initialise state tracking for this switch
        self.mac_to_port.setdefault(dpid, {})
        self.port_states.setdefault(dpid, {})
        self.port_stats.setdefault(dpid, {})

        # Table-miss rule → send to controller
        match  = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,
                                          ofproto.OFPCML_NO_BUFFER)]
        self._add_flow(datapath, priority=0, match=match, actions=actions)

        # Request initial port descriptions
        req = parser.OFPPortDescStatsRequest(datapath, 0)
        datapath.send_msg(req)

    # ── MAC Learning / Packet-In ───────────────────────────────────────────────

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """Learn MAC addresses and install forwarding flow rules."""
        msg      = ev.msg
        datapath = msg.datapath
        ofproto  = datapath.ofproto
        parser   = datapath.ofproto_parser
        dpid     = datapath.id
        in_port  = msg.match["in_port"]

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return  # Ignore LLDP

        dst = eth.dst
        src = eth.src

        # Learn source MAC
        self.mac_to_port[dpid][src] = in_port
        logger.debug(f"[LEARN] DPID={dpid:#x} MAC={src} → port {in_port}")

        # Determine output port
        if dst in self.mac_to_port[dpid]:
            out_port = self.mac_to_port[dpid][dst]
        else:
            out_port = ofproto.OFPP_FLOOD

        actions = [parser.OFPActionOutput(out_port)]

        # Install flow rule (avoid flooding next time)
        if out_port != ofproto.OFPP_FLOOD:
            match = parser.OFPMatch(in_port=in_port, eth_dst=dst, eth_src=src)
            self._add_flow(datapath, priority=1, match=match, actions=actions,
                           idle_timeout=30, hard_timeout=120)

        # Send packet out
        data = msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None
        out  = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=msg.buffer_id,
            in_port=in_port,
            actions=actions,
            data=data
        )
        datapath.send_msg(out)

    # ── Port Status Events ─────────────────────────────────────────────────────

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status_handler(self, ev):
        """Detect and log port UP / DOWN events, generate alerts."""
        msg      = ev.msg
        datapath = msg.datapath
        ofproto  = datapath.ofproto
        dpid     = datapath.id
        port     = msg.desc
        port_no  = port.port_no
        reason   = msg.reason

        reason_map = {
            ofproto.OFPPR_ADD:    "ADDED",
            ofproto.OFPPR_DELETE: "DELETED",
            ofproto.OFPPR_MODIFY: "MODIFIED",
        }
        reason_str = reason_map.get(reason, "UNKNOWN")

        # Determine link state from port config/state flags
        link_down = bool(port.state & ofproto.OFPPS_LINK_DOWN)
        new_state = "DOWN" if link_down else "UP"

        prev_state = self.port_states.get(dpid, {}).get(port_no, "UNKNOWN")
        self.port_states.setdefault(dpid, {})[port_no] = new_state

        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        log_entry = {
            "timestamp": ts,
            "dpid":      f"{dpid:#x}",
            "port":      port_no,
            "port_name": port.name.decode(),
            "reason":    reason_str,
            "prev_state": prev_state,
            "new_state": new_state,
        }

        # ── Alert logic ───────────────────────────────────────────────────────
        if new_state == "DOWN" and prev_state == "UP":
            alert_msg = (f"⚠️  ALERT: Port {port_no} ({port.name.decode()}) "
                         f"on switch {dpid:#x} went DOWN at {ts}")
            logger.warning(alert_msg)
            self.alerts.append({"type": "PORT_DOWN", **log_entry})
            self._write_alert(log_entry)

        elif new_state == "UP" and prev_state == "DOWN":
            alert_msg = (f"✅  RECOVERY: Port {port_no} ({port.name.decode()}) "
                         f"on switch {dpid:#x} came UP at {ts}")
            logger.info(alert_msg)
            self.alerts.append({"type": "PORT_UP", **log_entry})
            self._write_alert(log_entry)

        else:
            logger.info(f"[PORT-{reason_str}] DPID={dpid:#x} "
                        f"port={port_no} ({port.name.decode()}) "
                        f"state={new_state}")

        # Log full entry to JSON log
        self._write_log(log_entry)

        # Invalidate MAC entries for the downed port
        if new_state == "DOWN":
            removed = [mac for mac, p in self.mac_to_port.get(dpid, {}).items()
                       if p == port_no]
            for mac in removed:
                del self.mac_to_port[dpid][mac]
            if removed:
                logger.info(f"[MAC-FLUSH] Removed {len(removed)} MAC(s) "
                            f"associated with port {port_no}")

    # ── Port Description Reply (initial snapshot) ─────────────────────────────

    @set_ev_cls(ofp_event.EventOFPPortDescStatsReply, MAIN_DISPATCHER)
    def port_desc_stats_reply_handler(self, ev):
        """Snapshot initial port states when switch connects."""
        datapath = ev.msg.datapath
        ofproto  = datapath.ofproto
        dpid     = datapath.id

        logger.info(f"[PORT-SNAPSHOT] DPID={dpid:#x}")
        for port in ev.msg.body:
            if port.port_no >= ofproto.OFPP_MAX:
                continue
            link_down = bool(port.state & ofproto.OFPPS_LINK_DOWN)
            state = "DOWN" if link_down else "UP"
            self.port_states.setdefault(dpid, {})[port.port_no] = state
            logger.info(f"  port {port.port_no:>3} ({port.name.decode():<12}) "
                        f"→ {state}")

    # ── Port Statistics ────────────────────────────────────────────────────────

    def _monitor_loop(self):
        """Background thread: request port stats every 10 seconds."""
        while True:
            for dp in list(self._get_datapaths()):
                self._request_port_stats(dp)
            hub.sleep(10)

    def _get_datapaths(self):
        """Yield all currently connected datapaths."""
        from ryu.base.app_manager import lookup_service_brick
        switches_app = lookup_service_brick("switches")
        if switches_app:
            for dp in switches_app.dps.values():
                yield dp

    def _request_port_stats(self, datapath):
        parser = datapath.ofproto_parser
        req    = parser.OFPPortStatsRequest(datapath, 0,
                                            datapath.ofproto.OFPP_ANY)
        datapath.send_msg(req)

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def port_stats_reply_handler(self, ev):
        """Receive and log port statistics."""
        datapath = ev.msg.datapath
        dpid     = datapath.id
        ts       = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        logger.info(f"[STATS] DPID={dpid:#x} @ {ts}")
        self.port_stats.setdefault(dpid, {})

        for stat in ev.msg.body:
            pno = stat.port_no
            if pno >= datapath.ofproto.OFPP_MAX:
                continue
            self.port_stats[dpid][pno] = {
                "rx_packets": stat.rx_packets,
                "tx_packets": stat.tx_packets,
                "rx_bytes":   stat.rx_bytes,
                "tx_bytes":   stat.tx_bytes,
                "rx_errors":  stat.rx_errors,
                "tx_errors":  stat.tx_errors,
                "rx_dropped": stat.rx_dropped,
                "tx_dropped": stat.tx_dropped,
            }
            logger.info(f"  port {pno:>3} | "
                        f"rx={stat.rx_packets} pkts / {stat.rx_bytes} B | "
                        f"tx={stat.tx_packets} pkts / {stat.tx_bytes} B | "
                        f"err rx={stat.rx_errors} tx={stat.tx_errors}")

        # Persist stats snapshot
        stats_file = f"{LOG_DIR}/stats_{dpid:#x}.json"
        with open(stats_file, "w") as f:
            json.dump({"timestamp": ts, "dpid": f"{dpid:#x}",
                       "ports": self.port_stats[dpid]}, f, indent=2)

    # ── Switch Disconnect ──────────────────────────────────────────────────────

    @set_ev_cls(ofp_event.EventOFPStateChange, DEAD_DISPATCHER)
    def switch_disconnect_handler(self, ev):
        dpid = ev.datapath.id
        logger.warning(f"[DISCONNECT] Switch {dpid:#x} disconnected")
        self._generate_alert(f"Switch {dpid:#x} disconnected", "SWITCH_DOWN")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _add_flow(self, datapath, priority, match, actions,
                  idle_timeout=0, hard_timeout=0):
        ofproto = datapath.ofproto
        parser  = datapath.ofproto_parser
        inst    = [parser.OFPInstructionActions(
                       ofproto.OFPIT_APPLY_ACTIONS, actions)]
        mod = parser.OFPFlowMod(
            datapath=datapath, priority=priority, match=match,
            instructions=inst,
            idle_timeout=idle_timeout, hard_timeout=hard_timeout
        )
        datapath.send_msg(mod)

    def _write_log(self, entry):
        """Append JSON entry to the event log."""
        with open(f"{LOG_DIR}/events.json", "a") as f:
            f.write(json.dumps(entry) + "\n")

    def _write_alert(self, entry):
        """Append JSON entry to the alerts log."""
        with open(f"{LOG_DIR}/alerts.json", "a") as f:
            f.write(json.dumps(entry) + "\n")

    def _generate_alert(self, msg, alert_type):
        ts = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        entry = {"timestamp": ts, "type": alert_type, "message": msg}
        self.alerts.append(entry)
        self._write_alert(entry)
        logger.warning(f"[ALERT] {msg}")

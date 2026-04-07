# SDN Port Monitor – Orange Problem
> **Course Assignment** | Mininet + Ryu OpenFlow Controller

## Problem Statement

This project implements an **SDN-based port status monitoring system** using Mininet and the Ryu OpenFlow controller. The controller monitors switch port status changes in real-time, detects port UP/DOWN events, logs all changes with timestamps, generates alerts on port failures, and displays live statistics.

**Key capabilities:**
- Controller–switch interaction via OpenFlow 1.3
- Packet-in handling with MAC learning (learning switch)
- Explicit flow rule installation (match + action)
- Port event detection and structured logging
- Alert generation on port failure/recovery
- Periodic port statistics polling (every 10 seconds)

---

## Architecture

```
┌─────────────┐        OpenFlow 1.3        ┌─────────┐   ┌─────────┐
│  Ryu        │◄──────────────────────────►│   s1    │───│   s2    │
│  Controller │   port_status / packet_in  └────┬────┘   └────┬────┘
│ port_monitor│                                h1,h2         h3,h4
└─────────────┘
       │
  logs/events.json
  logs/alerts.json
  logs/stats_*.json
```

**Topology:**
- 2 switches (s1, s2) connected via an inter-switch link
- 4 hosts: h1, h2 on s1 | h3, h4 on s2
- All links: TCLink with configurable bandwidth and delay

---

## Setup & Execution

### Prerequisites

```bash
# Ubuntu 20.04 / 22.04 with Mininet installed
sudo apt update
sudo apt install -y mininet python3-pip openvswitch-switch
pip3 install ryu          # or: pip3 install ryu --break-system-packages
```

### Installation

```bash
git clone https://github.com/<your-username>/sdn-port-monitor.git
cd sdn-port-monitor
chmod +x run.sh
```

### Running the Project

Open **3 terminals** in the project directory:

**Terminal 1 – Start Ryu Controller:**
```bash
./run.sh controller
# or directly:
ryu-manager --observe-links controller/port_monitor.py
```

**Terminal 2 – Start Mininet Topology:**
```bash
./run.sh topology
# or directly:
sudo python3 topology/topology.py
```

**Terminal 3 – Stream Logs:**
```bash
./run.sh logs
```

---

## Running Test Scenarios

From the **Mininet CLI** (Terminal 2):

```
mininet> py exec(open('tests/test_scenarios.py').read())

# Scenario 1: Normal connectivity
mininet> py run_scenario1(net)

# Scenario 2: Port failure and recovery
mininet> py run_scenario2(net)
```

Or run individual commands manually:
```
mininet> h1 ping h3 -c 4
mininet> h1 iperf -s &
mininet> h4 iperf -c 10.0.0.1 -t 5
mininet> s1 ovs-ofctl -O OpenFlow13 dump-flows s1
mininet> s1 ifconfig s1-eth3 down      ← trigger port DOWN alert
mininet> s1 ifconfig s1-eth3 up        ← trigger port UP / recovery
```

---

## Expected Output

### Scenario 1 – Normal Connectivity
```
[CONNECT]  Switch connected: DPID=0x1
[PORT-SNAPSHOT] DPID=0x1
  port   1 (s1-eth1     ) → UP
  port   2 (s1-eth2     ) → UP
  port   3 (s1-eth3     ) → UP
[LEARN]   DPID=0x1 MAC=00:00:00:00:00:01 → port 1
h1 → h3: 0% packet loss, rtt min/avg/max = 6/7/8 ms
```

### Scenario 2 – Port Failure
```
⚠️  ALERT: Port 3 (s1-eth3) on switch 0x1 went DOWN at 2024-11-15 10:32:01
[MAC-FLUSH] Removed 2 MAC(s) associated with port 3
...
✅  RECOVERY: Port 3 (s1-eth3) on switch 0x1 came UP at 2024-11-15 10:32:18
```

---

## Log Files

| File | Contents |
|------|----------|
| `logs/port_monitor.log` | Human-readable event stream |
| `logs/events.json` | All port events (newline-delimited JSON) |
| `logs/alerts.json` | Alerts only (DOWN / RECOVERY / SWITCH_DOWN) |
| `logs/stats_0x*.json` | Latest port statistics per switch |

---

## Flow Table Design

| Priority | Match | Action | Description |
|----------|-------|--------|-------------|
| 0 | (any) | → Controller | Table-miss: send unknown packets to controller |
| 1 | in_port + eth_src + eth_dst | → specific port | Learned forwarding rule |

Flow rules use `idle_timeout=30s` and `hard_timeout=120s` to ensure stale entries are removed automatically.

---

## Performance Observations

| Metric | Tool | Expected |
|--------|------|----------|
| Latency (same switch) | `ping` | ~1–2 ms |
| Latency (cross switch) | `ping` | ~6–10 ms |
| Throughput | `iperf` | ~90–950 Mbps (link limited) |
| Flow install delay | first ping RTT vs subsequent | visible RTT drop |
| Port-down detection | `EventOFPPortStatus` | < 1 second |

---

## Validation / Regression Tests

```bash
# From Mininet CLI:
mininet> pingall                         # Must be 0% loss
mininet> py run_scenario1(net)           # All flows installed, throughput OK
mininet> py run_scenario2(net)           # Alert logged, recovery confirmed
mininet> s1 ovs-ofctl -O OpenFlow13 dump-flows s1   # Flow table non-empty
mininet> cat logs/alerts.json            # Contains PORT_DOWN + PORT_UP entries
```

---

## Project Structure

```
sdn-port-monitor/
├── controller/
│   └── port_monitor.py      # Ryu controller (main logic)
├── topology/
│   └── topology.py          # Mininet topology definition
├── tests/
│   └── test_scenarios.py    # Test scenario functions
├── logs/                    # Auto-created at runtime
│   ├── port_monitor.log
│   ├── events.json
│   └── alerts.json
├── run.sh                   # Convenience launcher
└── README.md
```

---

## References

1. Ryu SDN Framework Documentation – https://ryu.readthedocs.io/
2. OpenFlow 1.3 Specification – https://opennetworking.org/wp-content/uploads/2014/10/openflow-spec-v1.3.0.pdf
3. Mininet Documentation – http://mininet.org/walkthrough/
4. Open vSwitch Documentation – https://docs.openvswitch.org/
5. Lantz, B. et al. "A Network in a Laptop: Rapid Prototyping for Software-Defined Networks." HotNets '10, 2010.

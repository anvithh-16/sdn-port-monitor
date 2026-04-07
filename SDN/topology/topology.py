#!/usr/bin/env python3
"""
SDN Port Monitor – Mininet Topology
Orange Problem Assignment

Topology:
         h1
          |
    s1 ---+--- s2
          |         |
         h2        h3
                    |
                   h4

Linear + star hybrid to demonstrate port monitoring across multiple switches.
"""

from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.topo import Topo
from mininet.log import setLogLevel, info
from mininet.cli import CLI
from mininet.link import TCLink
import time


class PortMonitorTopo(Topo):
    """
    Custom topology for port monitoring demo.

    Switches: s1, s2
    Hosts:    h1, h2 (connected to s1)
              h3, h4 (connected to s2)
    Inter-switch link: s1 ↔ s2
    """

    def build(self):
        # Create switches
        s1 = self.addSwitch("s1", protocols="OpenFlow13")
        s2 = self.addSwitch("s2", protocols="OpenFlow13")

        # Create hosts
        h1 = self.addHost("h1", ip="10.0.0.1/24", mac="00:00:00:00:00:01")
        h2 = self.addHost("h2", ip="10.0.0.2/24", mac="00:00:00:00:00:02")
        h3 = self.addHost("h3", ip="10.0.0.3/24", mac="00:00:00:00:00:03")
        h4 = self.addHost("h4", ip="10.0.0.4/24", mac="00:00:00:00:00:04")

        # Host ↔ switch links (100 Mbps, 1ms delay)
        self.addLink(h1, s1, bw=100, delay="1ms")
        self.addLink(h2, s1, bw=100, delay="1ms")
        self.addLink(h3, s2, bw=100, delay="1ms")
        self.addLink(h4, s2, bw=100, delay="1ms")

        # Inter-switch link (1 Gbps, 5ms delay)
        self.addLink(s1, s2, bw=1000, delay="5ms")


def run():
    setLogLevel("info")

    topo = PortMonitorTopo()
    net  = Mininet(
        topo=topo,
        controller=None,       # Use remote Ryu controller
        switch=OVSSwitch,
        link=TCLink,
        autoSetMacs=False,
    )

    # Connect to remote Ryu controller
    c0 = net.addController(
        "c0",
        controller=RemoteController,
        ip="127.0.0.1",
        port=6653
    )

    info("\n*** Starting network\n")
    net.start()

    # Give controller time to connect
    info("*** Waiting for controller handshake (3s)...\n")
    time.sleep(3)

    # Print topology summary
    info("\n" + "=" * 55 + "\n")
    info("  SDN Port Monitor – Topology Ready\n")
    info("=" * 55 + "\n")
    info("  Switches : s1, s2\n")
    info("  Hosts    : h1 (10.0.0.1)  h2 (10.0.0.2)\n")
    info("             h3 (10.0.0.3)  h4 (10.0.0.4)\n")
    info("  Links    : h1-s1, h2-s1, h3-s2, h4-s2, s1-s2\n")
    info("=" * 55 + "\n\n")
    info("  Run test scenarios:\n")
    info("    mininet> py run_scenario1(net)\n")
    info("    mininet> py run_scenario2(net)\n")
    info("  Or: mininet> source /path/to/test_scenarios.py\n\n")

    CLI(net)

    info("\n*** Stopping network\n")
    net.stop()


if __name__ == "__main__":
    run()

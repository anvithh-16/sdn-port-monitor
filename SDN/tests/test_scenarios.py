#!/usr/bin/env python3
"""
Test Scenarios for SDN Port Monitor – Orange Problem
=====================================================
Scenario 1 – Normal connectivity (all ports UP)
Scenario 2 – Port failure simulation (link DOWN)

Run from Mininet CLI:
    mininet> exec python3 tests/test_scenarios.py
Or import functions in CLI:
    mininet> py exec(open('tests/test_scenarios.py').read())
    mininet> py run_scenario1(net)
    mininet> py run_scenario2(net)
"""

import subprocess
import time
import sys
import os


# ── Helpers ───────────────────────────────────────────────────────────────────

def banner(title):
    print("\n" + "=" * 60)
    print(f"  {title}")
    print("=" * 60)


def run_ping(net, src_name, dst_name, count=4):
    src = net.get(src_name)
    dst = net.get(dst_name)
    banner(f"PING: {src_name} → {dst_name} ({count} packets)")
    result = src.cmd(f"ping -c {count} -W 2 {dst.IP()}")
    print(result)
    loss = "0%" if "0% packet loss" in result else "LOSS DETECTED"
    print(f"  ▶ Result: {loss}\n")
    return result


def run_iperf(net, server_name, client_name, duration=5):
    server = net.get(server_name)
    client = net.get(client_name)
    banner(f"IPERF: {client_name} → {server_name} ({duration}s)")
    server.cmd(f"iperf -s -t {duration + 2} &")
    time.sleep(1)
    result = client.cmd(f"iperf -c {server.IP()} -t {duration}")
    print(result)
    server.cmd("kill %iperf")
    return result


def show_flow_tables(net, switch_names):
    banner("FLOW TABLES")
    for sw_name in switch_names:
        print(f"\n  ── {sw_name} ──")
        sw = net.get(sw_name)
        result = sw.cmd("ovs-ofctl -O OpenFlow13 dump-flows " + sw_name)
        print(result)


def show_port_stats(net, switch_name):
    banner(f"PORT STATS: {switch_name}")
    sw = net.get(switch_name)
    result = sw.cmd(f"ovs-ofctl -O OpenFlow13 dump-ports {switch_name}")
    print(result)


# ── Scenario 1 – Normal Connectivity ─────────────────────────────────────────

def run_scenario1(net):
    """
    Scenario 1: All links UP – verify normal forwarding.
    Tests:
      • h1 ↔ h2 (same switch)
      • h1 ↔ h3 (cross switch)
      • iperf throughput h1 → h4
    """
    banner("SCENARIO 1 – NORMAL CONNECTIVITY (All Ports UP)")
    print("  Testing reachability and throughput with all links active.\n")

    time.sleep(2)  # Let controller install flows

    # Ping tests
    run_ping(net, "h1", "h2")          # Same switch
    run_ping(net, "h1", "h3")          # Cross switch
    run_ping(net, "h2", "h4")          # Cross switch

    # Throughput test
    run_iperf(net, "h4", "h1", duration=5)

    # Show state
    show_flow_tables(net, ["s1", "s2"])
    show_port_stats(net, "s1")
    show_port_stats(net, "s2")

    print("\n  ✅ Scenario 1 Complete – All hosts reachable, flows installed.\n")


# ── Scenario 2 – Port Failure / Recovery ─────────────────────────────────────

def run_scenario2(net):
    """
    Scenario 2: Simulate port DOWN event on s1-s2 link.
    Tests:
      • Connectivity before failure (should pass)
      • Port down event detected by controller
      • Connectivity during failure (cross-switch should fail)
      • Recovery after link restored
    """
    banner("SCENARIO 2 – PORT FAILURE & RECOVERY")
    print("  Simulates an inter-switch link going DOWN then UP.\n")

    # Step 1: Baseline connectivity
    print("  [STEP 1] Baseline – all links UP\n")
    run_ping(net, "h1", "h3", count=3)

    # Step 2: Bring down inter-switch link
    print("\n  [STEP 2] Taking down s1-s2 link (port failure simulation)...\n")
    s1 = net.get("s1")
    s2 = net.get("s2")

    # Disable the link on both ends (simulates physical failure)
    s1.cmd("ifconfig s1-eth3 down")   # s1's port facing s2
    s2.cmd("ifconfig s2-eth3 down")   # s2's port facing s1
    print("  ⚠️  Link s1-s2 brought DOWN. Controller should log ALERT.\n")
    time.sleep(3)

    # Step 3: Test connectivity during failure
    print("  [STEP 3] Testing connectivity DURING failure\n")
    run_ping(net, "h1", "h2", count=3)   # Same switch – should work
    run_ping(net, "h1", "h3", count=3)   # Cross switch – should FAIL

    # Step 4: Restore link
    print("\n  [STEP 4] Restoring s1-s2 link (recovery)...\n")
    s1.cmd("ifconfig s1-eth3 up")
    s2.cmd("ifconfig s2-eth3 up")
    print("  ✅  Link s1-s2 restored. Controller should log RECOVERY.\n")
    time.sleep(3)

    # Step 5: Verify recovery
    print("  [STEP 5] Verifying recovery\n")
    run_ping(net, "h1", "h3", count=4)

    # Show final state
    show_flow_tables(net, ["s1", "s2"])
    show_port_stats(net, "s1")

    print("\n  ✅ Scenario 2 Complete – Port failure detected and logged.\n")
    print("     Check logs/alerts.json and logs/events.json for entries.\n")


# ── Standalone runner (if executed directly) ──────────────────────────────────

if __name__ == "__main__":
    print("This script is designed to be sourced from the Mininet CLI.")
    print("Usage inside Mininet:")
    print("  mininet> py exec(open('tests/test_scenarios.py').read())")
    print("  mininet> py run_scenario1(net)")
    print("  mininet> py run_scenario2(net)")

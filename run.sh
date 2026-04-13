#!/bin/bash
# ============================================================
#  SDN Port Monitor – Launcher Script
#  Orange Problem Assignment
# ============================================================
# Usage:
#   ./run.sh controller   → Start Ryu controller (activate ryu-env first)
#   ./run.sh topology     → Start Mininet topology
#   ./run.sh logs         → Tail live logs
#   ./run.sh alerts       → Print alert log
#   ./run.sh clean        → Clean OVS state and logs
# ============================================================

ACTION=${1:-help}
CTRL_FILE="controller/port_monitor.py"
TOPO_FILE="topology/topology.py"
LOG_DIR="logs"

RED='\033[0;31m'; GRN='\033[0;32m'; YLW='\033[1;33m'
BLU='\033[0;34m'; NC='\033[0m'

header() {
  echo -e "\n${BLU}══════════════════════════════════════${NC}"
  echo -e "${BLU}  $1${NC}"
  echo -e "${BLU}══════════════════════════════════════${NC}\n"
}

case "$ACTION" in

  controller)
    header "Starting Ryu Controller"
    mkdir -p "$LOG_DIR"
    echo -e "${YLW}Make sure conda ryu-env is active before running this!${NC}"
    echo -e "${GRN}Launching: ryu-manager $CTRL_FILE${NC}"
    echo -e "${YLW}Press Ctrl+C to stop.${NC}\n"
    ryu-manager --observe-links "$CTRL_FILE"
    ;;

  topology)
    header "Starting Mininet Topology"
    echo -e "${YLW}Make sure the Ryu controller is running in another terminal first!${NC}\n"
    sleep 1
    sudo python3 "$TOPO_FILE"
    ;;

  logs)
    header "Tailing Port Monitor Logs"
    mkdir -p "$LOG_DIR"
    touch "$LOG_DIR/port_monitor.log"
    echo -e "${GRN}Streaming logs/port_monitor.log  (Ctrl+C to stop)${NC}\n"
    tail -f "$LOG_DIR/port_monitor.log"
    ;;

  alerts)
    header "Recent Alerts"
    if [ -f "$LOG_DIR/alerts.json" ]; then
      echo -e "${RED}Alert log:${NC}\n"
      cat "$LOG_DIR/alerts.json" | python3 -m json.tool 2>/dev/null || cat "$LOG_DIR/alerts.json"
    else
      echo "No alerts yet. Run the topology and scenarios first."
    fi
    ;;

  clean)
    header "Cleaning Up"
    echo "Stopping Mininet..."
    sudo mn --clean 2>/dev/null
    echo "Removing logs..."
    rm -rf "$LOG_DIR"
    echo -e "${GRN}Done.${NC}"
    ;;

  help|*)
    echo ""
    echo -e "${BLU}  SDN Port Monitor – Orange Problem${NC}"
    echo ""
    echo "  Usage: ./run.sh <command>"
    echo ""
    echo "  Commands:"
    echo -e "    ${GRN}controller${NC}   Start the Ryu SDN controller"
    echo -e "    ${GRN}topology${NC}     Start the Mininet topology"
    echo -e "    ${GRN}logs${NC}         Stream live controller logs"
    echo -e "    ${GRN}alerts${NC}       Print all generated alerts"
    echo -e "    ${GRN}clean${NC}        Clean Mininet state and logs"
    echo ""
    echo "  Quickstart:"
    echo "    Terminal 1: conda activate ryu-env && ./run.sh controller"
    echo "    Terminal 2: ./run.sh topology"
    echo "    Terminal 3: ./run.sh logs"
    echo ""
    ;;
esac

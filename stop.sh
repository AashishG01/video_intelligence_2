#!/bin/bash
# ============================================================
# C.O.R.E. Video Intelligence - Clean Shutdown Script
# Usage: bash stop.sh
# ============================================================

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo ""
echo -e "${RED}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${RED}║        C.O.R.E. SYSTEM SHUTDOWN SEQUENCE         ║${NC}"
echo -e "${RED}╚══════════════════════════════════════════════════╝${NC}"
echo ""

# Stop PM2 services
echo -e "${YELLOW}[1/2]${NC} Stopping application services..."
pm2 stop all 2>/dev/null || true
pm2 delete all 2>/dev/null || true
echo -e "${GREEN}✅ Application services stopped.${NC}"

# Stop Docker
echo ""
echo -e "${YELLOW}[2/2]${NC} Stopping Docker infrastructure..."
cd "$PROJECT_DIR"
docker compose down
echo -e "${GREEN}✅ Docker containers stopped.${NC}"

echo ""
echo -e "${CYAN}System is fully offline. All services terminated.${NC}"
echo ""

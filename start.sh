#!/bin/bash
# ============================================================
# C.O.R.E. Video Intelligence - One-Click Startup Script
# Usage: bash start.sh
# ============================================================

set -e

# Color codes for pretty output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# 🧠 CRITICAL: All paths are double-quoted to handle spaces in directory names
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PYTHON="$PROJECT_DIR/venv/bin/python"
VENV_PIP="$PROJECT_DIR/venv/bin/pip"

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║     C.O.R.E. VIDEO INTELLIGENCE SYSTEM v3.1     ║${NC}"
echo -e "${CYAN}║           ONE-CLICK STARTUP SEQUENCE             ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════╝${NC}"
echo ""

# ──────────────────────────────────────────────────
# PHASE 1: Verify Python Virtual Environment
# ──────────────────────────────────────────────────
echo -e "${YELLOW}[PHASE 1/5]${NC} Checking Python virtual environment..."
if [ ! -f "$VENV_PYTHON" ]; then
    echo -e "${RED}❌ ERROR: Virtual environment not found at $VENV_PYTHON${NC}"
    echo -e "${RED}   Please create it first: python -m venv venv && source venv/bin/activate && pip install -r requirements.txt${NC}"
    exit 1
fi
echo -e "${GREEN}✅ Virtual environment found.${NC}"
echo -e "${GREEN}   Using Python: $VENV_PYTHON${NC}"

# ──────────────────────────────────────────────────
# PHASE 2: Start Docker Infrastructure
# ──────────────────────────────────────────────────
echo ""
echo -e "${YELLOW}[PHASE 2/5]${NC} Starting Docker infrastructure (PostgreSQL, Redis, Milvus, MediaMTX)..."
cd "$PROJECT_DIR"
docker compose up -d
echo -e "${GREEN}✅ Docker containers started.${NC}"

# Wait for services to be healthy
echo -e "${YELLOW}   ⏳ Waiting 10 seconds for databases to initialize...${NC}"
sleep 10

# ──────────────────────────────────────────────────
# PHASE 3: Initialize Database (Safe - uses IF NOT EXISTS)
# ──────────────────────────────────────────────────
echo ""
echo -e "${YELLOW}[PHASE 3/5]${NC} Running database initialization (safe - idempotent)..."
cd "$PROJECT_DIR/database_init"
"$VENV_PYTHON" init_db.py
echo -e "${GREEN}✅ Database infrastructure verified.${NC}"

# ──────────────────────────────────────────────────
# PHASE 4: Start all Application Services via PM2
# ──────────────────────────────────────────────────
echo ""
echo -e "${YELLOW}[PHASE 4/5]${NC} Starting application services via PM2..."
cd "$PROJECT_DIR"

# Kill any previous PM2 processes to avoid duplicates
pm2 delete all 2>/dev/null || true

# Start the ecosystem
pm2 start ecosystem.config.js
echo -e "${GREEN}✅ All services launched.${NC}"

# ──────────────────────────────────────────────────
# PHASE 5: Status Report
# ──────────────────────────────────────────────────
echo ""
echo -e "${YELLOW}[PHASE 5/5]${NC} Generating system status report..."
sleep 3
pm2 status

echo ""
echo -e "${CYAN}╔══════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║           🚀 SYSTEM IS NOW ONLINE 🚀            ║${NC}"
echo -e "${CYAN}╠══════════════════════════════════════════════════╣${NC}"
echo -e "${CYAN}║  Frontend:   http://localhost:5173               ║${NC}"
echo -e "${CYAN}║  Backend:    http://localhost:8000/docs           ║${NC}"
echo -e "${CYAN}║  MediaMTX:   http://localhost:9997                ║${NC}"
echo -e "${CYAN}╚══════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${GREEN}To monitor logs:  pm2 logs${NC}"
echo -e "${GREEN}To stop system:   pm2 stop all${NC}"
echo -e "${RED}To full shutdown: pm2 stop all && docker compose down${NC}"

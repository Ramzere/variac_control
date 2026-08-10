#!/bin/bash
# ── Variac Control — Launcher ────────────────────────────────────────────────

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG="$SCRIPT_DIR/config.ini"

# ── Couleurs terminal ────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

clear

echo ""
echo -e "${CYAN}${BOLD}"
echo "  ╔══════════════════════════════════════════╗"
echo "  ║                                          ║"
echo "  ║      ⚡  VARIAC CONTROL SYSTEM           ║"
echo "  ║                                          ║"
echo "  ╚══════════════════════════════════════════╝"
echo -e "${RESET}"
echo ""

# ── Vérification config.ini ──────────────────────────────────────────────────
echo -e "${BOLD}[ 1/4 ]${RESET} Checking configuration..."

if [ ! -f "$CONFIG" ]; then
  echo -e "  ${RED}✗ config.ini not found in :${RESET}"
  echo -e "    $SCRIPT_DIR"
  echo ""
  read -p "Press Enter to close..."
  exit 1
fi

APP_DIR=$(grep "app_dir" "$CONFIG" | sed 's/.*= *//' | tr -d '\r')
PORT=$(grep "^port" "$CONFIG" | sed 's/.*= *//' | tr -d '\r')
PORT=${PORT:-5001}

echo -e "  ${GREEN}✓ config.ini found${RESET}"
echo ""

# ── Vérification dossier ─────────────────────────────────────────────────────
echo -e "${BOLD}[ 2/4 ]${RESET} Checking project folder..."

if [ ! -d "$APP_DIR" ]; then
  echo -e "  ${RED}✗ Folder not found :${RESET}"
  echo -e "    $APP_DIR"
  echo -e "  ${YELLOW}→ Check app_dir in config.ini${RESET}"
  echo ""
  read -p "Press Enter to close..."
  exit 1
fi

if [ ! -f "$APP_DIR/app.py" ]; then
  echo -e "  ${RED}✗ app.py not found in :${RESET}"
  echo -e "    $APP_DIR"
  echo ""
  read -p "Press Enter to close..."
  exit 1
fi

echo -e "  ${GREEN}✓ Project folder OK${RESET}"
echo -e "    ${CYAN}$APP_DIR${RESET}"
echo ""

# ── Vérification Python ──────────────────────────────────────────────────────
echo -e "${BOLD}[ 3/4 ]${RESET} Checking Python..."

PYTHON=$(which python3)
if [ -z "$PYTHON" ]; then
  echo -e "  ${RED}✗ python3 not found${RESET}"
  echo -e "  ${YELLOW}→ Install Python 3 from python.org${RESET}"
  echo ""
  read -p "Press Enter to close..."
  exit 1
fi

PY_VERSION=$($PYTHON --version 2>&1)
echo -e "  ${GREEN}✓ $PY_VERSION${RESET}"
echo ""

# ── Vérification dépendances ─────────────────────────────────────────────────
echo -e "${BOLD}[ 4/4 ]${RESET} Checking dependencies..."

MISSING=""
for pkg in flask flask_socketio serial; do
  $PYTHON -c "import $pkg" 2>/dev/null || MISSING="$MISSING $pkg"
done

if [ -n "$MISSING" ]; then
  echo -e "  ${YELLOW}⚠ Missing packages :$MISSING${RESET}"
  echo -e "  ${BLUE}→ Installing...${RESET}"
  pip3 install flask flask-socketio pyserial 2>&1 | grep -E "Successfully|already"
  echo ""
else
  echo -e "  ${GREEN}✓ All dependencies OK${RESET}"
  echo ""
fi

# ── Démarrage ────────────────────────────────────────────────────────────────
echo -e "  ${BOLD}────────────────────────────────────────────${RESET}"
echo -e "  ${GREEN}${BOLD}🚀 Starting server on port $PORT...${RESET}"
echo -e "  ${CYAN}🌍 http://localhost:$PORT${RESET}"
echo -e "  ${BOLD}────────────────────────────────────────────${RESET}"
echo ""
echo -e "  ${YELLOW}Press CTRL+C to stop the server${RESET}"
echo ""

cd "$APP_DIR"

# Crée le dossier logs si absent
mkdir -p "$APP_DIR/logs"

# Ouvre le navigateur après 4 secondes
(sleep 4 && open "http://localhost:$PORT") &

# Lance le serveur
$PYTHON app.py

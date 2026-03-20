#!/bin/bash
# ============================================================================
# Cloudflare Tunnel Setup for Autonomy Demo
#
# Run this on MSI-Stealth.local (the machine running the Docker stack).
# Creates a Cloudflare Tunnel so demo.azirella.com → localhost:8088
#
# Prerequisites:
#   - Docker stack running on localhost:8088
#   - Cloudflare account with azirella.com zone
#
# Usage:
#   chmod +x scripts/setup_cloudflare_tunnel.sh
#   ./scripts/setup_cloudflare_tunnel.sh
# ============================================================================

set -e

TUNNEL_NAME="autonomy-demo"
HOSTNAME="demo.azirella.com"
LOCAL_PORT="8088"

echo "============================================"
echo "  Cloudflare Tunnel Setup for Autonomy Demo"
echo "============================================"
echo ""

# Step 1: Install cloudflared
if ! command -v cloudflared &> /dev/null; then
    echo "[1/6] Installing cloudflared..."
    curl -sL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /tmp/cloudflared
    chmod +x /tmp/cloudflared
    sudo mv /tmp/cloudflared /usr/local/bin/cloudflared
    echo "  ✓ cloudflared installed"
else
    echo "[1/6] cloudflared already installed: $(cloudflared --version)"
fi

# Step 2: Authenticate
echo ""
echo "[2/6] Authenticating with Cloudflare..."
echo "  This will open a browser. Select the azirella.com zone."
echo "  Press Enter when ready..."
read -r
cloudflared tunnel login
echo "  ✓ Authenticated"

# Step 3: Create tunnel
echo ""
echo "[3/6] Creating tunnel '${TUNNEL_NAME}'..."
# Check if tunnel already exists
if cloudflared tunnel list | grep -q "${TUNNEL_NAME}"; then
    echo "  Tunnel '${TUNNEL_NAME}' already exists"
    TUNNEL_ID=$(cloudflared tunnel list | grep "${TUNNEL_NAME}" | awk '{print $1}')
else
    cloudflared tunnel create "${TUNNEL_NAME}"
    TUNNEL_ID=$(cloudflared tunnel list | grep "${TUNNEL_NAME}" | awk '{print $1}')
fi
echo "  ✓ Tunnel ID: ${TUNNEL_ID}"

# Step 4: Route DNS
echo ""
echo "[4/6] Routing ${HOSTNAME} → tunnel..."
cloudflared tunnel route dns "${TUNNEL_NAME}" "${HOSTNAME}" 2>/dev/null || echo "  (DNS route may already exist)"
echo "  ✓ ${HOSTNAME} → ${TUNNEL_NAME}"

# Step 5: Create config
echo ""
echo "[5/6] Creating tunnel config..."
CREDS_FILE="${HOME}/.cloudflared/${TUNNEL_ID}.json"
CONFIG_FILE="${HOME}/.cloudflared/config.yml"

cat > "${CONFIG_FILE}" << EOF
# Cloudflare Tunnel config for Autonomy Demo
# Created: $(date)
tunnel: ${TUNNEL_ID}
credentials-file: ${CREDS_FILE}

ingress:
  - hostname: ${HOSTNAME}
    service: http://localhost:${LOCAL_PORT}
    originRequest:
      noTLSVerify: true
  - service: http_status:404
EOF

echo "  ✓ Config written to ${CONFIG_FILE}"
echo ""
cat "${CONFIG_FILE}"

# Step 6: Test or install as service
echo ""
echo "[6/6] Starting tunnel..."
echo ""
echo "  Choose:"
echo "    1) Test run (foreground, Ctrl+C to stop)"
echo "    2) Install as systemd service (persistent, survives reboot)"
echo ""
read -rp "  Enter 1 or 2: " choice

case "$choice" in
    1)
        echo ""
        echo "  Starting tunnel in foreground..."
        echo "  Visit https://${HOSTNAME} to test"
        echo "  Press Ctrl+C to stop"
        echo ""
        cloudflared tunnel run "${TUNNEL_NAME}"
        ;;
    2)
        echo ""
        echo "  Installing as systemd service..."
        sudo cloudflared service install
        sudo systemctl enable cloudflared
        sudo systemctl start cloudflared
        echo "  ✓ Service installed and started"
        echo ""
        echo "  Check status: sudo systemctl status cloudflared"
        echo "  View logs:    sudo journalctl -u cloudflared -f"
        ;;
    *)
        echo "  Skipping. Run manually with:"
        echo "    cloudflared tunnel run ${TUNNEL_NAME}"
        ;;
esac

echo ""
echo "============================================"
echo "  Setup complete!"
echo ""
echo "  Demo URL: https://${HOSTNAME}"
echo "  Auto-login: https://${HOSTNAME}/auto-login?token=<demo_token>"
echo ""
echo "  To generate a demo token:"
echo "    curl -s https://${HOSTNAME}/api/v1/auth/demo-token | jq .url"
echo ""
echo "  For the website button, use:"
echo "    <a href=\"https://${HOSTNAME}/api/v1/auth/demo-token-redirect\">"
echo "      Try the Live Demo"
echo "    </a>"
echo "============================================"

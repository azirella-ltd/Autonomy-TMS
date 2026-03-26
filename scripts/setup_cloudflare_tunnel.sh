#!/bin/bash
# ============================================================================
# Cloudflare Tunnel Setup for Autonomy Platform
#
# Creates a Cloudflare Tunnel with wildcard subdomain routing:
#   *.azirella.com  → localhost:8088  (all tenant subdomains)
#   azirella.com    → localhost:8088  (bare domain)
#
# The tunnel handles SSL termination (Cloudflare edge) and passes the
# original Host header through to nginx, which forwards to frontend/backend.
# The backend's subdomain middleware validates tenant_slug from the JWT.
#
# Prerequisites:
#   - Docker stack running on localhost:8088
#   - Cloudflare account with azirella.com zone
#   - Cloudflare plan that supports wildcard DNS (free plan works)
#
# Usage:
#   chmod +x scripts/setup_cloudflare_tunnel.sh
#   ./scripts/setup_cloudflare_tunnel.sh
#
# After setup, update .env:
#   APP_DOMAIN=azirella.com
#   APP_SCHEME=https
#   APP_PORT=
#   SUBDOMAIN_ROUTING_ENABLED=true
#   COOKIE_DOMAIN=.azirella.com
#   CSRF_COOKIE_DOMAIN=.azirella.com
#   COOKIE_SECURE=true
# ============================================================================

set -e

TUNNEL_NAME="${1:-autonomy}"
DOMAIN="azirella.com"
LOCAL_PORT="8088"

echo "============================================"
echo "  Cloudflare Tunnel — Autonomy Platform"
echo "============================================"
echo ""
echo "  Tunnel:    ${TUNNEL_NAME}"
echo "  Domain:    ${DOMAIN}"
echo "  Wildcard:  *.${DOMAIN}"
echo "  Local:     http://localhost:${LOCAL_PORT}"
echo ""

# --- Step 1: Install cloudflared ---
if ! command -v cloudflared &> /dev/null; then
    echo "[1/6] Installing cloudflared..."
    curl -sL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 -o /tmp/cloudflared
    chmod +x /tmp/cloudflared
    sudo mv /tmp/cloudflared /usr/local/bin/cloudflared
    echo "  OK: cloudflared installed"
else
    echo "[1/6] cloudflared already installed: $(cloudflared --version 2>&1 | head -1)"
fi

# --- Step 2: Authenticate ---
echo ""
echo "[2/6] Authenticating with Cloudflare..."
if [[ -f "${HOME}/.cloudflared/cert.pem" ]]; then
    echo "  Already authenticated (cert.pem exists)"
else
    echo "  This will open a browser. Select the ${DOMAIN} zone."
    echo "  Press Enter when ready..."
    read -r
    cloudflared tunnel login
    echo "  OK: Authenticated"
fi

# --- Step 3: Create tunnel ---
echo ""
echo "[3/6] Creating tunnel '${TUNNEL_NAME}'..."
if cloudflared tunnel list 2>/dev/null | grep -q "${TUNNEL_NAME}"; then
    echo "  Tunnel '${TUNNEL_NAME}' already exists"
    TUNNEL_ID=$(cloudflared tunnel list 2>/dev/null | grep "${TUNNEL_NAME}" | awk '{print $1}')
else
    cloudflared tunnel create "${TUNNEL_NAME}"
    TUNNEL_ID=$(cloudflared tunnel list 2>/dev/null | grep "${TUNNEL_NAME}" | awk '{print $1}')
fi
echo "  OK: Tunnel ID: ${TUNNEL_ID}"

# --- Step 4: Route DNS (wildcard + bare domain) ---
echo ""
echo "[4/6] Routing DNS..."

# Wildcard: *.azirella.com → tunnel
echo "  Routing *.${DOMAIN} → tunnel..."
cloudflared tunnel route dns "${TUNNEL_NAME}" "*.${DOMAIN}" 2>/dev/null || echo "    (wildcard route may already exist)"

# Bare domain: azirella.com → tunnel
echo "  Routing ${DOMAIN} → tunnel..."
cloudflared tunnel route dns "${TUNNEL_NAME}" "${DOMAIN}" 2>/dev/null || echo "    (bare domain route may already exist)"

echo "  OK: DNS routes configured"
echo ""
echo "  NOTE: In Cloudflare dashboard, verify these DNS records exist:"
echo "    *.${DOMAIN}  CNAME  ${TUNNEL_ID}.cfargotunnel.com  (proxied)"
echo "    ${DOMAIN}    CNAME  ${TUNNEL_ID}.cfargotunnel.com  (proxied)"

# --- Step 5: Create config ---
echo ""
echo "[5/6] Creating tunnel config..."
CREDS_FILE="${HOME}/.cloudflared/${TUNNEL_ID}.json"
CONFIG_FILE="${HOME}/.cloudflared/config.yml"

cat > "${CONFIG_FILE}" << EOF
# Cloudflare Tunnel config for Autonomy Platform
# Wildcard routing: *.${DOMAIN} + ${DOMAIN} → localhost:${LOCAL_PORT}
# Created: $(date)

tunnel: ${TUNNEL_ID}
credentials-file: ${CREDS_FILE}

ingress:
  # All subdomains (login, autonomy, tenant slugs) → local proxy
  - hostname: "*.${DOMAIN}"
    service: http://localhost:${LOCAL_PORT}
    originRequest:
      noTLSVerify: true
      httpHostHeader: ""

  # Bare domain → local proxy
  - hostname: "${DOMAIN}"
    service: http://localhost:${LOCAL_PORT}
    originRequest:
      noTLSVerify: true

  # Catch-all (required by cloudflared)
  - service: http_status:404
EOF

echo "  OK: Config written to ${CONFIG_FILE}"

# --- Step 6: Start or install ---
echo ""
echo "[6/6] Starting tunnel..."
echo ""
echo "  Choose:"
echo "    1) Test run (foreground, Ctrl+C to stop)"
echo "    2) Install as systemd service (survives reboot)"
echo ""
read -rp "  Enter 1 or 2: " choice

case "$choice" in
    1)
        echo ""
        echo "  Starting tunnel in foreground..."
        echo "  Test URLs:"
        echo "    https://login.${DOMAIN}"
        echo "    https://autonomy.${DOMAIN}"
        echo "    https://${DOMAIN}"
        echo ""
        echo "  Press Ctrl+C to stop"
        echo ""
        cloudflared tunnel run "${TUNNEL_NAME}"
        ;;
    2)
        echo ""
        echo "  Installing as systemd service..."
        sudo cloudflared service install 2>/dev/null || echo "  (service may already be installed)"
        sudo systemctl enable cloudflared
        sudo systemctl restart cloudflared
        echo "  OK: Service installed and started"
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
echo "  URLs:"
echo "    https://login.${DOMAIN}          Login portal"
echo "    https://autonomy.${DOMAIN}       Default app"
echo "    https://{tenant}.${DOMAIN}       Tenant vanity subdomain"
echo ""
echo "  Next steps:"
echo "    1. Update .env:"
echo "       APP_DOMAIN=${DOMAIN}"
echo "       APP_SCHEME=https"
echo "       APP_PORT="
echo "       SUBDOMAIN_ROUTING_ENABLED=true"
echo "       COOKIE_DOMAIN=.${DOMAIN}"
echo "       CSRF_COOKIE_DOMAIN=.${DOMAIN}"
echo "       COOKIE_SECURE=true"
echo ""
echo "    2. Restart backend:"
echo "       docker compose restart backend"
echo ""
echo "    3. Populate tenant slugs:"
echo "       UPDATE tenants SET slug='food-dist', subdomain='food-dist' WHERE id=3;"
echo "       UPDATE tenants SET slug='sap-demo', subdomain='sap-demo' WHERE id=20;"
echo "       UPDATE tenants SET slug='d365-demo', subdomain='d365-demo' WHERE id=24;"
echo "       UPDATE tenants SET slug='odoo-demo', subdomain='odoo-demo' WHERE id=26;"
echo "============================================"

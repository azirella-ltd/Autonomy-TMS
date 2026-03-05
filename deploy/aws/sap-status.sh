#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Check SAP S/4HANA instance status and session cost
#
# Usage:
#   ./sap-status.sh                   # Uses terraform output
#   ./sap-status.sh i-0abc123def456   # Explicit instance ID
# ---------------------------------------------------------------------------
set -euo pipefail

INSTANCE_ID="${1:-${SAP_INSTANCE_ID:-}}"
REGION="${AWS_REGION:-eu-central-1}"

if [[ -z "$INSTANCE_ID" ]]; then
    if command -v terraform &>/dev/null && [[ -f "main.tf" ]]; then
        INSTANCE_ID=$(terraform output -raw sap_instance_id 2>/dev/null || true)
    fi
fi

if [[ -z "$INSTANCE_ID" || "$INSTANCE_ID" == "N/A" ]]; then
    echo "Error: No SAP instance ID."
    echo "  Usage: ./sap-status.sh i-0abc123def456"
    exit 1
fi

INFO=$(aws ec2 describe-instances \
    --instance-ids "$INSTANCE_ID" \
    --region "$REGION" \
    --query 'Reservations[0].Instances[0].{State:State.Name,Type:InstanceType,PublicIp:PublicIpAddress,PrivateIp:PrivateIpAddress,LaunchTime:LaunchTime}' \
    --output json)

STATE=$(echo "$INFO" | jq -r '.State')
TYPE=$(echo "$INFO" | jq -r '.Type')
PUBLIC_IP=$(echo "$INFO" | jq -r '.PublicIp // "none"')
PRIVATE_IP=$(echo "$INFO" | jq -r '.PrivateIp // "none"')
LAUNCH=$(echo "$INFO" | jq -r '.LaunchTime // "never"')

echo "SAP S/4HANA Instance Status (eu-central-1)"
echo "============================================"
echo "  Instance ID:  $INSTANCE_ID"
echo "  State:        $STATE"
echo "  Type:         $TYPE"
echo "  Public IP:    $PUBLIC_IP"
echo "  Private IP:   $PRIVATE_IP"
echo "  Last Launch:  $LAUNCH"
echo ""

if [[ "$STATE" == "running" ]]; then
    # Calculate uptime and cost (EUR 2.90/hr for r5.4xlarge in eu-central-1)
    LAUNCH_EPOCH=$(date -d "$LAUNCH" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%S" "${LAUNCH%%.*}" +%s 2>/dev/null || echo 0)
    NOW_EPOCH=$(date +%s)
    if [[ "$LAUNCH_EPOCH" -gt 0 ]]; then
        SECONDS_UP=$((NOW_EPOCH - LAUNCH_EPOCH))
        HOURS=$((SECONDS_UP / 3600))
        MINS=$(( (SECONDS_UP % 3600) / 60 ))
        COST=$(echo "scale=2; $SECONDS_UP / 3600 * 2.90" | bc 2>/dev/null || echo "N/A")
        echo "  Uptime:       ${HOURS}h ${MINS}m"
        echo "  Session cost: ~EUR $COST (~EUR 2.90/hr)"
    fi
    echo ""
    echo "  SAP GUI:   $PUBLIC_IP:3200"
    echo "  SAP HTTP:  http://$PUBLIC_IP:8000"
    echo "  SAP HTTPS: https://$PUBLIC_IP:44300"
    echo "  Fiori:     https://$PUBLIC_IP:44300/sap/bc/ui5_ui5/ui2/ushell/shells/abap/FioriLaunchpad.html"
    echo ""
    echo "  Stop with: ./sap-stop.sh $INSTANCE_ID"
else
    echo "  Monthly EBS cost (stopped): ~EUR 46/mo (500 GB gp3)"
    echo ""
    echo "  Start with: ./sap-start.sh $INSTANCE_ID"
fi

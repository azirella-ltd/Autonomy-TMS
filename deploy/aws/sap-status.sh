#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Check SAP S/4HANA instance status
#
# Usage:
#   ./sap-status.sh                   # Uses terraform output
#   ./sap-status.sh i-0abc123def456   # Explicit instance ID
# ---------------------------------------------------------------------------
set -euo pipefail

INSTANCE_ID="${1:-${SAP_INSTANCE_ID:-}}"
REGION="${AWS_REGION:-us-east-1}"

if [[ -z "$INSTANCE_ID" ]]; then
    if command -v terraform &>/dev/null && [[ -f "main.tf" ]]; then
        INSTANCE_ID=$(terraform output -raw sap_instance_id 2>/dev/null || true)
    fi
fi

if [[ -z "$INSTANCE_ID" || "$INSTANCE_ID" == "N/A" ]]; then
    echo "Error: No SAP instance ID."
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

echo "SAP S/4HANA Instance Status"
echo "=========================="
echo "  Instance ID:  $INSTANCE_ID"
echo "  State:        $STATE"
echo "  Type:         $TYPE"
echo "  Public IP:    $PUBLIC_IP"
echo "  Private IP:   $PRIVATE_IP"
echo "  Last Launch:  $LAUNCH"
echo ""

if [[ "$STATE" == "running" ]]; then
    # Calculate uptime cost
    LAUNCH_EPOCH=$(date -d "$LAUNCH" +%s 2>/dev/null || date -j -f "%Y-%m-%dT%H:%M:%S" "${LAUNCH%%.*}" +%s 2>/dev/null || echo 0)
    NOW_EPOCH=$(date +%s)
    if [[ "$LAUNCH_EPOCH" -gt 0 ]]; then
        HOURS=$(( (NOW_EPOCH - LAUNCH_EPOCH) / 3600 ))
        COST=$(echo "scale=2; $HOURS * 3.02" | bc 2>/dev/null || echo "N/A")
        echo "  Uptime:       ~${HOURS}h"
        echo "  Session cost: ~\$$COST"
    fi
    echo ""
    echo "  Stop with: ./sap-stop.sh $INSTANCE_ID"
else
    echo "  Start with: ./sap-start.sh $INSTANCE_ID"
fi

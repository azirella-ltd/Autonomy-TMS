#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Start SAP S/4HANA instance and wait for it to be running
#
# Usage:
#   ./sap-start.sh                    # Uses terraform output
#   ./sap-start.sh i-0abc123def456    # Explicit instance ID
#   SAP_INSTANCE_ID=i-0abc... ./sap-start.sh
# ---------------------------------------------------------------------------
set -euo pipefail

INSTANCE_ID="${1:-${SAP_INSTANCE_ID:-}}"
REGION="${AWS_REGION:-us-east-1}"

# Try terraform output if no ID provided
if [[ -z "$INSTANCE_ID" ]]; then
    if command -v terraform &>/dev/null && [[ -f "main.tf" ]]; then
        INSTANCE_ID=$(terraform output -raw sap_instance_id 2>/dev/null || true)
    fi
fi

if [[ -z "$INSTANCE_ID" || "$INSTANCE_ID" == "N/A" ]]; then
    echo "Error: No SAP instance ID. Provide as argument or set SAP_INSTANCE_ID."
    exit 1
fi

echo "Checking SAP instance $INSTANCE_ID..."
STATE=$(aws ec2 describe-instances \
    --instance-ids "$INSTANCE_ID" \
    --region "$REGION" \
    --query 'Reservations[0].Instances[0].State.Name' \
    --output text)

if [[ "$STATE" == "running" ]]; then
    IP=$(aws ec2 describe-instances \
        --instance-ids "$INSTANCE_ID" \
        --region "$REGION" \
        --query 'Reservations[0].Instances[0].PublicIpAddress' \
        --output text)
    echo "SAP instance is already running at $IP"
    exit 0
fi

if [[ "$STATE" != "stopped" ]]; then
    echo "Error: Instance is in state '$STATE'. Can only start from 'stopped'."
    exit 1
fi

echo "Starting SAP instance..."
aws ec2 start-instances --instance-ids "$INSTANCE_ID" --region "$REGION" >/dev/null

echo "Waiting for instance to reach 'running' state..."
aws ec2 wait instance-running --instance-ids "$INSTANCE_ID" --region "$REGION"

IP=$(aws ec2 describe-instances \
    --instance-ids "$INSTANCE_ID" \
    --region "$REGION" \
    --query 'Reservations[0].Instances[0].PublicIpAddress' \
    --output text)

PRIVATE_IP=$(aws ec2 describe-instances \
    --instance-ids "$INSTANCE_ID" \
    --region "$REGION" \
    --query 'Reservations[0].Instances[0].PrivateIpAddress' \
    --output text)

echo ""
echo "SAP S/4HANA instance is running."
echo "  Public IP:  $IP"
echo "  Private IP: $PRIVATE_IP (use this from Autonomy)"
echo "  SAP GUI:    $IP:3200"
echo "  SAP HTTP:   http://$IP:8000"
echo "  SAP HTTPS:  https://$IP:44300"
echo ""
echo "Note: SAP services may take 5-10 minutes to fully start after boot."
echo "Monitor with: ssh <user>@$IP 'sudo su - <sid>adm -c \"sapcontrol -nr 00 -function GetProcessList\"'"

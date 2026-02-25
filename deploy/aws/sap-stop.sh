#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Stop SAP S/4HANA instance gracefully
#
# Usage:
#   ./sap-stop.sh                     # Uses terraform output
#   ./sap-stop.sh i-0abc123def456     # Explicit instance ID
#   SAP_INSTANCE_ID=i-0abc... ./sap-stop.sh
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

if [[ "$STATE" == "stopped" ]]; then
    echo "SAP instance is already stopped."
    exit 0
fi

if [[ "$STATE" != "running" ]]; then
    echo "Error: Instance is in state '$STATE'. Can only stop from 'running'."
    exit 1
fi

echo "Stopping SAP instance..."
aws ec2 stop-instances --instance-ids "$INSTANCE_ID" --region "$REGION" >/dev/null

echo "Waiting for instance to reach 'stopped' state..."
aws ec2 wait instance-stopped --instance-ids "$INSTANCE_ID" --region "$REGION"

echo ""
echo "SAP S/4HANA instance is stopped."
echo "  EBS volumes are preserved (data is safe)."
echo "  No compute charges while stopped."
echo "  EBS storage charges continue (~\$0.08/GB/mo = ~\$40/mo for ${SAP_VOLUME_SIZE:-500}GB)."
echo ""
echo "Restart with: ./sap-start.sh $INSTANCE_ID"

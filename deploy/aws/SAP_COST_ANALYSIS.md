# SAP S/4HANA Start/Stop Cost Analysis

## The Problem

SAP S/4HANA requires a large instance (r5.4xlarge: 16 vCPU, 128 GB RAM) at **$3.02/hr**. Running 24/7 costs **$2,175/mo**. Since you only need it during integration testing, on-demand start/stop can save 60-90%.

## Approach Comparison

| Approach | Monthly Cost | Complexity | Best For |
|----------|-------------|------------|----------|
| Always-on | $2,175 | None | Active daily testing |
| Scheduled (weekdays 12h) | $660 | Low | Regular testing cadence |
| Manual on-demand | $44 base + $3.02/hr | None | Sporadic testing |
| Spot instance | ~$900 (60% savings) | Medium | Non-critical testing |

### Breakdown by Usage Pattern

**Scenario A: Heavy testing phase (daily for 2 weeks)**
- Always-on: $2,175
- Scheduled 12h/day: $660
- Manual 6h/day: $396 + $44 storage = $440
- **Recommended: Scheduled** (saves $1,515/mo vs always-on)

**Scenario B: Periodic testing (2-3 days/week)**
- Always-on: $2,175
- Scheduled weekdays 12h: $660
- Manual 8h × 3 days/week: $290 + $44 = $334
- **Recommended: Manual** (save when you know the schedule is irregular)

**Scenario C: Initial setup then occasional validation**
- Always-on: $2,175
- Manual 4h × 2 days/mo: $24 + $44 = $68
- **Recommended: Manual** (saves $2,107/mo)

## Recommended Strategy

**Phase 1 — Autonomy deployment (no SAP needed)**
- Deploy Autonomy only: `sap_ami_id = ""` in tfvars
- Monthly cost: ~$137 (Autonomy instance + EBS + EIP)
- Test Autonomy deployment, verify Docker Compose, run test suite

**Phase 2 — SAP provisioning**
- Provision SAP via SAP CAL, export as AMI
- Set `sap_ami_id` in tfvars, run `terraform apply`
- Enable scheduled start/stop during active testing weeks
- Switch to manual-only when testing cadence drops

**Phase 3 — Steady-state integration testing**
- Manual start/stop with CLI scripts
- Typical session: start SAP, run tests (2-4h), stop SAP
- Cost per session: ~$6-12

## What Happens When SAP Is Stopped

| Resource | Behavior | Cost |
|----------|----------|------|
| EC2 compute | No charges | $0 |
| EBS volumes | Preserved, charged at $0.08/GB/mo | ~$40/mo for 500GB |
| Elastic IP | Charged when NOT attached to running instance | ~$3.65/mo |
| SAP data | Fully preserved on EBS | Included in EBS |
| SAP config | Fully preserved | Included in EBS |
| HANA database | Preserved (cold start on boot) | Included in EBS |

**Data safety**: All data is on EBS volumes which persist independently of instance state. Stopping is completely safe — equivalent to a clean shutdown.

**Boot time**: SAP S/4HANA typically takes 5-10 minutes after EC2 reaches "running" state for all SAP services (dispatcher, message server, HANA) to fully initialize.

## Implementation Details

### Automated Schedule (Lambda + EventBridge)

The Terraform config creates two Lambda functions and two EventBridge rules:
- `autonomy-sap-start` — triggered by schedule or manual invocation
- `autonomy-sap-stop` — triggered by schedule or manual invocation

Default schedule: **weekdays 8 AM - 8 PM ET** (UTC: 1 PM - 1 AM next day)

Toggle on/off:
```bash
# Disable schedule (keep manual start/stop)
terraform apply -var="sap_auto_schedule_enabled=false"

# Re-enable schedule
terraform apply -var="sap_auto_schedule_enabled=true"

# Change hours (e.g., 6 AM - 6 PM ET)
terraform apply \
  -var='sap_schedule_start=cron(0 11 ? * MON-FRI *)' \
  -var='sap_schedule_stop=cron(0 23 ? * MON-FRI *)'
```

### Manual Start/Stop

Three options, from simplest to most automated:

```bash
# Option 1: Direct AWS CLI
aws ec2 start-instances --instance-ids i-0abc123
aws ec2 stop-instances  --instance-ids i-0abc123

# Option 2: Helper scripts (with status checks and wait)
cd deploy/aws
./sap-start.sh
./sap-stop.sh
./sap-status.sh

# Option 3: Lambda invocation (same functions as schedule uses)
aws lambda invoke --function-name autonomy-sap-start /dev/stdout
aws lambda invoke --function-name autonomy-sap-stop  /dev/stdout
```

### Makefile Integration

```bash
make sap-start    # Start SAP instance
make sap-stop     # Stop SAP instance
make sap-status   # Check SAP instance state + session cost
```

## Cost Summary

| Component | Always-On | Scheduled (12h weekday) | Manual Only |
|-----------|-----------|------------------------|-------------|
| Autonomy compute | $125 | $125 | $125 |
| Autonomy EBS + EIP | $12 | $12 | $12 |
| SAP compute | $2,175 | $660 | $3.02/hr |
| SAP EBS + EIP | $44 | $44 | $44 |
| Lambda + EventBridge | — | ~$0 | — |
| **Total** | **$2,356/mo** | **$841/mo** | **$181/mo + usage** |

**Bottom line**: For integration testing, start with manual on-demand (~$181/mo base). Switch to scheduled when testing daily. This saves $1,500-2,000/mo vs always-on.

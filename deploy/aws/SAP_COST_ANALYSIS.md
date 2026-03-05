# SAP S/4HANA Start/Stop Cost Analysis (Frankfurt / eu-central-1)

## The Problem

SAP S/4HANA requires a large instance (r5.4xlarge: 16 vCPU, 128 GB RAM) at **~EUR 2.90/hr** in Frankfurt. Running 24/7 costs **~EUR 2,088/mo**. Since you only need it during integration testing, on-demand start/stop can save 60-90%.

## Approach Comparison

| Approach | Monthly Cost | Complexity | Best For |
|----------|-------------|------------|----------|
| Always-on | EUR 2,088 | None | Active daily testing |
| Scheduled (weekdays 12h) | EUR 634 | Low | Regular testing cadence |
| Manual on-demand | EUR 50 base + EUR 2.90/hr | None | Sporadic testing |
| Spot instance | ~EUR 835 (60% savings) | Medium | Non-critical testing |

### Breakdown by Usage Pattern

**Scenario A: Heavy testing phase (daily for 2 weeks)**
- Always-on: EUR 2,088
- Scheduled 12h/day: EUR 634
- Manual 6h/day: EUR 380 + EUR 50 storage = EUR 430
- **Recommended: Scheduled** (saves EUR 1,454/mo vs always-on)

**Scenario B: Periodic testing (2-3 days/week)**
- Always-on: EUR 2,088
- Scheduled weekdays 12h: EUR 634
- Manual 8h x 3 days/week: EUR 278 + EUR 50 = EUR 328
- **Recommended: Manual** (save when you know the schedule is irregular)

**Scenario C: Initial setup then occasional validation**
- Always-on: EUR 2,088
- Manual 4h x 2 days/mo: EUR 23 + EUR 50 = EUR 73
- **Recommended: Manual** (saves EUR 2,015/mo)

## Recommended Strategy

**Phase 1 — Autonomy + SAP CAL IAM only (no SAP compute)**
- Deploy VPC + Autonomy: `sap_ami_id = ""`
- Monthly cost: ~EUR 150 (Autonomy instance + EBS + EIP)
- SAP CAL IAM role created (no cost)
- Test Autonomy deployment, verify Docker Compose, run test suite

**Phase 2 — SAP provisioning via SAP CAL**
- Connect SAP CAL to AWS using the IAM role from Phase 1
- SAP CAL provisions S/4HANA FAA into your VPC (~1-2 hours)
- Create AMI from CAL instance, set `sap_ami_id`, run `terraform apply`
- Enable manual start/stop via `./sap-start.sh` and `./sap-stop.sh`

**Phase 3 — Steady-state integration testing**
- Manual start/stop with CLI scripts
- Typical session: start SAP, run tests (2-4h), stop SAP
- Cost per session: ~EUR 6-12
- Enable scheduled start/stop if testing daily: `sap_auto_schedule_enabled = true`

## What Happens When SAP Is Stopped

| Resource | Behavior | Monthly Cost |
|----------|----------|------|
| EC2 compute | No charges | EUR 0 |
| EBS volumes | Preserved, charged at EUR 0.0912/GB/mo | ~EUR 46/mo for 500 GB |
| Elastic IP | Charged when NOT attached to running instance | ~EUR 3.65/mo |
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

Default schedule: **weekdays 8 AM - 8 PM CET** (UTC: 7 AM - 7 PM)

Toggle on/off:
```bash
# Disable schedule (keep manual start/stop)
terraform apply -var="sap_auto_schedule_enabled=false"

# Re-enable schedule
terraform apply -var="sap_auto_schedule_enabled=true"

# Change hours (e.g., 9 AM - 6 PM CET = 8 AM - 5 PM UTC)
terraform apply \
  -var='sap_schedule_start=cron(0 8 ? * MON-FRI *)' \
  -var='sap_schedule_stop=cron(0 17 ? * MON-FRI *)'
```

### Manual Start/Stop

```bash
# Shell scripts (recommended — with status checks, cost info, and wait)
cd deploy/aws
./sap-start.sh       # Start and wait for running
./sap-stop.sh        # Stop with session cost summary
./sap-status.sh      # Status + uptime + cost

# Direct AWS CLI
aws ec2 start-instances --instance-ids i-0abc123 --region eu-central-1
aws ec2 stop-instances  --instance-ids i-0abc123 --region eu-central-1

# Lambda invocation (same functions as schedule uses)
aws lambda invoke --function-name autonomy-sap-start --region eu-central-1 /dev/stdout
aws lambda invoke --function-name autonomy-sap-stop  --region eu-central-1 /dev/stdout
```

### Makefile Integration

```bash
make sap-start    # Start SAP instance
make sap-stop     # Stop SAP instance
make sap-status   # Check SAP instance state + session cost
```

## Frankfurt (eu-central-1) Pricing Reference

| Resource | Spec | Hourly | Monthly (730h) |
|----------|------|--------|----------------|
| r5.4xlarge (SAP) | 16 vCPU, 128 GB | EUR 2.90 | EUR 2,088 |
| t3.xlarge (Autonomy) | 4 vCPU, 16 GB | EUR 0.19 | EUR 137 |
| EBS gp3 | Per GB | — | EUR 0.0912/GB |
| Elastic IP (idle) | Per IP | — | EUR 3.65 |
| Data Transfer (out) | First 100 GB | — | EUR 0.09/GB |
| Lambda | Per 1M invocations | — | ~EUR 0 |

## Cost Summary

| Component | Always-On | Scheduled (12h weekday) | Manual Only |
|-----------|-----------|------------------------|-------------|
| Autonomy compute | EUR 137 | EUR 137 | EUR 137 |
| Autonomy EBS + EIP | EUR 13 | EUR 13 | EUR 13 |
| SAP compute | EUR 2,088 | EUR 634 | EUR 2.90/hr |
| SAP EBS + EIP | EUR 50 | EUR 50 | EUR 50 |
| Lambda + EventBridge | — | ~EUR 0 | — |
| **Total** | **EUR 2,288/mo** | **EUR 834/mo** | **EUR 200/mo + usage** |

**Bottom line**: For integration testing, start with manual on-demand (~EUR 200/mo base). Switch to scheduled when testing daily. This saves EUR 1,400-2,000/mo vs always-on.

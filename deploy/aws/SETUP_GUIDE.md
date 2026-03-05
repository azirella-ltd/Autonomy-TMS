# SAP S/4HANA on AWS — Setup Guide (Frankfurt)

Complete step-by-step guide from zero to a running SAP S/4HANA instance with IDES sample data, connected to Autonomy, with on-demand start/stop.

**Time**: ~3 hours (mostly waiting for SAP CAL provisioning)
**Cost**: ~EUR 200/mo base + EUR 2.90/hr when SAP is running

---

## Prerequisites

You will need:

| Requirement | How to Get It |
|-------------|---------------|
| **AWS Account** | [aws.amazon.com](https://aws.amazon.com/) |
| **SAP ID** | [account.sap.com/core/create/register](https://account.sap.com/core/create/register) (free) |
| **AWS CLI v2** | `curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o awscliv2.zip && unzip awscliv2.zip && sudo ./aws/install` |
| **Terraform >= 1.5** | `sudo apt install -y terraform` or [terraform.io/downloads](https://developer.hashicorp.com/terraform/downloads) |
| **jq** | `sudo apt install -y jq` |

---

## Phase 1: Deploy VPC + Autonomy + SAP CAL IAM Role

This creates the AWS infrastructure and the IAM role that SAP CAL needs.

### Step 1.1: Configure AWS CLI

```bash
aws configure
# AWS Access Key ID: <your access key>
# AWS Secret Access Key: <your secret key>
# Default region name: eu-central-1
# Default output format: json
```

Verify:
```bash
aws sts get-caller-identity
# Should show your account ID
```

### Step 1.2: Create terraform.tfvars

```bash
cd deploy/aws

# Find your public IP
MY_IP=$(curl -s ifconfig.me)
echo "Your IP: $MY_IP"

# Create tfvars from template
cp terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars`:
```hcl
aws_region   = "eu-central-1"
project_name = "autonomy"
environment  = "dev"

# SSH key — auto-generate
create_ssh_key = true

# IMPORTANT: Replace with your actual IP
allowed_ssh_cidrs = ["<YOUR_IP>/32"]
allowed_web_cidrs = ["0.0.0.0/0"]

# Git repo for Autonomy bootstrap
autonomy_repo_url = "https://github.com/your-org/Autonomy.git"

# Phase 1: No SAP instance yet
sap_ami_id          = ""
sap_cal_external_id = ""
```

### Step 1.3: Deploy Phase 1

```bash
terraform init
terraform plan    # Review what will be created
terraform apply   # Type "yes" to confirm
```

This creates:
- VPC with 2 public subnets in Frankfurt
- Security groups (Autonomy + SAP)
- SSH key pair (written to `autonomy-dev.pem`)
- **SAP CAL IAM role** (the key piece)
- Autonomy EC2 instance (t3.xlarge, auto-bootstraps)
- Elastic IP for Autonomy

### Step 1.4: Note the Outputs

```bash
terraform output
```

Key outputs you'll need:
```
sap_cal_role_arn = "arn:aws:iam::123456789012:role/autonomy-sap-cal-provisioner"
vpc_id           = "vpc-0abc123..."
subnet_id        = "subnet-0abc123..."
autonomy_url     = "http://3.120.xxx.xxx:8088"
```

**Save the `sap_cal_role_arn`** — you need it in Step 2.

---

## Phase 2: Provision SAP S/4HANA via SAP CAL

SAP Cloud Appliance Library (CAL) automates the S/4HANA deployment using the IAM role from Phase 1.

### Step 2.1: Connect AWS Account to SAP CAL

1. Go to [cal.sap.com](https://cal.sap.com) and log in with your SAP ID
2. Click **Accounts** in the left menu
3. Click **Create** → select **Amazon Web Services**
4. Fill in:
   - **Account Name**: `autonomy-dev`
   - **Authorization**: Select **"Use a cross account IAM role"**
   - **Role ARN**: Paste the `sap_cal_role_arn` from Step 1.4
   - **Region**: `eu-central-1 (Frankfurt)`
5. SAP CAL will show you an **External ID** (looks like: `CAL-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx`)
6. **Copy this External ID**

### Step 2.2: Secure the IAM Role with External ID

Update `terraform.tfvars`:
```hcl
sap_cal_external_id = "CAL-xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
```

Apply:
```bash
terraform apply
```

Go back to SAP CAL and click **Verify** — it should succeed now.

### Step 2.3: Create S/4HANA Appliance

1. In SAP CAL, click **Appliances** in the left menu
2. Search for **"SAP S/4HANA 2023, Fully-Activated Appliance"** (or latest version)
3. Click **Create Instance**
4. Configure:
   - **Account**: Select the AWS account you just connected
   - **Region**: `eu-central-1`
   - **Network**: Select **existing VPC** → choose the VPC from Step 1.4
   - **Subnet**: Select the subnet from Step 1.4
   - **Instance Type**: `r5.4xlarge` (default, 128 GB RAM)
   - **SSH Key**: SAP CAL will create its own, or you can upload the public key from `autonomy-dev.pem`
   - **Password**: Set a master password for all SAP users
5. Click **Create**

**Wait ~1-2 hours** for SAP CAL to provision and install everything.

### Step 2.4: Verify SAP is Running

Once SAP CAL shows "Active":
1. Note the **Instance ID** (visible in SAP CAL or EC2 console): `i-0abc123def456`
2. Note the **Public IP** assigned by SAP CAL

Test connectivity:
```bash
# From your local machine
curl -k https://<SAP_PUBLIC_IP>:44300/sap/public/ping
# Should return: "Server reached."
```

### Step 2.5: Create AMI from Running Instance

Create a reusable AMI so you can recreate the instance anytime:

```bash
SAP_INSTANCE_ID="i-0abc123def456"  # From Step 2.4

# Stop the instance first (cleaner AMI)
aws ec2 stop-instances --instance-ids $SAP_INSTANCE_ID --region eu-central-1
aws ec2 wait instance-stopped --instance-ids $SAP_INSTANCE_ID --region eu-central-1

# Create AMI
AMI_ID=$(aws ec2 create-image \
    --instance-id $SAP_INSTANCE_ID \
    --name "sap-s4hana-faa-$(date +%Y%m%d)" \
    --description "SAP S/4HANA FAA with IDES sample data" \
    --region eu-central-1 \
    --output text)

echo "AMI ID: $AMI_ID"
# Wait for AMI to complete (takes 10-30 min for 500 GB)
aws ec2 wait image-available --image-ids $AMI_ID --region eu-central-1
echo "AMI ready: $AMI_ID"
```

### Step 2.6: Import into Terraform

**Option A (recommended): Set AMI and let Terraform manage the instance**

Update `terraform.tfvars`:
```hcl
sap_ami_id = "ami-xxxxxxxxxxxxxxxxx"  # From Step 2.5
```

Apply:
```bash
terraform apply
```

Then terminate the original SAP CAL instance (Terraform created a new one from the AMI):
```bash
aws ec2 terminate-instances --instance-ids i-0abc123def456 --region eu-central-1
```

**Option B: Import the existing SAP CAL instance into Terraform**

If you prefer to keep the exact CAL instance:
```bash
# First, set sap_ami_id to the original AMI used by CAL (check EC2 console)
# Then import:
terraform import aws_instance.sap[0] i-0abc123def456
terraform plan  # Should show no changes (or minor tag diffs)
terraform apply
```

---

## Phase 3: Daily Operations

### Start/Stop SAP

```bash
cd deploy/aws

# Start SAP instance (~2 min boot + 10 min SAP services)
./sap-start.sh

# Check status and session cost
./sap-status.sh

# Stop SAP instance (EBS preserved, stops billing)
./sap-stop.sh
```

### Connect Autonomy to SAP

Once SAP is running:

1. Open Autonomy: `http://<autonomy_ip>:8088`
2. Login: `systemadmin@autonomy.ai` / `Autonomy@2026`
3. Navigate: **Administration → SAP Data Management**
4. Click **Add Connection**:
   ```
   Name:          S/4HANA Dev
   System Type:   S/4HANA
   Host:          <SAP_PRIVATE_IP>    (from terraform output sap_private_ip)
   System Number: 00
   Client:        100
   Connection:    RFC
   Username:      BPINST              (or your SAP user)
   Password:      <master password from Step 2.3>
   ```
5. Click **Test Connection** — should show green
6. Click **Save**

### Extract Sample Data

In SAP Data Management:
1. Click **Discover Tables** on your connection
2. Select tables to map:
   - `MARA` → Product (material master)
   - `MARC` → Site/Product mapping (plant data)
   - `T001W` → Site (plants/warehouses)
   - `EKKO`/`EKPO` → Inbound orders (purchase orders)
   - `VBAK`/`VBAP` → Outbound orders (sales orders)
   - `STKO`/`STPO` → Product BOM (bill of materials)
3. Click **Auto-Map Fields** (AI-powered fuzzy matching)
4. Review mappings and click **Start Ingestion**

### Enable Scheduled Start/Stop (Optional)

For regular testing, enable automatic weekday scheduling:

```bash
# In terraform.tfvars:
# sap_auto_schedule_enabled = true

terraform apply -var="sap_auto_schedule_enabled=true"
```

Default: 8 AM - 8 PM CET weekdays (~EUR 634/mo).

---

## SAP Default Users (FAA)

The Fully-Activated Appliance comes with pre-configured users:

| Username | Role | Client |
|----------|------|--------|
| `BPINST` | Business Process Master | 100 |
| `SAP*` | Super admin | 000 |
| `DDIC` | Data Dictionary | 000 |
| `DEVELOPER` | ABAP developer | 100 |

All passwords are set to what you chose during CAL provisioning (Step 2.3).

SAP GUI access (optional):
- Install SAP GUI from [tools.hana.ondemand.com](https://tools.hana.ondemand.com/#sapgui)
- Connection: `<Public_IP>`, System Number: `00`, Client: `100`

---

## Troubleshooting

### SAP CAL "Authorization Failed"
- Verify `sap_cal_role_arn` is correct: `terraform output sap_cal_role_arn`
- Verify External ID is set: check `sap_cal_external_id` in tfvars
- Run `terraform apply` after setting the External ID
- In SAP CAL, click **Re-verify**

### SAP Services Not Starting After Boot
```bash
# SSH into SAP instance
ssh -i autonomy-dev.pem ec2-user@<SAP_PUBLIC_IP>

# Check SAP service status
sudo su - <sid>adm
sapcontrol -nr 00 -function GetProcessList

# Manually start all SAP services
startsap all

# Check HANA status
HDB info
```

### Cannot Connect RFC from Autonomy
- Verify SAP is running: `./sap-status.sh`
- Check security group allows RFC (port 3300-3399) from VPC CIDR
- Use **private IP** (not public) from `terraform output sap_private_ip`
- Verify SAP ICM is active: `curl http://<SAP_PRIVATE_IP>:8000/sap/public/ping`

### Terraform Import Conflicts
If `terraform import` shows conflicts with SAP CAL-created resources:
```bash
# Remove from state and re-import
terraform state rm aws_instance.sap[0]
terraform import aws_instance.sap[0] i-0abc123def456
```

### Reset to Clean State
```bash
# Destroy everything (DESTRUCTIVE — will delete all resources)
terraform destroy

# Or just remove SAP instance
terraform apply -var="sap_ami_id="
```

---

## File Reference

| File | Purpose |
|------|---------|
| `main.tf` | VPC, networking, security groups, IAM, EC2 instances |
| `sap_scheduler.tf` | Lambda start/stop functions, EventBridge schedule |
| `variables.tf` | All configurable variables with Frankfurt defaults |
| `outputs.tf` | Connection info, SAP CAL instructions, cost estimates |
| `terraform.tfvars.example` | Template — copy to `terraform.tfvars` |
| `sap-start.sh` | Start SAP instance with status checks |
| `sap-stop.sh` | Stop SAP with session cost summary |
| `sap-status.sh` | Status, uptime, cost, connection URLs |
| `SAP_COST_ANALYSIS.md` | Detailed cost analysis for Frankfurt |

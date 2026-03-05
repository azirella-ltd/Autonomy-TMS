# ---------------------------------------------------------------------------
# Autonomy + SAP S/4HANA — AWS Infrastructure (Frankfurt)
# ---------------------------------------------------------------------------
#
# Provisions:
#   1. VPC with public subnets, IGW, route table
#   2. Security groups (Autonomy web + SAP RFC/GUI)
#   3. Optional SSH key pair generation
#   4. SAP CAL IAM role (cross-account trust for SAP Cloud Appliance Library)
#   5. Autonomy EC2 instance (always-on, Docker Compose)
#   6. SAP S/4HANA EC2 instance (on-demand, managed or imported from SAP CAL)
#   7. Lambda + EventBridge for SAP instance scheduling (see sap_scheduler.tf)
#
# Two-phase deployment:
#   Phase 1 — Deploy VPC + IAM + Autonomy (sap_ami_id = ""):
#     terraform init
#     terraform apply
#     → Copy sap_cal_role_arn output into SAP CAL portal
#
#   Phase 2 — After SAP CAL provisions S/4HANA:
#     Option A: Import CAL-created instance into Terraform state
#       terraform import aws_instance.sap[0] i-0abc123def456
#     Option B: Create AMI from CAL instance, set sap_ami_id
#       terraform apply -var="sap_ami_id=ami-xxxxxxxx"
#
# ---------------------------------------------------------------------------

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    tls = {
      source  = "hashicorp/tls"
      version = "~> 4.0"
    }
    local = {
      source  = "hashicorp/local"
      version = "~> 2.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = var.project_name
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}

locals {
  create_sap = var.sap_ami_id != ""
  create_key = var.create_ssh_key
}

# ---------------------------------------------------------------------------
# Data Sources
# ---------------------------------------------------------------------------

data "aws_caller_identity" "current" {}

data "aws_availability_zones" "available" {
  state = "available"
}

# Latest Ubuntu 22.04 for Autonomy
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-22.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# ---------------------------------------------------------------------------
# SSH Key Pair (optional — generates a new key pair if create_ssh_key = true)
# ---------------------------------------------------------------------------

resource "tls_private_key" "ssh" {
  count     = local.create_key ? 1 : 0
  algorithm = "ED25519"
}

resource "aws_key_pair" "generated" {
  count      = local.create_key ? 1 : 0
  key_name   = "${var.project_name}-${var.environment}"
  public_key = tls_private_key.ssh[0].public_key_openssh

  tags = { Name = "${var.project_name}-ssh-key" }
}

resource "local_file" "ssh_private_key" {
  count           = local.create_key ? 1 : 0
  content         = tls_private_key.ssh[0].private_key_openssh
  filename        = "${path.module}/${var.project_name}-${var.environment}.pem"
  file_permission = "0600"
}

locals {
  ssh_key_name = local.create_key ? aws_key_pair.generated[0].key_name : var.ssh_key_name
}

# ---------------------------------------------------------------------------
# VPC & Networking
# ---------------------------------------------------------------------------

resource "aws_vpc" "main" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "${var.project_name}-vpc" }
}

resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id
  tags   = { Name = "${var.project_name}-igw" }
}

resource "aws_subnet" "public_a" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, 1) # 10.0.1.0/24
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true

  tags = { Name = "${var.project_name}-public-a" }
}

resource "aws_subnet" "public_b" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, 2) # 10.0.2.0/24
  availability_zone       = data.aws_availability_zones.available.names[1]
  map_public_ip_on_launch = true

  tags = { Name = "${var.project_name}-public-b" }
}

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.igw.id
  }

  tags = { Name = "${var.project_name}-public-rt" }
}

resource "aws_route_table_association" "public_a" {
  subnet_id      = aws_subnet.public_a.id
  route_table_id = aws_route_table.public.id
}

resource "aws_route_table_association" "public_b" {
  subnet_id      = aws_subnet.public_b.id
  route_table_id = aws_route_table.public.id
}

# ---------------------------------------------------------------------------
# Security Groups
# ---------------------------------------------------------------------------

resource "aws_security_group" "autonomy" {
  name_prefix = "${var.project_name}-autonomy-"
  description = "Autonomy web UI + API"
  vpc_id      = aws_vpc.main.id

  # SSH
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.allowed_ssh_cidrs
    description = "SSH"
  }

  # HTTP (Autonomy UI via nginx proxy)
  ingress {
    from_port   = 8088
    to_port     = 8088
    protocol    = "tcp"
    cidr_blocks = var.allowed_web_cidrs
    description = "Autonomy HTTP"
  }

  # HTTPS
  ingress {
    from_port   = 8443
    to_port     = 8443
    protocol    = "tcp"
    cidr_blocks = var.allowed_web_cidrs
    description = "Autonomy HTTPS"
  }

  # Allow all within VPC (for SAP <-> Autonomy communication)
  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [var.vpc_cidr]
    description = "Intra-VPC"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "All outbound"
  }

  tags = { Name = "${var.project_name}-autonomy-sg" }

  lifecycle {
    create_before_destroy = true
  }
}

resource "aws_security_group" "sap" {
  name_prefix = "${var.project_name}-sap-"
  description = "SAP S/4HANA RFC, GUI, HTTP, HANA"
  vpc_id      = aws_vpc.main.id

  # SSH
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.allowed_ssh_cidrs
    description = "SSH"
  }

  # SAP GUI (dispatcher port 32NN where NN = instance number)
  ingress {
    from_port   = 3200
    to_port     = 3299
    protocol    = "tcp"
    cidr_blocks = var.allowed_web_cidrs
    description = "SAP GUI"
  }

  # SAP RFC Gateway (33NN)
  ingress {
    from_port   = 3300
    to_port     = 3399
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
    description = "SAP RFC (VPC only - Autonomy backend connects here)"
  }

  # SAP ICM HTTP (8000-8001)
  ingress {
    from_port   = 8000
    to_port     = 8001
    protocol    = "tcp"
    cidr_blocks = var.allowed_web_cidrs
    description = "SAP ICM HTTP (Fiori, OData)"
  }

  # SAP ICM HTTPS (443NN)
  ingress {
    from_port   = 44300
    to_port     = 44399
    protocol    = "tcp"
    cidr_blocks = var.allowed_web_cidrs
    description = "SAP ICM HTTPS"
  }

  # SAP HANA DB (300NN SQL, 300NN-2 indexserver)
  ingress {
    from_port   = 30013
    to_port     = 30015
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
    description = "HANA DB (VPC only - never expose publicly)"
  }

  # SAP Message Server HTTP (81NN)
  ingress {
    from_port   = 8100
    to_port     = 8199
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
    description = "SAP Message Server (VPC only)"
  }

  # Intra-VPC (covers RFC, HANA, internal comms)
  ingress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = [var.vpc_cidr]
    description = "Intra-VPC"
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
    description = "All outbound"
  }

  tags = { Name = "${var.project_name}-sap-sg" }

  lifecycle {
    create_before_destroy = true
  }
}

# ---------------------------------------------------------------------------
# IAM — SAP CAL Cross-Account Role
# ---------------------------------------------------------------------------
# SAP Cloud Appliance Library (cal.sap.com) needs an IAM role in YOUR
# account so it can provision EC2 instances, security groups, and EBS
# volumes on your behalf.
#
# Setup flow:
#   1. Go to cal.sap.com → Accounts → Create → Amazon Web Services
#   2. SAP CAL shows you the Account ID and External ID to trust
#   3. Set sap_cal_account_id and sap_cal_external_id in terraform.tfvars
#   4. terraform apply  (creates this role)
#   5. Copy the sap_cal_role_arn output back into SAP CAL
#   6. Click Verify in SAP CAL
# ---------------------------------------------------------------------------

resource "aws_iam_role" "sap_cal" {
  count = var.sap_cal_account_id != "" ? 1 : 0
  name  = "${var.project_name}-sap-cal-provisioner"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "AllowSAPCALAssumeRole"
      Effect = "Allow"
      Principal = {
        AWS = "arn:aws:iam::${var.sap_cal_account_id}:root"
      }
      Action = "sts:AssumeRole"
      Condition = var.sap_cal_external_id != "" ? {
        StringEquals = {
          "sts:ExternalId" = var.sap_cal_external_id
        }
      } : {}
    }]
  })

  max_session_duration = 7200

  tags = { Name = "${var.project_name}-sap-cal-role" }
}

resource "aws_iam_role_policy" "sap_cal_ec2" {
  count = var.sap_cal_account_id != "" ? 1 : 0
  name  = "sap-cal-ec2-management"
  role  = aws_iam_role.sap_cal[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EC2FullForProvisioning"
        Effect = "Allow"
        Action = [
          "ec2:RunInstances",
          "ec2:TerminateInstances",
          "ec2:StartInstances",
          "ec2:StopInstances",
          "ec2:RebootInstances",
          "ec2:DescribeInstances",
          "ec2:DescribeInstanceStatus",
          "ec2:DescribeInstanceTypes",
          "ec2:DescribeImages",
          "ec2:DescribeKeyPairs",
          "ec2:CreateKeyPair",
          "ec2:DeleteKeyPair",
          "ec2:ImportKeyPair",
          "ec2:DescribeRegions",
          "ec2:DescribeAvailabilityZones",
          "ec2:GetConsoleOutput",
          "ec2:CreateTags",
          "ec2:DeleteTags",
          "ec2:DescribeTags",
        ]
        Resource = "*"
      },
      {
        Sid    = "EC2NetworkForProvisioning"
        Effect = "Allow"
        Action = [
          "ec2:DescribeVpcs",
          "ec2:DescribeSubnets",
          "ec2:DescribeSecurityGroups",
          "ec2:CreateSecurityGroup",
          "ec2:DeleteSecurityGroup",
          "ec2:AuthorizeSecurityGroupIngress",
          "ec2:AuthorizeSecurityGroupEgress",
          "ec2:RevokeSecurityGroupIngress",
          "ec2:RevokeSecurityGroupEgress",
          "ec2:DescribeRouteTables",
          "ec2:DescribeInternetGateways",
          "ec2:DescribeNatGateways",
          "ec2:DescribeNetworkInterfaces",
          "ec2:AllocateAddress",
          "ec2:ReleaseAddress",
          "ec2:AssociateAddress",
          "ec2:DisassociateAddress",
          "ec2:DescribeAddresses",
        ]
        Resource = "*"
      },
      {
        Sid    = "EBSForProvisioning"
        Effect = "Allow"
        Action = [
          "ec2:CreateVolume",
          "ec2:DeleteVolume",
          "ec2:AttachVolume",
          "ec2:DetachVolume",
          "ec2:DescribeVolumes",
          "ec2:DescribeVolumeStatus",
          "ec2:ModifyVolume",
          "ec2:CreateSnapshot",
          "ec2:DeleteSnapshot",
          "ec2:DescribeSnapshots",
          "ec2:CopySnapshot",
          "ec2:RegisterImage",
          "ec2:DeregisterImage",
          "ec2:CopyImage",
          "ec2:DescribeImageAttribute",
          "ec2:ModifyImageAttribute",
        ]
        Resource = "*"
      },
      {
        Sid    = "IAMForInstanceProfiles"
        Effect = "Allow"
        Action = [
          "iam:PassRole",
          "iam:ListInstanceProfiles",
          "iam:GetInstanceProfile",
          "iam:CreateInstanceProfile",
          "iam:DeleteInstanceProfile",
          "iam:AddRoleToInstanceProfile",
          "iam:RemoveRoleFromInstanceProfile",
          "iam:CreateRole",
          "iam:DeleteRole",
          "iam:GetRole",
          "iam:PutRolePolicy",
          "iam:DeleteRolePolicy",
          "iam:GetRolePolicy",
          "iam:ListRolePolicies",
          "iam:AttachRolePolicy",
          "iam:DetachRolePolicy",
          "iam:ListAttachedRolePolicies",
        ]
        Resource = "*"
      },
      {
        Sid    = "S3ForBackupRestore"
        Effect = "Allow"
        Action = [
          "s3:CreateBucket",
          "s3:DeleteBucket",
          "s3:ListBucket",
          "s3:GetBucketLocation",
          "s3:PutObject",
          "s3:GetObject",
          "s3:DeleteObject",
          "s3:ListAllMyBuckets",
        ]
        Resource = "*"
      },
      {
        Sid    = "CloudFormationForStacks"
        Effect = "Allow"
        Action = [
          "cloudformation:CreateStack",
          "cloudformation:DeleteStack",
          "cloudformation:DescribeStacks",
          "cloudformation:DescribeStackEvents",
          "cloudformation:DescribeStackResources",
          "cloudformation:GetTemplate",
          "cloudformation:ListStacks",
          "cloudformation:UpdateStack",
        ]
        Resource = "*"
      },
    ]
  })
}

# ---------------------------------------------------------------------------
# IAM — Autonomy EC2 Instance Profile
# ---------------------------------------------------------------------------

resource "aws_iam_role" "autonomy_ec2" {
  name_prefix = "${var.project_name}-ec2-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "autonomy_ssm" {
  role       = aws_iam_role.autonomy_ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

# Allow Autonomy instance to start/stop SAP instance
resource "aws_iam_role_policy" "autonomy_sap_control" {
  name = "sap-instance-control"
  role = aws_iam_role.autonomy_ec2.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Action = [
        "ec2:StartInstances",
        "ec2:StopInstances",
        "ec2:DescribeInstances",
        "ec2:DescribeInstanceStatus",
      ]
      Resource = "*"
      Condition = {
        StringEquals = {
          "ec2:ResourceTag/Project"   = var.project_name
          "ec2:ResourceTag/Component" = "sap"
        }
      }
    },
    {
      Effect   = "Allow"
      Action   = ["ec2:DescribeInstances", "ec2:DescribeInstanceStatus"]
      Resource = "*"
    }]
  })
}

resource "aws_iam_instance_profile" "autonomy" {
  name_prefix = "${var.project_name}-"
  role        = aws_iam_role.autonomy_ec2.name
}

# ---------------------------------------------------------------------------
# Autonomy EC2 Instance
# ---------------------------------------------------------------------------

resource "aws_instance" "autonomy" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = var.autonomy_instance_type
  key_name               = local.ssh_key_name
  subnet_id              = aws_subnet.public_a.id
  vpc_security_group_ids = [aws_security_group.autonomy.id]
  iam_instance_profile   = aws_iam_instance_profile.autonomy.name

  root_block_device {
    volume_size = var.autonomy_volume_size
    volume_type = "gp3"
    encrypted   = true
  }

  user_data = <<-USERDATA
    #!/bin/bash
    set -euo pipefail
    exec > /var/log/autonomy-bootstrap.log 2>&1

    echo "[$(date)] Starting Autonomy bootstrap..."

    # System updates
    apt-get update -y
    apt-get install -y docker.io docker-compose-v2 git make jq awscli

    # Enable Docker
    systemctl enable docker
    systemctl start docker
    usermod -aG docker ubuntu

    # Clone repository
    cd /home/ubuntu
    su - ubuntu -c "git clone ${var.autonomy_repo_url} Autonomy" || true
    cd Autonomy

    # Initialize environment
    su - ubuntu -c "cd /home/ubuntu/Autonomy && make init-env"

    # Start services
    su - ubuntu -c "cd /home/ubuntu/Autonomy && make up"

    echo "[$(date)] Autonomy deployment complete"
  USERDATA

  tags = {
    Name      = "${var.project_name}-server"
    Component = "autonomy"
    Schedule  = "always-on"
  }
}

resource "aws_eip" "autonomy" {
  instance = aws_instance.autonomy.id
  domain   = "vpc"

  tags = { Name = "${var.project_name}-eip" }
}

# ---------------------------------------------------------------------------
# SAP S/4HANA EC2 Instance (conditional)
# ---------------------------------------------------------------------------
# Created when sap_ami_id is set. Can also be populated by importing a
# SAP CAL-provisioned instance:
#   terraform import aws_instance.sap[0] i-0abc123def456
# ---------------------------------------------------------------------------

resource "aws_instance" "sap" {
  count = local.create_sap ? 1 : 0

  ami                    = var.sap_ami_id
  instance_type          = var.sap_instance_type
  key_name               = local.ssh_key_name
  subnet_id              = aws_subnet.public_a.id
  vpc_security_group_ids = [aws_security_group.sap.id]

  root_block_device {
    volume_size = var.sap_volume_size
    volume_type = "gp3"
    iops        = 3000
    throughput  = 250
    encrypted   = true
  }

  # Start stopped — only run when needed
  instance_initiated_shutdown_behavior = "stop"

  tags = {
    Name      = "${var.project_name}-sap-s4hana"
    Component = "sap"
    Schedule  = "on-demand"
    AutoStop  = "true"
  }
}

resource "aws_eip" "sap" {
  count    = local.create_sap ? 1 : 0
  instance = aws_instance.sap[0].id
  domain   = "vpc"

  tags = { Name = "${var.project_name}-sap-eip" }
}

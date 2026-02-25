# ---------------------------------------------------------------------------
# Autonomy + SAP S/4HANA — AWS Infrastructure
# ---------------------------------------------------------------------------
#
# Provisions:
#   1. VPC with public subnet, IGW, route table
#   2. Security groups (Autonomy web + SAP RFC/GUI)
#   3. Autonomy EC2 instance (always-on, Docker Compose)
#   4. SAP S/4HANA EC2 instance (on-demand, scheduled start/stop)
#   5. Lambda + EventBridge for SAP instance scheduling
#   6. IAM roles for Lambda and EC2
#
# Usage:
#   terraform init
#   terraform plan -var="ssh_key_name=my-key"
#   terraform apply -var="ssh_key_name=my-key"
#
# SAP AMI:
#   The sap_ami_id variable must be set to an SAP S/4HANA AMI.
#   Options:
#     a) SAP CAL — provision via cal.sap.com, snapshot to AMI
#     b) AWS Marketplace — search "SAP S/4HANA" (BYOL)
#     c) Manual install on SUSE/RHEL AMI
#   Leave empty to skip SAP instance creation.
# ---------------------------------------------------------------------------

terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
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
}

# ---------------------------------------------------------------------------
# Data Sources
# ---------------------------------------------------------------------------

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
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, 1)  # 10.0.1.0/24
  availability_zone       = data.aws_availability_zones.available.names[0]
  map_public_ip_on_launch = true

  tags = { Name = "${var.project_name}-public-a" }
}

resource "aws_subnet" "public_b" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = cidrsubnet(var.vpc_cidr, 8, 2)  # 10.0.2.0/24
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

  # Allow all within VPC (for SAP ↔ Autonomy communication)
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
  count       = local.create_sap ? 1 : 0
  name_prefix = "${var.project_name}-sap-"
  description = "SAP S/4HANA RFC, GUI, HTTP"
  vpc_id      = aws_vpc.main.id

  # SSH
  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = var.allowed_ssh_cidrs
    description = "SSH"
  }

  # SAP GUI (3200-3299)
  ingress {
    from_port   = 3200
    to_port     = 3299
    protocol    = "tcp"
    cidr_blocks = var.allowed_web_cidrs
    description = "SAP GUI"
  }

  # SAP RFC Gateway (3300-3399)
  ingress {
    from_port   = 3300
    to_port     = 3399
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
    description = "SAP RFC (VPC only)"
  }

  # SAP HTTP/HTTPS (8000-8001, 44300-44399)
  ingress {
    from_port   = 8000
    to_port     = 8001
    protocol    = "tcp"
    cidr_blocks = var.allowed_web_cidrs
    description = "SAP ICM HTTP"
  }

  ingress {
    from_port   = 44300
    to_port     = 44399
    protocol    = "tcp"
    cidr_blocks = var.allowed_web_cidrs
    description = "SAP ICM HTTPS"
  }

  # SAP HANA DB (30015, 30013)
  ingress {
    from_port   = 30013
    to_port     = 30015
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
    description = "HANA DB (VPC only)"
  }

  # Intra-VPC
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
# IAM — Autonomy EC2 Instance Profile
# ---------------------------------------------------------------------------

resource "aws_iam_role" "autonomy_ec2" {
  name_prefix = "${var.project_name}-ec2-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "autonomy_ssm" {
  role       = aws_iam_role.autonomy_ec2.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
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
  key_name               = var.ssh_key_name
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

    # System updates
    apt-get update -y
    apt-get install -y docker.io docker-compose-v2 git make jq

    # Enable Docker
    systemctl enable docker
    systemctl start docker
    usermod -aG docker ubuntu

    # Clone repository
    cd /home/ubuntu
    git clone https://github.com/your-org/Autonomy.git || true
    cd Autonomy

    # Initialize environment
    make init-env

    # Start services
    make up

    echo "Autonomy deployment complete" > /home/ubuntu/deploy-status.txt
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

resource "aws_instance" "sap" {
  count = local.create_sap ? 1 : 0

  ami                    = var.sap_ami_id
  instance_type          = var.sap_instance_type
  key_name               = var.ssh_key_name
  subnet_id              = aws_subnet.public_a.id
  vpc_security_group_ids = [aws_security_group.sap[0].id]

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

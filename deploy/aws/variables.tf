# ---------------------------------------------------------------------------
# Autonomy + SAP S/4HANA — AWS Variables
# ---------------------------------------------------------------------------

variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Project name used for resource tagging"
  type        = string
  default     = "autonomy"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

# --- Autonomy instance ---

variable "autonomy_instance_type" {
  description = "EC2 instance type for Autonomy (4 vCPU, 16 GB)"
  type        = string
  default     = "t3.xlarge"
}

variable "autonomy_volume_size" {
  description = "Root EBS volume size in GB for Autonomy"
  type        = number
  default     = 100
}

# --- SAP S/4HANA instance ---

variable "sap_instance_type" {
  description = "EC2 instance type for SAP S/4HANA (16 vCPU, 128 GB)"
  type        = string
  default     = "r5.4xlarge"
}

variable "sap_volume_size" {
  description = "Root EBS volume size in GB for SAP"
  type        = number
  default     = 500
}

variable "sap_ami_id" {
  description = "AMI ID for SAP S/4HANA (from SAP CAL or marketplace). Leave empty to skip SAP instance creation."
  type        = string
  default     = ""
}

# --- Access ---

variable "ssh_key_name" {
  description = "Name of existing EC2 key pair for SSH access"
  type        = string
}

variable "allowed_ssh_cidrs" {
  description = "CIDR blocks allowed to SSH into instances"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "allowed_web_cidrs" {
  description = "CIDR blocks allowed to access Autonomy web UI"
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

# --- SAP Schedule ---

variable "sap_schedule_start" {
  description = "Cron expression (UTC) for auto-starting SAP instance. Empty = no schedule."
  type        = string
  default     = "cron(0 13 ? * MON-FRI *)"  # 8 AM ET weekdays
}

variable "sap_schedule_stop" {
  description = "Cron expression (UTC) for auto-stopping SAP instance. Empty = no schedule."
  type        = string
  default     = "cron(0 1 ? * MON-FRI *)"   # 8 PM ET weekdays
}

variable "sap_auto_schedule_enabled" {
  description = "Whether to enable the auto start/stop schedule for SAP"
  type        = bool
  default     = true
}

# --- Tags ---

variable "environment" {
  description = "Environment tag (dev, staging, prod)"
  type        = string
  default     = "dev"
}

# ---------------------------------------------------------------------------
# Autonomy + SAP S/4HANA — Variables (Frankfurt / eu-central-1)
# ---------------------------------------------------------------------------

# --- Region & Project ---

variable "aws_region" {
  description = "AWS region for deployment"
  type        = string
  default     = "eu-central-1" # Frankfurt
}

variable "project_name" {
  description = "Project name used for resource naming and tagging"
  type        = string
  default     = "autonomy"
}

variable "environment" {
  description = "Environment tag (dev, staging, prod)"
  type        = string
  default     = "dev"
}

# --- VPC ---

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

# --- SSH Key ---

variable "create_ssh_key" {
  description = "Generate a new SSH key pair (true) or use an existing one (false). When true, the private key is written to deploy/aws/<project>-<env>.pem"
  type        = bool
  default     = true
}

variable "ssh_key_name" {
  description = "Name of existing EC2 key pair. Only used when create_ssh_key = false."
  type        = string
  default     = ""
}

# --- Autonomy Instance ---

variable "autonomy_instance_type" {
  description = "EC2 instance type for Autonomy (4 vCPU, 16 GB recommended)"
  type        = string
  default     = "t3.xlarge" # ~EUR 0.19/hr in eu-central-1
}

variable "autonomy_volume_size" {
  description = "Root EBS volume size in GB for Autonomy"
  type        = number
  default     = 100
}

variable "autonomy_repo_url" {
  description = "Git repository URL for Autonomy (used in EC2 bootstrap user_data)"
  type        = string
  default     = "https://github.com/your-org/Autonomy.git"
}

# --- SAP S/4HANA Instance ---

variable "sap_instance_type" {
  description = "EC2 instance type for SAP S/4HANA. r5.4xlarge = 16 vCPU, 128 GB RAM (SAP minimum). x2idn.xlarge is cheaper but slower."
  type        = string
  default     = "r5.4xlarge" # ~EUR 2.90/hr in eu-central-1
}

variable "sap_volume_size" {
  description = "Root EBS volume size in GB for SAP (500 GB minimum for S/4HANA FAA)"
  type        = number
  default     = 500
}

variable "sap_ami_id" {
  description = "AMI ID for SAP S/4HANA. Leave empty for Phase 1 (deploy Autonomy + SAP CAL IAM only). Set after creating AMI from SAP CAL instance."
  type        = string
  default     = ""
}

# --- SAP CAL Integration ---

variable "sap_cal_account_id" {
  description = "SAP CAL AWS Account ID. Get this from: SAP CAL > Accounts > Create > AWS (SAP CAL shows the account ID to trust). Leave empty to skip SAP CAL IAM role creation."
  type        = string
  default     = ""
}

variable "sap_cal_external_id" {
  description = "External ID from SAP CAL portal. Get this from: SAP CAL > Accounts > Create > AWS. Leave empty initially, then set after SAP CAL generates it."
  type        = string
  default     = ""
}

# --- Network Access ---

variable "allowed_ssh_cidrs" {
  description = "CIDR blocks allowed SSH access. IMPORTANT: restrict to your IP (e.g. [\"203.0.113.10/32\"]). Use 'curl ifconfig.me' to find your IP."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

variable "allowed_web_cidrs" {
  description = "CIDR blocks allowed to access web UIs (Autonomy, SAP Fiori). Restrict to your IP for security."
  type        = list(string)
  default     = ["0.0.0.0/0"]
}

# --- SAP Schedule (Lambda start/stop) ---

variable "sap_auto_schedule_enabled" {
  description = "Enable automatic weekday start/stop for SAP instance via Lambda + EventBridge"
  type        = bool
  default     = false # Manual-only by default to minimize cost
}

variable "sap_schedule_start" {
  description = "Cron expression (UTC) for auto-starting SAP instance. Default: 7 AM UTC = 8 AM CET / 9 AM CEST"
  type        = string
  default     = "cron(0 7 ? * MON-FRI *)"
}

variable "sap_schedule_stop" {
  description = "Cron expression (UTC) for auto-stopping SAP instance. Default: 7 PM UTC = 8 PM CET / 9 PM CEST"
  type        = string
  default     = "cron(0 19 ? * MON-FRI *)"
}

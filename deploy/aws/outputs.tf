# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

# --- SSH Key ---

output "ssh_private_key_file" {
  description = "Path to generated SSH private key (only if create_ssh_key = true)"
  value       = local.create_key ? local_file.ssh_private_key[0].filename : "N/A — using existing key '${var.ssh_key_name}'"
}

output "ssh_command" {
  description = "SSH command for Autonomy instance"
  value       = local.create_key ? "ssh -i ${local_file.ssh_private_key[0].filename} ubuntu@${aws_eip.autonomy.public_ip}" : "ssh -i ~/.ssh/${var.ssh_key_name}.pem ubuntu@${aws_eip.autonomy.public_ip}"
}

# --- SAP CAL ---

output "sap_cal_role_arn" {
  description = "IAM Role ARN to paste into SAP CAL portal (Accounts > Create > AWS)"
  value       = var.sap_cal_account_id != "" ? aws_iam_role.sap_cal[0].arn : "Set sap_cal_account_id first (get it from SAP CAL portal)"
}

output "sap_cal_setup_instructions" {
  description = "Next steps for SAP CAL setup"
  value = (var.sap_cal_account_id == ""
    ? join("\n", [
        "",
        "  SAP CAL Setup - Next steps:",
        "",
        "  1. Go to https://cal.sap.com",
        "  2. Accounts > Create > Amazon Web Services",
        "  3. SAP CAL shows you an Account ID and External ID",
        "  4. Set sap_cal_account_id and sap_cal_external_id in terraform.tfvars",
        "  5. Run: terraform apply",
        "  6. Copy the sap_cal_role_arn output back into SAP CAL",
        "  7. Click Verify in SAP CAL",
        "  8. In SAP CAL: Appliances > S/4HANA FAA > Create",
        "     Region: eu-central-1 (Frankfurt)",
        "     VPC: ${aws_vpc.main.id}",
        "     Subnet: ${aws_subnet.public_a.id}",
        "",
      ])
    : var.sap_cal_account_id != "" ? join("\n", [
        "",
        "  SAP CAL role created. Paste this ARN into SAP CAL:",
        "  ${aws_iam_role.sap_cal[0].arn}",
        "",
      ])
    : "SAP CAL not configured."
  )
}

# --- Autonomy ---

output "autonomy_public_ip" {
  description = "Autonomy instance public IP (Elastic IP)"
  value       = aws_eip.autonomy.public_ip
}

output "autonomy_url" {
  description = "Autonomy web UI URL"
  value       = "http://${aws_eip.autonomy.public_ip}:8088"
}

output "autonomy_instance_id" {
  description = "Autonomy EC2 instance ID"
  value       = aws_instance.autonomy.id
}

# --- SAP ---

output "sap_public_ip" {
  description = "SAP instance public IP (Elastic IP)"
  value       = local.create_sap ? aws_eip.sap[0].public_ip : "N/A — set sap_ami_id to deploy SAP instance"
}

output "sap_instance_id" {
  description = "SAP EC2 instance ID (use with sap-start.sh / sap-stop.sh)"
  value       = local.create_sap ? aws_instance.sap[0].id : "N/A"
}

output "sap_private_ip" {
  description = "SAP private IP (for Autonomy -> SAP RFC/OData within VPC)"
  value       = local.create_sap ? aws_instance.sap[0].private_ip : "N/A"
}

output "sap_connection_info" {
  description = "SAP connection details for Autonomy integration"
  value = (local.create_sap
    ? join("\n", [
        "",
        "  SAP S/4HANA Connection Details:",
        "    SAP GUI:     ${aws_eip.sap[0].public_ip}:3200 (instance 00)",
        "    SAP HTTP:    http://${aws_eip.sap[0].public_ip}:8000",
        "    SAP HTTPS:   https://${aws_eip.sap[0].public_ip}:44300",
        "    HANA Studio: ${aws_instance.sap[0].private_ip}:30015 (VPC only)",
        "",
        "  Autonomy SAP Data Management config:",
        "    Host:          ${aws_instance.sap[0].private_ip}",
        "    System Number: 00",
        "    Client:        100",
        "    Type:          RFC",
        "",
      ])
    : "SAP instance not deployed yet"
  )
}

# --- Networking ---

output "vpc_id" {
  description = "VPC ID (provide to SAP CAL during provisioning)"
  value       = aws_vpc.main.id
}

output "subnet_id" {
  description = "Public subnet ID (provide to SAP CAL during provisioning)"
  value       = aws_subnet.public_a.id
}

output "sap_security_group_id" {
  description = "SAP security group ID (provide to SAP CAL if it asks)"
  value       = aws_security_group.sap.id
}

# --- Start/Stop ---

output "sap_start_command" {
  description = "Command to start SAP instance"
  value       = local.create_sap ? "./sap-start.sh ${aws_instance.sap[0].id}" : "N/A"
}

output "sap_stop_command" {
  description = "Command to stop SAP instance"
  value       = local.create_sap ? "./sap-stop.sh ${aws_instance.sap[0].id}" : "N/A"
}

output "sap_schedule" {
  description = "SAP auto-schedule status"
  value       = local.create_sap && var.sap_auto_schedule_enabled ? "Enabled: start=${var.sap_schedule_start}, stop=${var.sap_schedule_stop}" : "Disabled (manual start/stop only)"
}

# --- Cost Estimate ---

output "monthly_cost_estimate" {
  description = "Estimated monthly cost (eu-central-1 Frankfurt pricing)"
  value = <<-EOT

    Autonomy (${var.autonomy_instance_type}, 24/7):
      Compute: ~EUR 137/mo
      EBS ${var.autonomy_volume_size}GB gp3: ~EUR 9/mo
      Elastic IP: ~EUR 3.65/mo
      Subtotal: ~EUR 150/mo

    SAP (${var.sap_instance_type}, ${local.create_sap ? (var.sap_auto_schedule_enabled ? "scheduled" : "on-demand") : "not deployed"}):
      ${local.create_sap ? (var.sap_auto_schedule_enabled ? "Weekday 12h/day: ~EUR 700/mo" : "Per hour when running: ~EUR 2.90/hr") : "Not deployed yet — EUR 0"}
      ${local.create_sap ? "EBS ${var.sap_volume_size}GB gp3: ~EUR 46/mo" : ""}
      ${local.create_sap ? "Elastic IP (when stopped): ~EUR 3.65/mo" : ""}

    Data Transfer: ~EUR 10-50/mo (estimate)

    ${local.create_sap ? (var.sap_auto_schedule_enabled ? "TOTAL: ~EUR 910/mo" : "TOTAL: ~EUR 210/mo base + EUR 2.90/hr SAP usage") : "TOTAL: ~EUR 160/mo (Autonomy only, Phase 1)"}
  EOT
}

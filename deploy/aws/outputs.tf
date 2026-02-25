# ---------------------------------------------------------------------------
# Outputs
# ---------------------------------------------------------------------------

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

output "sap_public_ip" {
  description = "SAP instance public IP (Elastic IP)"
  value       = local.create_sap ? aws_eip.sap[0].public_ip : "N/A — no SAP AMI provided"
}

output "sap_instance_id" {
  description = "SAP EC2 instance ID"
  value       = local.create_sap ? aws_instance.sap[0].id : "N/A"
}

output "sap_private_ip" {
  description = "SAP private IP (for Autonomy → SAP RFC/OData within VPC)"
  value       = local.create_sap ? aws_instance.sap[0].private_ip : "N/A"
}

output "sap_start_command" {
  description = "Manual SAP start command"
  value       = local.create_sap ? "aws lambda invoke --function-name ${var.project_name}-sap-start /dev/stdout" : "N/A"
}

output "sap_stop_command" {
  description = "Manual SAP stop command"
  value       = local.create_sap ? "aws lambda invoke --function-name ${var.project_name}-sap-stop /dev/stdout" : "N/A"
}

output "sap_schedule" {
  description = "SAP auto-schedule status"
  value       = local.create_sap && var.sap_auto_schedule_enabled ? "Enabled: start=${var.sap_schedule_start}, stop=${var.sap_schedule_stop}" : "Disabled"
}

output "vpc_id" {
  description = "VPC ID"
  value       = aws_vpc.main.id
}

output "monthly_cost_estimate" {
  description = "Estimated monthly cost breakdown"
  value = <<-EOT
    Autonomy (${var.autonomy_instance_type}, 24/7):
      Compute: ~$125/mo
      EBS ${var.autonomy_volume_size}GB gp3: ~$8/mo
      Elastic IP: $3.65/mo
      Subtotal: ~$137/mo

    SAP (${var.sap_instance_type}, ${var.sap_auto_schedule_enabled ? "scheduled" : "on-demand"}):
      ${var.sap_auto_schedule_enabled ? "Weekday 12h/day: ~$660/mo" : "Per hour when running: ~$3.02/hr"}
      EBS ${var.sap_volume_size}GB gp3: ~$40/mo
      Elastic IP (when stopped): ~$3.65/mo
      ${var.sap_auto_schedule_enabled ? "Subtotal: ~$704/mo" : "Subtotal: $44/mo + $3.02/hr usage"}

    Data Transfer: ~$10-50/mo (estimate)

    ${var.sap_auto_schedule_enabled ? "TOTAL: ~$850-900/mo" : "TOTAL: ~$190/mo base + $3.02/hr SAP usage"}
  EOT
}

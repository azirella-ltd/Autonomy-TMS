# ---------------------------------------------------------------------------
# SAP Instance Start/Stop Automation (Frankfurt)
# ---------------------------------------------------------------------------
#
# Uses Lambda + EventBridge to automatically start/stop the SAP instance
# on a configurable schedule (default: weekdays 8 AM - 8 PM CET).
#
# Manual invocation:
#   ./sap-start.sh    # Shell script with status checks
#   ./sap-stop.sh     # Shell script with cost info
#   ./sap-status.sh   # Status + session cost estimate
#
# Or via Lambda:
#   aws lambda invoke --function-name autonomy-sap-start --region eu-central-1 /dev/stdout
#   aws lambda invoke --function-name autonomy-sap-stop  --region eu-central-1 /dev/stdout
#
# Or direct AWS CLI:
#   aws ec2 start-instances --instance-ids <id> --region eu-central-1
#   aws ec2 stop-instances  --instance-ids <id> --region eu-central-1
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# IAM for Lambda
# ---------------------------------------------------------------------------

resource "aws_iam_role" "sap_scheduler" {
  count       = local.create_sap ? 1 : 0
  name_prefix = "${var.project_name}-sap-sched-"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })
}

resource "aws_iam_role_policy" "sap_scheduler" {
  count = local.create_sap ? 1 : 0
  name  = "ec2-start-stop"
  role  = aws_iam_role.sap_scheduler[0].id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ec2:StartInstances", "ec2:StopInstances"]
        Resource = "arn:aws:ec2:${var.aws_region}:${data.aws_caller_identity.current.account_id}:instance/${aws_instance.sap[0].id}"
      },
      {
        Effect   = "Allow"
        Action   = ["ec2:DescribeInstances", "ec2:DescribeInstanceStatus"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:${var.aws_region}:${data.aws_caller_identity.current.account_id}:*"
      }
    ]
  })
}

# ---------------------------------------------------------------------------
# Lambda Functions
# ---------------------------------------------------------------------------

data "archive_file" "sap_start" {
  count       = local.create_sap ? 1 : 0
  type        = "zip"
  output_path = "${path.module}/.terraform/sap_start.zip"

  source {
    content = <<-PYTHON
      import boto3
      import os
      import json

      def handler(event, context):
          ec2 = boto3.client('ec2', region_name=os.environ['AWS_REGION'])
          instance_id = os.environ['SAP_INSTANCE_ID']

          resp = ec2.describe_instances(InstanceIds=[instance_id])
          state = resp['Reservations'][0]['Instances'][0]['State']['Name']

          if state == 'running':
              ip = resp['Reservations'][0]['Instances'][0].get('PublicIpAddress', 'pending')
              return {'statusCode': 200, 'body': json.dumps({
                  'message': f'SAP instance {instance_id} is already running at {ip}',
                  'state': state, 'ip': ip
              })}

          if state != 'stopped':
              return {'statusCode': 409, 'body': json.dumps({
                  'message': f'SAP instance is in state {state}, cannot start',
                  'state': state
              })}

          ec2.start_instances(InstanceIds=[instance_id])
          return {'statusCode': 200, 'body': json.dumps({
              'message': f'Starting SAP instance {instance_id}. Services ready in ~10 min.',
              'state': 'pending'
          })}
    PYTHON
    filename = "index.py"
  }
}

data "archive_file" "sap_stop" {
  count       = local.create_sap ? 1 : 0
  type        = "zip"
  output_path = "${path.module}/.terraform/sap_stop.zip"

  source {
    content = <<-PYTHON
      import boto3
      import os
      import json

      def handler(event, context):
          ec2 = boto3.client('ec2', region_name=os.environ['AWS_REGION'])
          instance_id = os.environ['SAP_INSTANCE_ID']

          resp = ec2.describe_instances(InstanceIds=[instance_id])
          state = resp['Reservations'][0]['Instances'][0]['State']['Name']

          if state == 'stopped':
              return {'statusCode': 200, 'body': json.dumps({
                  'message': f'SAP instance {instance_id} is already stopped',
                  'state': state
              })}

          if state != 'running':
              return {'statusCode': 409, 'body': json.dumps({
                  'message': f'SAP instance is in state {state}, cannot stop',
                  'state': state
              })}

          ec2.stop_instances(InstanceIds=[instance_id])
          return {'statusCode': 200, 'body': json.dumps({
              'message': f'Stopping SAP instance {instance_id}. EBS data preserved.',
              'state': 'stopping'
          })}
    PYTHON
    filename = "index.py"
  }
}

resource "aws_lambda_function" "sap_start" {
  count         = local.create_sap ? 1 : 0
  function_name = "${var.project_name}-sap-start"
  role          = aws_iam_role.sap_scheduler[0].arn
  handler       = "index.handler"
  runtime       = "python3.12"
  timeout       = 30
  filename      = data.archive_file.sap_start[0].output_path

  environment {
    variables = {
      SAP_INSTANCE_ID = aws_instance.sap[0].id
    }
  }

  tags = { Name = "${var.project_name}-sap-start" }
}

resource "aws_lambda_function" "sap_stop" {
  count         = local.create_sap ? 1 : 0
  function_name = "${var.project_name}-sap-stop"
  role          = aws_iam_role.sap_scheduler[0].arn
  handler       = "index.handler"
  runtime       = "python3.12"
  timeout       = 30
  filename      = data.archive_file.sap_stop[0].output_path

  environment {
    variables = {
      SAP_INSTANCE_ID = aws_instance.sap[0].id
    }
  }

  tags = { Name = "${var.project_name}-sap-stop" }
}

# ---------------------------------------------------------------------------
# EventBridge Scheduled Rules (CET weekdays)
# ---------------------------------------------------------------------------

resource "aws_cloudwatch_event_rule" "sap_start" {
  count               = local.create_sap && var.sap_auto_schedule_enabled ? 1 : 0
  name                = "${var.project_name}-sap-auto-start"
  description         = "Auto-start SAP instance (weekdays 8 AM CET / 9 AM CEST)"
  schedule_expression = var.sap_schedule_start
  state               = "ENABLED"
}

resource "aws_cloudwatch_event_target" "sap_start" {
  count     = local.create_sap && var.sap_auto_schedule_enabled ? 1 : 0
  rule      = aws_cloudwatch_event_rule.sap_start[0].name
  target_id = "sap-start-lambda"
  arn       = aws_lambda_function.sap_start[0].arn
}

resource "aws_lambda_permission" "sap_start_schedule" {
  count         = local.create_sap && var.sap_auto_schedule_enabled ? 1 : 0
  statement_id  = "AllowEventBridgeStart"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.sap_start[0].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.sap_start[0].arn
}

resource "aws_cloudwatch_event_rule" "sap_stop" {
  count               = local.create_sap && var.sap_auto_schedule_enabled ? 1 : 0
  name                = "${var.project_name}-sap-auto-stop"
  description         = "Auto-stop SAP instance (weekdays 8 PM CET / 9 PM CEST)"
  schedule_expression = var.sap_schedule_stop
  state               = "ENABLED"
}

resource "aws_cloudwatch_event_target" "sap_stop" {
  count     = local.create_sap && var.sap_auto_schedule_enabled ? 1 : 0
  rule      = aws_cloudwatch_event_rule.sap_stop[0].name
  target_id = "sap-stop-lambda"
  arn       = aws_lambda_function.sap_stop[0].arn
}

resource "aws_lambda_permission" "sap_stop_schedule" {
  count         = local.create_sap && var.sap_auto_schedule_enabled ? 1 : 0
  statement_id  = "AllowEventBridgeStop"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.sap_stop[0].function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.sap_stop[0].arn
}

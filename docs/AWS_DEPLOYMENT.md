# AWS Deployment

The repository includes a deployment script for hosting the ChatGPT Actions adapter on AWS Lambda with a Lambda Function URL.

## Prerequisites

- AWS CLI installed and authenticated.
- An IAM role for Lambda with basic execution permissions.
- A public HTTPS URL that ChatGPT can use for the action service. For Lambda Function URLs, set `--server-url` to the final function URL after the first deploy and redeploy once so `/openapi.json` advertises the correct URL.

## Install Optional Dependencies

```bash
.venv/bin/python -m pip install -e '.[chatgpt-plugin,aws]'
```

## Dry Run

```bash
.venv/bin/python scripts/deploy_aws.py \
  --function-name snowflake-agent-context-actions \
  --role-arn arn:aws:iam::123456789012:role/lambda-actions-role \
  --region us-east-1 \
  --server-url https://example.lambda-url.us-east-1.on.aws \
  --dry-run
```

## Deploy

```bash
.venv/bin/python scripts/deploy_aws.py \
  --function-name snowflake-agent-context-actions \
  --role-arn arn:aws:iam::123456789012:role/lambda-actions-role \
  --region us-east-1 \
  --server-url https://example.lambda-url.us-east-1.on.aws
```

The script builds `dist/aws-lambda/action-service.zip`, creates the Lambda function if it does not exist, updates code/configuration when it does exist, and creates a public Lambda Function URL by default.

## Handler

The deployed Lambda handler is:

```text
openai_snowflake_agent_context.aws_lambda.handler
```

The handler serves the ChatGPT Actions endpoints documented in [CHATGPT_PLUGIN_ACTIONS.md](CHATGPT_PLUGIN_ACTIONS.md).


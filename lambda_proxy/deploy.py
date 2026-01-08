#!/usr/bin/env python3
"""
Deploy Lambda + API Gateway to expose the AgentCore agent as a public HTTP endpoint.

Usage:
    AWS_PROFILE=tt-aws python deploy.py

This script will:
1. Create/update a Lambda function
2. Create/update an API Gateway HTTP API
3. Output the public URL for your agent
"""

import json
import os
import time
import zipfile
from io import BytesIO

import boto3

# Configuration - Set these via environment variables or modify for your account
REGION = os.environ.get("AWS_REGION", "eu-west-1")
FUNCTION_NAME = os.environ.get("LAMBDA_FUNCTION_NAME", "idea-lattice-agent-proxy")
API_NAME = os.environ.get("API_GATEWAY_NAME", "idea-lattice-agent-api")
AGENT_ARN = os.environ.get("AGENT_ARN")  # Required: your AgentCore runtime ARN

if not AGENT_ARN:
    print("❌ Error: AGENT_ARN environment variable is required")
    print("   Set it to your Bedrock AgentCore runtime ARN, e.g.:")
    print("   export AGENT_ARN='arn:aws:bedrock-agentcore:eu-west-1:123456789:runtime/your-agent-id'")
    exit(1)

def get_lambda_policy(agent_arn):
    """Generate IAM policy for Lambda to invoke AgentCore."""
    return {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Action": "bedrock-agentcore:InvokeAgentRuntime",
                "Resource": "*"  # Wildcard needed due to runtime-endpoint suffix
            },
            {
                "Effect": "Allow",
                "Action": [
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents"
                ],
                "Resource": "arn:aws:logs:*:*:*"
            }
        ]
    }

ASSUME_ROLE_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Principal": {"Service": "lambda.amazonaws.com"},
            "Action": "sts:AssumeRole"
        }
    ]
}


def create_deployment_package():
    """Create a ZIP file containing the Lambda code."""
    print("📦 Creating deployment package...")

    buffer = BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Read the handler code
        handler_path = os.path.join(os.path.dirname(__file__), "handler.py")
        with open(handler_path, 'r') as f:
            zf.writestr("handler.py", f.read())

    buffer.seek(0)
    return buffer.read()


def get_or_create_role(iam_client, account_id):
    """Get or create the Lambda execution role."""
    role_name = f"{FUNCTION_NAME}-role"
    role_arn = f"arn:aws:iam::{account_id}:role/{role_name}"

    try:
        iam_client.get_role(RoleName=role_name)
        print(f"✓ Using existing role: {role_name}")
    except iam_client.exceptions.NoSuchEntityException:
        print(f"Creating IAM role: {role_name}")
        iam_client.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(ASSUME_ROLE_POLICY),
            Description="Lambda execution role for AgentCore proxy"
        )

        # Attach inline policy
        iam_client.put_role_policy(
            RoleName=role_name,
            PolicyName="agentcore-invoke-policy",
            PolicyDocument=json.dumps(get_lambda_policy(AGENT_ARN))
        )

        # Wait for role to propagate
        print("   Waiting for role to propagate...")
        time.sleep(10)
        print(f"✓ Created role: {role_name}")

    return role_arn


def create_or_update_lambda(lambda_client, role_arn, zip_content):
    """Create or update the Lambda function."""
    try:
        # Try to update existing function
        lambda_client.update_function_code(
            FunctionName=FUNCTION_NAME,
            ZipFile=zip_content
        )
        print(f"✓ Updated Lambda function: {FUNCTION_NAME}")

        # Update environment variables
        lambda_client.update_function_configuration(
            FunctionName=FUNCTION_NAME,
            Environment={
                "Variables": {
                    "AGENT_ARN": AGENT_ARN,
                    "AGENT_REGION": REGION
                }
            }
        )

    except lambda_client.exceptions.ResourceNotFoundException:
        # Create new function
        print(f"Creating Lambda function: {FUNCTION_NAME}")
        lambda_client.create_function(
            FunctionName=FUNCTION_NAME,
            Runtime="python3.12",
            Role=role_arn,
            Handler="handler.lambda_handler",
            Code={"ZipFile": zip_content},
            Timeout=60,
            MemorySize=256,
            Environment={
                "Variables": {
                    "AGENT_ARN": AGENT_ARN,
                    "AGENT_REGION": REGION
                }
            },
            Architectures=["arm64"]
        )
        print(f"✓ Created Lambda function: {FUNCTION_NAME}")

        # Wait for function to be active
        print("   Waiting for function to be active...")
        waiter = lambda_client.get_waiter('function_active')
        waiter.wait(FunctionName=FUNCTION_NAME)

    # Get function ARN
    response = lambda_client.get_function(FunctionName=FUNCTION_NAME)
    return response["Configuration"]["FunctionArn"]


def create_or_update_api_gateway(apigateway_client, lambda_arn, account_id):
    """Create or update the HTTP API Gateway."""

    # Check if API already exists
    apis = apigateway_client.get_apis()
    existing_api = next(
        (api for api in apis.get("Items", []) if api["Name"] == API_NAME),
        None
    )

    if existing_api:
        api_id = existing_api["ApiId"]
        api_endpoint = existing_api["ApiEndpoint"]
        print(f"✓ Using existing API Gateway: {api_id}")
    else:
        # Create new HTTP API
        print(f"Creating API Gateway: {API_NAME}")
        response = apigateway_client.create_api(
            Name=API_NAME,
            ProtocolType="HTTP",
            CorsConfiguration={
                "AllowOrigins": ["https://weijian.ai"],
                "AllowMethods": ["POST", "OPTIONS"],
                "AllowHeaders": ["Content-Type", "Authorization"],
                "MaxAge": 86400
            }
        )
        api_id = response["ApiId"]
        api_endpoint = response["ApiEndpoint"]
        print(f"✓ Created API Gateway: {api_id}")

    # Create or update Lambda integration
    integrations = apigateway_client.get_integrations(ApiId=api_id)
    existing_integration = next(
        (i for i in integrations.get("Items", []) if i.get("IntegrationUri") == lambda_arn),
        None
    )

    if existing_integration:
        integration_id = existing_integration["IntegrationId"]
        print(f"✓ Using existing integration: {integration_id}")
    else:
        response = apigateway_client.create_integration(
            ApiId=api_id,
            IntegrationType="AWS_PROXY",
            IntegrationUri=lambda_arn,
            PayloadFormatVersion="2.0"
        )
        integration_id = response["IntegrationId"]
        print(f"✓ Created integration: {integration_id}")

    # Create POST route
    routes = apigateway_client.get_routes(ApiId=api_id)
    post_route = next(
        (r for r in routes.get("Items", []) if r["RouteKey"] == "POST /chat"),
        None
    )

    if not post_route:
        apigateway_client.create_route(
            ApiId=api_id,
            RouteKey="POST /chat",
            Target=f"integrations/{integration_id}"
        )
        print("✓ Created POST /chat route")

    # Create/update default stage
    try:
        apigateway_client.create_stage(
            ApiId=api_id,
            StageName="$default",
            AutoDeploy=True
        )
        print("✓ Created default stage")
    except apigateway_client.exceptions.ConflictException:
        pass  # Stage already exists

    # Add Lambda permission for API Gateway
    lambda_client = boto3.client("lambda", region_name=REGION)
    try:
        lambda_client.add_permission(
            FunctionName=FUNCTION_NAME,
            StatementId=f"apigateway-{api_id}",
            Action="lambda:InvokeFunction",
            Principal="apigateway.amazonaws.com",
            SourceArn=f"arn:aws:execute-api:{REGION}:{account_id}:{api_id}/*"
        )
        print("✓ Added API Gateway permission to Lambda")
    except lambda_client.exceptions.ResourceConflictException:
        pass  # Permission already exists

    return api_endpoint


def main():
    print("🚀 Deploying Lambda + API Gateway for AgentCore agent\n")

    # Initialize clients
    sts_client = boto3.client("sts", region_name=REGION)
    iam_client = boto3.client("iam", region_name=REGION)
    lambda_client = boto3.client("lambda", region_name=REGION)
    apigateway_client = boto3.client("apigatewayv2", region_name=REGION)

    # Get account ID
    account_id = sts_client.get_caller_identity()["Account"]
    print(f"Account: {account_id}")
    print(f"Region: {REGION}\n")

    # Create deployment package
    zip_content = create_deployment_package()

    # Create/get IAM role
    role_arn = get_or_create_role(iam_client, account_id)

    # Create/update Lambda
    lambda_arn = create_or_update_lambda(lambda_client, role_arn, zip_content)

    # Create/update API Gateway
    api_endpoint = create_or_update_api_gateway(apigateway_client, lambda_arn, account_id)

    # Print results
    chat_url = f"{api_endpoint}/chat"

    print("\n" + "=" * 60)
    print("✅ Deployment complete!")
    print("=" * 60)
    print(f"\n🌐 Your agent endpoint: {chat_url}")
    print("\n📝 Test with curl:")
    print(f'''
curl -X POST {chat_url} \\
  -H "Content-Type: application/json" \\
  -d '{{"prompt": "What mental models do you know about?"}}'
''')

    print("\n💡 Or open chat.html in your browser and enter the endpoint URL")

    return chat_url


if __name__ == "__main__":
    main()


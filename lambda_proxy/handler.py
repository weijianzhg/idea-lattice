"""
Lambda function that proxies requests to the Bedrock AgentCore agent.
This allows a frontend to call the agent via API Gateway.
"""

import json
import os
import boto3

# Get configuration from environment variables (set by Lambda deployment)
AGENT_ARN = os.environ.get("AGENT_ARN")
REGION = os.environ.get("AGENT_REGION", "eu-west-1")

if not AGENT_ARN:
    raise ValueError("AGENT_ARN environment variable is required")


def lambda_handler(event, context):
    """
    Handle incoming API Gateway requests and forward to AgentCore.

    Expected request body:
    {
        "prompt": "What mental models do you know about?",
        "session_id": "optional-session-id"
    }
    """
    # Parse request body
    try:
        if isinstance(event.get("body"), str):
            body = json.loads(event["body"])
        else:
            body = event.get("body", {}) or {}
    except json.JSONDecodeError:
        return {
            "statusCode": 400,
            "headers": cors_headers(),
            "body": json.dumps({"error": "Invalid JSON in request body"})
        }

    prompt = body.get("prompt", "Hello")
    session_id = body.get("session_id") or generate_session_id()

    # Call AgentCore
    try:
        client = boto3.client("bedrock-agentcore", region_name=REGION)

        payload = json.dumps({"prompt": prompt})

        response = client.invoke_agent_runtime(
            agentRuntimeArn=AGENT_ARN,
            runtimeSessionId=session_id,
            payload=payload.encode("utf-8"),
            qualifier="DEFAULT"
        )

        # Read the streaming response
        response_body = response["response"].read().decode("utf-8")

        # Parse streaming response to extract text
        text_parts = []
        for line in response_body.split("\n"):
            line = line.strip()
            if line.startswith("data: "):
                try:
                    data = json.loads(line[6:])
                    # Extract text from contentBlockDelta events
                    if isinstance(data, dict):
                        event = data.get("event", {})
                        delta = event.get("contentBlockDelta", {}).get("delta", {})
                        if "text" in delta:
                            text_parts.append(delta["text"])
                except json.JSONDecodeError:
                    pass

        # Combine all text parts
        full_text = "".join(text_parts) if text_parts else response_body
        result = {"message": full_text}

        return {
            "statusCode": 200,
            "headers": cors_headers(),
            "body": json.dumps({
                "response": result,
                "session_id": session_id
            })
        }

    except Exception as e:
        print(f"Error invoking agent: {e}")
        return {
            "statusCode": 500,
            "headers": cors_headers(),
            "body": json.dumps({"error": str(e)})
        }


def cors_headers():
    """Return CORS headers for browser access."""
    return {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type,Authorization",
        "Access-Control-Allow-Methods": "POST,OPTIONS"
    }


def generate_session_id():
    """Generate a unique session ID (must be 33+ chars for AgentCore)."""
    import uuid
    return str(uuid.uuid4()) + "-" + str(uuid.uuid4())[:8]


def lambda_handler_options(event, context):
    """Handle OPTIONS preflight requests for CORS."""
    return {
        "statusCode": 200,
        "headers": cors_headers(),
        "body": ""
    }


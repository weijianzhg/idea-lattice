"""
AgentCore SDK-style agent for deployment with Starter Toolkit.

Usage:
    # Configure
    agentcore configure --entrypoint agent_sdk.py

    # Deploy to AWS
    agentcore launch

    # Test
    agentcore invoke '{"prompt": "Hello!"}'
"""

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent

app = BedrockAgentCoreApp()
agent = Agent()


@app.entrypoint
async def invoke(payload: dict):
    """Process user input and stream the response."""
    user_message = payload.get("prompt", "Hello")

    async for event in agent.stream_async(user_message):
        yield event


if __name__ == "__main__":
    app.run()


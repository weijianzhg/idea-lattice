"""
AgentCore SDK-style agent for deployment with Starter Toolkit.

This agent can search and answer questions about the Latticework of Mental Models
knowledge graph using tools that query the RSS feed and crosslinks data.

Usage:
    # Configure
    agentcore configure --entrypoint agent_sdk.py

    # Deploy to AWS
    agentcore launch

    # Test
    agentcore invoke '{"prompt": "What mental models do you know about?"}'
"""

import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from bedrock_agentcore.runtime import BedrockAgentCoreApp
from strands import Agent, tool

# ─────────────────────────────────────────────────────────────────────────────
# Data Loading (reused from generate_graph.py)
# ─────────────────────────────────────────────────────────────────────────────

RSS_PATH = Path(__file__).parent / "latticeworkofmodels.substack.com_feed.xml"
CROSSLINKS_PATH = Path(__file__).parent / "crosslinks.json"


def parse_date(date_str: str) -> str:
    """Convert RSS date format to readable format."""
    try:
        dt = datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %Z")
        return dt.strftime("%b %d, %Y")
    except ValueError:
        return date_str


def split_title(title: str) -> tuple[str, str]:
    """Split title into (model, domain)."""
    m = re.match(r"^(.*?)\s*[\-–—]\s*(.+)$", title.strip())
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return title.strip(), "Misc"


def slugify(name: str) -> str:
    """Convert a name to a URL-friendly slug."""
    s = name.lower().strip()
    s = re.sub(r"[''']", "", s)
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s or "untitled"


def load_posts() -> list[dict]:
    """Load and parse all posts from the RSS feed."""
    if not RSS_PATH.exists():
        return []

    tree = ET.parse(RSS_PATH)
    root = tree.getroot()
    items = root.findall(".//item")

    posts = []
    for item in items:
        title = item.findtext("title") or ""
        link = item.findtext("link") or ""
        pub_date = item.findtext("pubDate") or ""
        description = item.findtext("description") or ""

        description = html.unescape(description)
        # Keep more content for the agent (not truncated like in the graph)
        if len(description) > 500:
            description = description[:497] + "..."

        model, domain = split_title(title)

        posts.append({
            "id": slugify(model),
            "title": model,
            "domain": domain.strip(),
            "link": link,
            "pubDate": parse_date(pub_date),
            "description": description,
        })

    return posts


def load_crosslinks() -> list[dict]:
    """Load cross-links that show relationships between mental models."""
    if not CROSSLINKS_PATH.exists():
        return []

    with open(CROSSLINKS_PATH) as f:
        data = json.load(f)

    return data.get("crosslinks", [])


# Load data at module level (once on startup)
POSTS = load_posts()
CROSSLINKS = load_crosslinks()

# Build lookup structures
POSTS_BY_ID = {p["id"]: p for p in POSTS}
POSTS_BY_DOMAIN = {}
for p in POSTS:
    POSTS_BY_DOMAIN.setdefault(p["domain"], []).append(p)


# ─────────────────────────────────────────────────────────────────────────────
# Agent Tools
# ─────────────────────────────────────────────────────────────────────────────


@tool
def list_mental_models() -> str:
    """
    List all mental models in the knowledge graph, grouped by domain.

    Returns:
        A formatted list of all mental models organized by their domain/category.
    """
    if not POSTS:
        return "No mental models found. The RSS feed may not be loaded."

    result = []
    for domain, posts in sorted(POSTS_BY_DOMAIN.items()):
        result.append(f"\n## {domain}")
        for p in posts:
            result.append(f"- {p['title']}")

    return f"Found {len(POSTS)} mental models across {len(POSTS_BY_DOMAIN)} domains:\n" + "\n".join(result)


@tool
def search_mental_models(query: str) -> str:
    """
    Search for mental models matching a query. Searches titles, domains, and descriptions.

    Args:
        query: The search term to find relevant mental models.

    Returns:
        Information about matching mental models including title, domain, description, and link.
    """
    if not POSTS:
        return "No mental models found. The RSS feed may not be loaded."

    query_lower = query.lower()
    matches = []

    for p in POSTS:
        score = 0
        # Title match (highest weight)
        if query_lower in p["title"].lower():
            score += 10
        # Domain match
        if query_lower in p["domain"].lower():
            score += 5
        # Description match
        if query_lower in p["description"].lower():
            score += 3
        # ID/slug match
        if query_lower in p["id"]:
            score += 2

        if score > 0:
            matches.append((score, p))

    if not matches:
        return f"No mental models found matching '{query}'. Try listing all models with list_mental_models."

    # Sort by score descending
    matches.sort(key=lambda x: x[0], reverse=True)

    result = [f"Found {len(matches)} mental model(s) matching '{query}':\n"]
    for _, p in matches[:5]:  # Top 5 results
        result.append(f"### {p['title']} ({p['domain']})")
        result.append(f"{p['description']}")
        result.append(f"Published: {p['pubDate']}")
        result.append(f"Link: {p['link']}\n")

    return "\n".join(result)


@tool
def get_mental_model(model_name: str) -> str:
    """
    Get detailed information about a specific mental model.

    Args:
        model_name: The name or slug of the mental model to look up.

    Returns:
        Detailed information about the mental model including related models.
    """
    if not POSTS:
        return "No mental models found. The RSS feed may not be loaded."

    # Try exact slug match first
    slug = slugify(model_name)
    post = POSTS_BY_ID.get(slug)

    # If not found, try fuzzy matching
    if not post:
        for p in POSTS:
            if model_name.lower() in p["title"].lower():
                post = p
                break

    if not post:
        return f"Mental model '{model_name}' not found. Use list_mental_models to see available models."

    # Find related models via crosslinks
    related = []
    for cl in CROSSLINKS:
        if cl["source"] == post["id"]:
            target = POSTS_BY_ID.get(cl["target"])
            if target:
                reason = cl.get("reason", "related concept")
                related.append(f"- {target['title']}: {reason}")
        elif cl["target"] == post["id"]:
            source = POSTS_BY_ID.get(cl["source"])
            if source:
                reason = cl.get("reason", "related concept")
                related.append(f"- {source['title']}: {reason}")

    # Find other models in same domain
    same_domain = [p["title"] for p in POSTS_BY_DOMAIN.get(post["domain"], []) if p["id"] != post["id"]]

    result = [
        f"# {post['title']}",
        f"**Domain:** {post['domain']}",
        f"**Published:** {post['pubDate']}",
        f"\n## Description\n{post['description']}",
        f"\n**Read more:** {post['link']}",
    ]

    if related:
        result.append(f"\n## Related Mental Models (Cross-links)")
        result.extend(related)

    if same_domain:
        result.append(f"\n## Other {post['domain']} Models")
        result.append(", ".join(same_domain[:5]))

    return "\n".join(result)


@tool
def get_model_connections(model_name: str) -> str:
    """
    Get the connections/relationships for a mental model in the knowledge graph.

    Args:
        model_name: The name or slug of the mental model.

    Returns:
        All connections this model has to other models, with explanations.
    """
    slug = slugify(model_name)
    post = POSTS_BY_ID.get(slug)

    if not post:
        for p in POSTS:
            if model_name.lower() in p["title"].lower():
                post = p
                break

    if not post:
        return f"Mental model '{model_name}' not found."

    connections = []
    for cl in CROSSLINKS:
        if cl["source"] == post["id"]:
            target = POSTS_BY_ID.get(cl["target"])
            if target:
                connections.append({
                    "model": target["title"],
                    "domain": target["domain"],
                    "reason": cl.get("reason", "conceptually related"),
                    "direction": "outgoing",
                })
        elif cl["target"] == post["id"]:
            source = POSTS_BY_ID.get(cl["source"])
            if source:
                connections.append({
                    "model": source["title"],
                    "domain": source["domain"],
                    "reason": cl.get("reason", "conceptually related"),
                    "direction": "incoming",
                })

    if not connections:
        return f"'{post['title']}' has no explicit cross-links to other models, but it belongs to the {post['domain']} domain."

    result = [f"Connections for '{post['title']}':\n"]
    for conn in connections:
        arrow = "→" if conn["direction"] == "outgoing" else "←"
        result.append(f"{arrow} **{conn['model']}** ({conn['domain']})")
        result.append(f"  _{conn['reason']}_\n")

    return "\n".join(result)


# ─────────────────────────────────────────────────────────────────────────────
# Agent Setup
# ─────────────────────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert on mental models and the "Latticework of Mental Models" knowledge base.

You have access to tools that let you search and explore a collection of mental models from various domains
(Economics, Psychology, Mathematics, Logic, etc.). Each mental model is a concept or framework that helps
understand how the world works.

When users ask about mental models:
1. Use your tools to find relevant information
2. Explain concepts clearly and provide examples
3. Show connections between related models
4. Always include links to the original articles when available

Be helpful, educational, and encourage users to explore the interconnections between different mental models."""

app = BedrockAgentCoreApp()
agent = Agent(
    system_prompt=SYSTEM_PROMPT,
    tools=[list_mental_models, search_mental_models, get_mental_model, get_model_connections],
)


@app.entrypoint
async def invoke(payload: dict):
    """Process user input and stream the response."""
    user_message = payload.get("prompt", "Hello")

    async for event in agent.stream_async(user_message):
        yield event


if __name__ == "__main__":
    app.run()

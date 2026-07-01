"""A small FastMCP server for MCP Inspector experiments."""

from fastmcp import FastMCP


mcp = FastMCP("Research Demo")


@mcp.tool
def add_numbers(a: int, b: int) -> int:
    """Add two integers and return the result."""
    return a + b


@mcp.resource("research://topics/{topic}")
def research_topic(topic: str) -> str:
    """Return a short read-only research note for a topic."""
    return f"Research note: {topic} is a useful topic for an MCP demonstration."


@mcp.prompt
def summarize_topic(topic: str) -> str:
    """Create a prompt for summarizing a research topic."""
    return f"请用三句话总结主题“{topic}”，并列出两个需要进一步查证的事实。"


if __name__ == "__main__":
    mcp.run()

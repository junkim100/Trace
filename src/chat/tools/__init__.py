"""
Tool Abstraction Layer for Trace

Provides a unified interface for tools that can be:
1. Local (existing actions)
2. MCP-based (future web browsing, external APIs)

This abstraction enables the ReAct loop and agentic pipeline to
work with both local and remote tools transparently.
"""

from src.chat.tools.base import Tool, ToolResult
from src.chat.tools.registry import ToolRegistry, get_tool_registry

__all__ = ["Tool", "ToolResult", "ToolRegistry", "get_tool_registry"]

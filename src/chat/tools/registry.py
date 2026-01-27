"""
Tool Registry for Trace

Manages registration and discovery of all available tools,
both local actions and MCP-based remote tools.
"""

import logging
from typing import Any

from src.chat.tools.base import LocalTool, MCPTool, MCPToolSpec, Tool

logger = logging.getLogger(__name__)


# Standard tool definitions for wrapping existing actions
STANDARD_TOOLS = {
    "semantic_search": {
        "description": "Search for notes using semantic similarity. Best for finding information about topics, activities, or general queries.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query string",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results to return",
                    "default": 10,
                },
                "time_filter": {
                    "type": "string",
                    "description": "Time filter like 'today', 'yesterday', 'last week'",
                },
            },
            "required": ["query"],
        },
    },
    "entity_search": {
        "description": "Search for notes mentioning a specific entity (app, person, topic).",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_name": {
                    "type": "string",
                    "description": "Name of the entity to search for",
                },
                "entity_type": {
                    "type": "string",
                    "description": "Type filter (app, person, topic)",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results",
                    "default": 10,
                },
            },
            "required": ["entity_name"],
        },
    },
    "find_last_entity_occurrence": {
        "description": "Find when an entity was last used or seen. Use for 'When did I last...' queries.",
        "parameters": {
            "type": "object",
            "properties": {
                "entity_name": {
                    "type": "string",
                    "description": "Name of the entity to find",
                },
                "entity_type": {
                    "type": "string",
                    "description": "Optional type filter",
                },
            },
            "required": ["entity_name"],
        },
    },
    "time_range_notes": {
        "description": "Get all notes within a specific time range.",
        "parameters": {
            "type": "object",
            "properties": {
                "time_filter": {
                    "type": "string",
                    "description": "Time filter description (e.g., 'yesterday', 'last week')",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results",
                    "default": 20,
                },
            },
            "required": ["time_filter"],
        },
    },
    "aggregates_query": {
        "description": "Get aggregate statistics (most used apps, top topics, etc.).",
        "parameters": {
            "type": "object",
            "properties": {
                "key_type": {
                    "type": "string",
                    "enum": ["app", "domain", "topic", "artist", "category"],
                    "description": "Type of aggregate",
                },
                "time_filter": {
                    "type": "string",
                    "description": "Optional time filter",
                },
                "limit": {
                    "type": "integer",
                    "description": "Maximum results",
                    "default": 10,
                },
            },
            "required": ["key_type"],
        },
    },
    "hierarchical_search": {
        "description": "Two-stage search: daily summaries first, then hourly details. Good for broad exploration.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query",
                },
                "time_filter": {
                    "type": "string",
                    "description": "Optional time filter",
                },
                "max_days": {
                    "type": "integer",
                    "description": "Maximum days to return",
                    "default": 5,
                },
            },
            "required": ["query"],
        },
    },
}


class ToolRegistry:
    """
    Registry of all available tools.

    Manages:
    - Local tools (wrapped actions)
    - MCP tools (from remote servers)
    - Tool discovery for LLM prompts
    """

    def __init__(
        self,
        db_path: str | None = None,
        api_key: str | None = None,
    ):
        """
        Initialize the tool registry.

        Args:
            db_path: Database path for local tools
            api_key: API key for tools that need it
        """
        self._db_path = db_path
        self._api_key = api_key
        self._tools: dict[str, Tool] = {}
        self._mcp_servers: dict[str, Any] = {}

        # Register standard local tools
        self._register_standard_tools()

    def _register_standard_tools(self) -> None:
        """Register all standard local tools."""
        for action_name, spec in STANDARD_TOOLS.items():
            tool = LocalTool(
                action_name=action_name,
                description=spec["description"],
                parameters=spec["parameters"],
                db_path=self._db_path,
                api_key=self._api_key,
            )
            self._tools[action_name] = tool
            logger.debug(f"Registered local tool: {action_name}")

    def register(self, tool: Tool) -> None:
        """
        Register a tool.

        Args:
            tool: Tool instance to register
        """
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    def register_mcp_server(
        self,
        server_name: str,
        client: Any,
        tools: list[MCPToolSpec],
    ) -> None:
        """
        Register an MCP server and its tools.

        Args:
            server_name: Name of the MCP server
            client: MCP client instance
            tools: List of tool specifications from the server
        """
        self._mcp_servers[server_name] = client

        for spec in tools:
            tool = MCPTool(spec, client)
            self._tools[tool.name] = tool
            logger.info(f"Registered MCP tool: {tool.name}")

    def get(self, name: str) -> Tool | None:
        """
        Get a tool by name.

        Args:
            name: Tool name

        Returns:
            Tool instance or None
        """
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        """Get list of all registered tool names."""
        return list(self._tools.keys())

    def get_tool_schemas(self) -> list[dict]:
        """
        Get OpenAI function schemas for all tools.

        Returns:
            List of function schemas for OpenAI API
        """
        return [tool.to_schema() for tool in self._tools.values()]

    def get_tool_descriptions(self) -> str:
        """
        Get formatted tool descriptions for LLM prompts.

        Returns:
            Formatted string describing all available tools
        """
        lines = []
        for name, tool in self._tools.items():
            params = tool.parameters.get("properties", {})
            param_str = ", ".join(
                f"{k}: {v.get('description', 'no description')}" for k, v in params.items()
            )
            lines.append(f"- {name}: {tool.description}")
            if param_str:
                lines.append(f"  Parameters: {{{param_str}}}")
        return "\n".join(lines)

    async def execute(self, tool_name: str, params: dict[str, Any]) -> Any:
        """
        Execute a tool by name.

        Args:
            tool_name: Name of the tool to execute
            params: Tool parameters

        Returns:
            ToolResult from execution
        """
        tool = self.get(tool_name)
        if tool is None:
            from src.chat.tools.base import ToolResult

            return ToolResult(
                success=False,
                error=f"Unknown tool: {tool_name}",
            )

        return await tool.execute(params)


# Global registry instance
_registry: ToolRegistry | None = None


def get_tool_registry(
    db_path: str | None = None,
    api_key: str | None = None,
) -> ToolRegistry:
    """
    Get the global tool registry instance.

    Args:
        db_path: Database path
        api_key: API key

    Returns:
        ToolRegistry instance
    """
    global _registry
    if _registry is None or db_path or api_key:
        _registry = ToolRegistry(db_path=db_path, api_key=api_key)
    return _registry


if __name__ == "__main__":
    import fire

    def list_tools():
        """List all registered tools."""
        registry = get_tool_registry()
        return registry.list_tools()

    def describe():
        """Get tool descriptions."""
        registry = get_tool_registry()
        print(registry.get_tool_descriptions())

    def schemas():
        """Get tool schemas for OpenAI."""
        registry = get_tool_registry()
        return registry.get_tool_schemas()

    fire.Fire({"list": list_tools, "describe": describe, "schemas": schemas})

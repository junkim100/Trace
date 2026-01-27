"""
Base Tool Interface for Trace

Defines the abstract interface that all tools must implement,
whether they are local actions or MCP-based remote tools.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Result of a tool execution."""

    success: bool
    data: Any = None
    error: str | None = None
    execution_time_ms: float = 0.0
    # For MCP tools, track the source
    source: str = "local"

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "data": self.data,
            "error": self.error,
            "execution_time_ms": self.execution_time_ms,
            "source": self.source,
        }


class Tool(ABC):
    """
    Abstract base class for all tools.

    Tools can be:
    - Local: Existing retrieval actions wrapped as tools
    - MCP: Remote tools from MCP servers (future)
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique tool name."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Human-readable description for LLM prompts."""
        pass

    @property
    @abstractmethod
    def parameters(self) -> dict:
        """JSON Schema for tool parameters."""
        pass

    @abstractmethod
    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """
        Execute the tool with given parameters.

        Args:
            params: Tool-specific parameters

        Returns:
            ToolResult with success status and data
        """
        pass

    def execute_sync(self, params: dict[str, Any]) -> ToolResult:
        """Synchronous wrapper for execute()."""
        import asyncio

        return asyncio.run(self.execute(params))

    def to_schema(self) -> dict:
        """
        Convert tool to OpenAI function schema.

        Returns:
            Dict suitable for OpenAI function calling
        """
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }


class LocalTool(Tool):
    """
    Wrapper to convert existing actions to the Tool interface.

    This allows seamless integration of existing retrieval
    actions with the new tool abstraction.
    """

    def __init__(
        self,
        action_name: str,
        description: str,
        parameters: dict,
        db_path: str | None = None,
        api_key: str | None = None,
    ):
        """
        Initialize a local tool wrapper.

        Args:
            action_name: Name of the action to wrap
            description: Tool description
            parameters: JSON Schema for parameters
            db_path: Database path
            api_key: API key for LLM calls
        """
        self._action_name = action_name
        self._description = description
        self._parameters = parameters
        self._db_path = db_path
        self._api_key = api_key

    @property
    def name(self) -> str:
        return self._action_name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> dict:
        return self._parameters

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Execute the wrapped action."""
        import time

        from src.chat.agentic.actions.base import ActionRegistry, ExecutionContext

        start_time = time.time()

        try:
            # Get the action
            action = ActionRegistry.create(
                self._action_name,
                db_path=self._db_path,
                api_key=self._api_key,
            )

            if action is None:
                return ToolResult(
                    success=False,
                    error=f"Unknown action: {self._action_name}",
                    execution_time_ms=(time.time() - start_time) * 1000,
                )

            # Execute with a context
            context = ExecutionContext(
                db_path=self._db_path,
                api_key=self._api_key,
            )

            # Add step_id for tracking
            params["step_id"] = f"tool_{self._action_name}"

            result = action.execute(params, context)

            return ToolResult(
                success=result.success,
                data=result.result,
                error=result.error,
                execution_time_ms=(time.time() - start_time) * 1000,
                source="local",
            )

        except Exception as e:
            logger.error(f"Tool execution failed: {e}")
            return ToolResult(
                success=False,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
                source="local",
            )


@dataclass
class MCPToolSpec:
    """Specification for an MCP-based tool."""

    server_name: str
    tool_name: str
    description: str
    input_schema: dict = field(default_factory=dict)


class MCPTool(Tool):
    """
    Wrapper for MCP server tools.

    Enables future integration with MCP servers for:
    - Web browsing
    - External APIs
    - File system access
    - etc.
    """

    def __init__(self, spec: MCPToolSpec, mcp_client: Any = None):
        """
        Initialize an MCP tool wrapper.

        Args:
            spec: Tool specification from MCP server
            mcp_client: MCP client instance (to be implemented)
        """
        self._spec = spec
        self._client = mcp_client

    @property
    def name(self) -> str:
        return f"{self._spec.server_name}:{self._spec.tool_name}"

    @property
    def description(self) -> str:
        return self._spec.description

    @property
    def parameters(self) -> dict:
        return self._spec.input_schema

    async def execute(self, params: dict[str, Any]) -> ToolResult:
        """Execute the MCP tool."""
        import time

        start_time = time.time()

        if self._client is None:
            return ToolResult(
                success=False,
                error="MCP client not configured",
                execution_time_ms=(time.time() - start_time) * 1000,
                source=f"mcp:{self._spec.server_name}",
            )

        try:
            # Future: Call MCP server
            # result = await self._client.call_tool(
            #     self._spec.server_name,
            #     self._spec.tool_name,
            #     params
            # )
            return ToolResult(
                success=False,
                error="MCP integration not yet implemented",
                execution_time_ms=(time.time() - start_time) * 1000,
                source=f"mcp:{self._spec.server_name}",
            )

        except Exception as e:
            logger.error(f"MCP tool execution failed: {e}")
            return ToolResult(
                success=False,
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000,
                source=f"mcp:{self._spec.server_name}",
            )

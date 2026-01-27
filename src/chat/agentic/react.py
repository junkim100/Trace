"""
ReAct (Reasoning + Acting) Loop for Multi-Hop Queries

Implements an iterative reasoning loop that allows the agent to:
1. Think about what it knows and needs to find out
2. Take actions (search, lookup) to gather information
3. Observe results and decide next steps
4. Synthesize a final answer

Based on the ReAct pattern: https://arxiv.org/abs/2210.03629
"""

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from src.chat.agentic.actions.base import ActionRegistry, ExecutionContext
from src.chat.agentic.schemas import StepResult
from src.chat.clarification import ClarificationRequest
from src.core.paths import DB_PATH

logger = logging.getLogger(__name__)

# Model for ReAct reasoning
REACT_MODEL = "gpt-4o"

REACT_PROMPT = """You are an AI assistant analyzing a user's query about their digital activity.
You have access to tools to search and retrieve information from the user's activity history.

Available tools:
{tools}

User's query: {query}

Current observations from previous steps:
{observations}

Think step by step:
1. What do I know so far from the observations?
2. What do I still need to find out to answer the query?
3. What action should I take next (or should I finish)?

Respond with ONLY valid JSON (no markdown):
{{
    "thought": "Your step-by-step reasoning about the current state and next action",
    "action": "tool_name OR FINISH",
    "action_input": {{"param": "value"}} OR null (if FINISH),
    "final_answer": "Your complete answer to the user (ONLY if action is FINISH)"
}}

IMPORTANT:
- Only use FINISH when you have enough information to answer the query
- If you need more information, choose an appropriate tool
- Be concise but thorough in your reasoning
"""


@dataclass
class ReActStep:
    """A single step in the ReAct loop."""

    step_number: int
    thought: str
    action: str
    action_input: dict[str, Any] | None
    result: Any = None
    execution_time_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "step_number": self.step_number,
            "thought": self.thought,
            "action": self.action,
            "action_input": self.action_input,
            "result": self.result,
            "execution_time_ms": self.execution_time_ms,
        }


@dataclass
class ReActResult:
    """Result of a ReAct loop execution."""

    success: bool
    answer: str | None = None
    reasoning_trace: list[ReActStep] = field(default_factory=list)
    notes: list[dict] = field(default_factory=list)
    error: str | None = None
    needs_clarification: bool = False
    clarification: ClarificationRequest | None = None
    total_time_ms: float = 0.0

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "answer": self.answer,
            "reasoning_trace": [s.to_dict() for s in self.reasoning_trace],
            "notes_count": len(self.notes),
            "error": self.error,
            "needs_clarification": self.needs_clarification,
            "total_time_ms": self.total_time_ms,
        }


class ReActLoop:
    """
    Implements the ReAct (Reasoning + Acting) pattern for multi-hop queries.

    The loop iteratively:
    1. Reasons about current state
    2. Selects and executes an action
    3. Observes the result
    4. Repeats until it can answer or max iterations reached
    """

    MAX_ITERATIONS = 5
    ACTION_TIMEOUT_MS = 10000

    # Tools available to the ReAct agent
    AVAILABLE_TOOLS = {
        "semantic_search": {
            "description": "Search for notes using semantic similarity. Use for finding information about topics, activities, or general queries.",
            "params": {
                "query": "Search query string",
                "limit": "Maximum results (default 10)",
                "time_filter": "Optional time filter like 'today', 'last week', etc.",
            },
        },
        "entity_search": {
            "description": "Search for notes mentioning a specific entity (app, person, topic, etc.).",
            "params": {
                "entity_name": "Name of the entity to search for",
                "entity_type": "Optional type filter (app, person, topic)",
                "limit": "Maximum results (default 10)",
            },
        },
        "find_last_entity_occurrence": {
            "description": "Find when an entity was last used/seen. Use for 'When did I last...' queries.",
            "params": {
                "entity_name": "Name of the entity to find",
                "entity_type": "Optional type filter",
            },
        },
        "time_range_notes": {
            "description": "Get all notes within a specific time range.",
            "params": {
                "time_filter": "Time filter description (e.g., 'yesterday', 'last week')",
                "limit": "Maximum results (default 20)",
            },
        },
        "aggregates_query": {
            "description": "Get aggregate statistics (most used apps, top topics, etc.).",
            "params": {
                "key_type": "Type of aggregate (app, domain, topic, artist)",
                "time_filter": "Optional time filter",
                "limit": "Maximum results (default 10)",
            },
        },
    }

    def __init__(
        self,
        api_key: str | None = None,
        db_path: str | None = None,
    ):
        """
        Initialize the ReAct loop.

        Args:
            api_key: OpenAI API key
            db_path: Path to the database
        """
        self._api_key = api_key
        self._db_path = db_path or DB_PATH
        self._client: OpenAI | None = None
        self._context: ExecutionContext | None = None

    def _get_client(self) -> OpenAI:
        """Get or create the OpenAI client."""
        if self._client is None:
            self._client = OpenAI(api_key=self._api_key) if self._api_key else OpenAI()
        return self._client

    def _get_context(self) -> ExecutionContext:
        """Get or create the execution context."""
        if self._context is None:
            self._context = ExecutionContext(
                db_path=self._db_path,
                api_key=self._api_key,
            )
        return self._context

    def _format_tools(self) -> str:
        """Format available tools for the prompt."""
        lines = []
        for name, info in self.AVAILABLE_TOOLS.items():
            params_str = ", ".join(f"{k}: {v}" for k, v in info["params"].items())
            lines.append(f"- {name}: {info['description']}")
            lines.append(f"  Parameters: {{{params_str}}}")
        return "\n".join(lines)

    def _format_observations(self, steps: list[ReActStep]) -> str:
        """Format previous observations for the prompt."""
        if not steps:
            return "No observations yet."

        lines = []
        for step in steps:
            lines.append(f"Step {step.step_number}:")
            lines.append(f"  Thought: {step.thought}")
            lines.append(f"  Action: {step.action}")
            if step.action_input:
                lines.append(f"  Input: {json.dumps(step.action_input)}")
            if step.result:
                # Summarize result to avoid token bloat
                result_summary = self._summarize_result(step.result)
                lines.append(f"  Result: {result_summary}")
            lines.append("")
        return "\n".join(lines)

    def _summarize_result(self, result: Any) -> str:
        """Summarize a result for the observations."""
        if isinstance(result, dict):
            if "notes" in result:
                notes = result["notes"]
                count = len(notes)
                if count == 0:
                    return "No notes found."
                summaries = [n.get("summary", "")[:100] for n in notes[:3]]
                return f"Found {count} note(s). Top results: {summaries}"
            if "found" in result:
                if result["found"]:
                    return f"Found! Last occurrence: {result.get('last_occurrence', 'unknown')}"
                return "Entity not found in records."
            if "aggregates" in result:
                aggs = result["aggregates"][:5]
                items = [f"{a['key']}: {a['value']}min" for a in aggs]
                return f"Aggregates: {', '.join(items)}"
            return json.dumps(result)[:200]
        return str(result)[:200]

    async def run(
        self,
        query: str,
        initial_context: dict[str, Any] | None = None,
    ) -> ReActResult:
        """
        Run the ReAct loop for a query.

        Args:
            query: User's query
            initial_context: Optional initial context

        Returns:
            ReActResult with answer and reasoning trace
        """
        start_time = time.time()
        steps: list[ReActStep] = []

        for i in range(self.MAX_ITERATIONS):
            step_start = time.time()

            # Get next action from LLM
            try:
                response = self._think(query, steps)
            except Exception as e:
                logger.error(f"ReAct thinking failed: {e}")
                return ReActResult(
                    success=False,
                    error=f"Reasoning failed: {e}",
                    reasoning_trace=steps,
                    notes=self._get_context().get_all_notes(),
                    total_time_ms=(time.time() - start_time) * 1000,
                )

            # Check if done
            if response["action"] == "FINISH":
                steps.append(
                    ReActStep(
                        step_number=i + 1,
                        thought=response["thought"],
                        action="FINISH",
                        action_input=None,
                        result=response.get("final_answer"),
                        execution_time_ms=(time.time() - step_start) * 1000,
                    )
                )
                return ReActResult(
                    success=True,
                    answer=response.get("final_answer", ""),
                    reasoning_trace=steps,
                    notes=self._get_context().get_all_notes(),
                    total_time_ms=(time.time() - start_time) * 1000,
                )

            # Execute action
            action_result = self._execute_action(
                response["action"],
                response.get("action_input", {}),
            )

            steps.append(
                ReActStep(
                    step_number=i + 1,
                    thought=response["thought"],
                    action=response["action"],
                    action_input=response.get("action_input"),
                    result=action_result.result if action_result.success else action_result.error,
                    execution_time_ms=(time.time() - step_start) * 1000,
                )
            )

        # Max iterations reached
        return ReActResult(
            success=False,
            error="Could not complete reasoning within iteration limit",
            reasoning_trace=steps,
            notes=self._get_context().get_all_notes(),
            total_time_ms=(time.time() - start_time) * 1000,
        )

    def run_sync(
        self,
        query: str,
        initial_context: dict[str, Any] | None = None,
    ) -> ReActResult:
        """Synchronous wrapper for run()."""
        import asyncio

        return asyncio.run(self.run(query, initial_context))

    def _think(self, query: str, steps: list[ReActStep]) -> dict[str, Any]:
        """
        Get the next action from the LLM.

        Args:
            query: User's query
            steps: Previous reasoning steps

        Returns:
            Dict with thought, action, action_input, and optionally final_answer
        """
        client = self._get_client()

        prompt = REACT_PROMPT.format(
            tools=self._format_tools(),
            query=query,
            observations=self._format_observations(steps),
        )

        response = client.chat.completions.create(
            model=REACT_MODEL,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1000,
            temperature=0.2,
        )

        content = response.choices[0].message.content or "{}"

        # Parse JSON response
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            # Try to extract JSON from response
            import re

            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                return json.loads(json_match.group())
            raise ValueError(f"Could not parse LLM response: {content[:100]}") from e

    def _execute_action(
        self,
        action_name: str,
        params: dict[str, Any],
    ) -> StepResult:
        """
        Execute an action and return the result.

        Args:
            action_name: Name of the action to execute
            params: Action parameters

        Returns:
            StepResult from the action
        """
        # Get or create action instance
        action = ActionRegistry.create(
            action_name,
            db_path=self._db_path,
            api_key=self._api_key,
        )

        if action is None:
            return StepResult(
                step_id=f"react_{action_name}",
                action=action_name,
                success=False,
                error=f"Unknown action: {action_name}",
            )

        # Add step_id to params
        params["step_id"] = f"react_{action_name}"

        # Execute with context
        context = self._get_context()
        try:
            result = action.execute(params, context)
            # Store result in context
            context.add_result(params["step_id"], result)
            return result
        except Exception as e:
            logger.error(f"Action {action_name} failed: {e}")
            return StepResult(
                step_id=params["step_id"],
                action=action_name,
                success=False,
                error=str(e),
            )


if __name__ == "__main__":
    import fire

    def run(query: str):
        """Run the ReAct loop on a query."""
        loop = ReActLoop()
        result = loop.run_sync(query)
        return result.to_dict()

    def demo():
        """Demo the ReAct loop with example queries."""
        loop = ReActLoop()

        queries = [
            "When did I last use Discord?",
            "What was I working on last Saturday while listening to music?",
            "How much time did I spend on coding this week?",
        ]

        results = []
        for query in queries:
            print(f"\n{'=' * 50}")
            print(f"Query: {query}")
            print("=" * 50)

            result = loop.run_sync(query)

            print(f"Success: {result.success}")
            print(f"Answer: {result.answer}")
            print(f"Steps: {len(result.reasoning_trace)}")
            print(f"Time: {result.total_time_ms:.0f}ms")

            results.append(
                {
                    "query": query,
                    "success": result.success,
                    "answer": result.answer,
                    "steps": len(result.reasoning_trace),
                }
            )

        return results

    fire.Fire({"run": run, "demo": demo})

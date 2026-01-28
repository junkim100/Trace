"""
Query Router with LLM Tool Calling

Uses OpenAI function calling to intelligently decide:
1. Whether to augment the query with web search
2. What type of query this is (for planning)

This replaces the pattern-based approach with semantic understanding.
"""

import json
import logging
from dataclasses import dataclass
from typing import Any

from openai import OpenAI

logger = logging.getLogger(__name__)

# Model for routing decisions (fast, capable model)
ROUTER_MODEL = "gpt-4o-mini"

# Tool definitions for the router
ROUTER_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": """Search the web for external information to augment the answer.

Use this tool when:
- The user explicitly asks to search the web, google something, or look something up online
- The query asks about current events, latest news, or recent developments
- The query asks about external facts that wouldn't be in the user's activity notes (documentation, tutorials, how-tos)
- The query references old activities and asks what has changed or evolved since then
- The query asks about something the user was learning/researching and wants current info

Do NOT use this tool when:
- The user is only asking about their own past activities
- The query is about what the user did, worked on, or experienced
- The information is purely personal (their schedule, their habits, their notes)
- A simple activity lookup from notes would answer the question""",
            "parameters": {
                "type": "object",
                "properties": {
                    "search_query": {
                        "type": "string",
                        "description": "The search query to send to the web search engine. Should be optimized for search (keywords, not a question).",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Brief explanation of why web search would help answer this query.",
                    },
                },
                "required": ["search_query", "reason"],
            },
        },
    },
]

# System prompt for the router
ROUTER_SYSTEM_PROMPT = """You are a query router for a personal activity tracker app called Trace.

Your job is to analyze user queries and decide:
1. What type of query this is
2. Whether web search would help answer it

The app has access to:
- User's activity notes (what they worked on, apps used, websites visited, etc.)
- Time-based filtering (today, yesterday, last week, etc.)
- Entity relationships (topics, people, projects they interact with)

Query types:
- SIMPLE: Basic activity lookup ("What did I do today?")
- ENTITY_TEMPORAL: Finding when something was last used ("When did I last use Discord?")
- RELATIONSHIP: How things relate ("What was I working on while listening to music?")
- COMPARISON: Comparing periods ("How has my coding time changed?")
- MEMORY_RECALL: Vague memory retrieval ("There was something about...")
- CORRELATION: Pattern finding ("Do I usually work late on Fridays?")
- WEB_AUGMENTED: Needs external info + user data ("What's new with React since I was learning it?")

IMPORTANT: Only call the search_web tool if the query would genuinely benefit from web results.
Most queries about personal activities do NOT need web search.

Respond with a JSON object:
{
    "query_type": "TYPE_NAME",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation"
}"""


@dataclass
class RoutingDecision:
    """Result of routing a query."""

    query_type: str
    confidence: float
    reasoning: str
    needs_web_search: bool = False
    web_search_query: str | None = None
    web_search_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary."""
        result = {
            "query_type": self.query_type,
            "confidence": self.confidence,
            "reasoning": self.reasoning,
            "needs_web_search": self.needs_web_search,
        }
        if self.web_search_query:
            result["web_search_query"] = self.web_search_query
        if self.web_search_reason:
            result["web_search_reason"] = self.web_search_reason
        return result


class QueryRouter:
    """
    Routes queries using LLM tool calling.

    Uses OpenAI's function calling to semantically determine:
    - Query type for planning
    - Whether web search should be used
    """

    def __init__(self, api_key: str | None = None) -> None:
        """
        Initialize the router.

        Args:
            api_key: OpenAI API key (uses env var if not provided)
        """
        self._api_key = api_key
        self._client: OpenAI | None = None

    def _get_client(self) -> OpenAI:
        """Get or create the OpenAI client."""
        if self._client is None:
            self._client = OpenAI(api_key=self._api_key) if self._api_key else OpenAI()
        return self._client

    def route(
        self,
        query: str,
        time_context: str | None = None,
        check_rate_limit: bool = True,
    ) -> RoutingDecision:
        """
        Route a query using LLM tool calling.

        Args:
            query: The user's query
            time_context: Optional time context (e.g., "today", "last week")
            check_rate_limit: Whether to check Tavily rate limit before allowing web search

        Returns:
            RoutingDecision with query type and web search decision
        """
        # Check rate limit before even asking about web search
        web_search_allowed = True
        if check_rate_limit:
            try:
                from src.core.config import can_use_tavily_auto, get_tavily_api_key

                # Check if Tavily is configured
                if not get_tavily_api_key():
                    web_search_allowed = False
                    logger.debug("Web search disabled: no Tavily API key")
                # Check rate limit
                elif not can_use_tavily_auto():
                    web_search_allowed = False
                    logger.debug("Web search disabled: rate limit threshold reached")
            except Exception as e:
                logger.debug(f"Could not check rate limit: {e}")
                web_search_allowed = False

        # Build user message
        user_message = f"Query: {query}"
        if time_context:
            user_message += f"\nTime context: {time_context}"

        try:
            client = self._get_client()

            # Only include web search tool if it's allowed
            tools = ROUTER_TOOLS if web_search_allowed else None

            response = client.chat.completions.create(
                model=ROUTER_MODEL,
                messages=[
                    {"role": "system", "content": ROUTER_SYSTEM_PROMPT},
                    {"role": "user", "content": user_message},
                ],
                tools=tools,
                tool_choice="auto" if tools else None,
                temperature=0.1,
                max_tokens=500,
            )

            message = response.choices[0].message

            # Check if the model called the web search tool
            needs_web_search = False
            web_search_query = None
            web_search_reason = None

            if message.tool_calls:
                for tool_call in message.tool_calls:
                    if tool_call.function.name == "search_web":
                        needs_web_search = True
                        try:
                            args = json.loads(tool_call.function.arguments)
                            web_search_query = args.get("search_query", query)
                            web_search_reason = args.get(
                                "reason", "LLM decided web search would help"
                            )
                        except json.JSONDecodeError:
                            web_search_query = query
                            web_search_reason = "LLM tool call"
                        break

            # Parse the text response for query type
            query_type = "simple"
            confidence = 0.7
            reasoning = "Default routing"

            content = message.content
            if content:
                try:
                    # Try to parse JSON from the content
                    # The model might include markdown code blocks
                    json_str = content
                    if "```json" in content:
                        json_str = content.split("```json")[1].split("```")[0]
                    elif "```" in content:
                        json_str = content.split("```")[1].split("```")[0]

                    data = json.loads(json_str.strip())
                    query_type = data.get("query_type", "simple").lower()
                    confidence = float(data.get("confidence", 0.7))
                    reasoning = data.get("reasoning", "LLM classification")

                    # Normalize query type
                    query_type = self._normalize_query_type(query_type)

                except (json.JSONDecodeError, IndexError, ValueError) as e:
                    logger.debug(f"Could not parse router response: {e}")
                    # Try to extract query type from text
                    query_type = self._extract_query_type_from_text(content)

            # If web search was requested, set query type to web_augmented
            if needs_web_search:
                query_type = "web_augmented"

            logger.info(
                f"Router decision: type={query_type}, web_search={needs_web_search}, "
                f"confidence={confidence:.2f}"
            )

            return RoutingDecision(
                query_type=query_type,
                confidence=confidence,
                reasoning=reasoning,
                needs_web_search=needs_web_search,
                web_search_query=web_search_query,
                web_search_reason=web_search_reason,
            )

        except Exception as e:
            logger.error(f"Router failed: {e}")
            # Fallback to simple routing
            return RoutingDecision(
                query_type="simple",
                confidence=0.5,
                reasoning=f"Fallback due to error: {e}",
                needs_web_search=False,
            )

    def _normalize_query_type(self, query_type: str) -> str:
        """Normalize query type to known values."""
        type_map = {
            "simple": "simple",
            "simple_retrieval": "simple",
            "entity_temporal": "entity_temporal",
            "relationship": "relationship",
            "comparison": "comparison",
            "memory_recall": "memory_recall",
            "correlation": "correlation",
            "web_augmented": "web_augmented",
            "multi_entity": "multi_entity",
        }
        return type_map.get(query_type.lower().replace(" ", "_"), "simple")

    def _extract_query_type_from_text(self, text: str) -> str:
        """Extract query type from text if JSON parsing fails."""
        text_lower = text.lower()
        if "web_augmented" in text_lower or "web augmented" in text_lower:
            return "web_augmented"
        elif "entity_temporal" in text_lower:
            return "entity_temporal"
        elif "relationship" in text_lower:
            return "relationship"
        elif "comparison" in text_lower:
            return "comparison"
        elif "memory_recall" in text_lower:
            return "memory_recall"
        elif "correlation" in text_lower:
            return "correlation"
        return "simple"


# Convenience function
def route_query(
    query: str,
    time_context: str | None = None,
    api_key: str | None = None,
) -> RoutingDecision:
    """
    Route a query using LLM tool calling.

    Args:
        query: The user's query
        time_context: Optional time context
        api_key: Optional OpenAI API key

    Returns:
        RoutingDecision
    """
    router = QueryRouter(api_key=api_key)
    return router.route(query, time_context)


if __name__ == "__main__":
    import fire

    def test(query: str, time_context: str | None = None):
        """Test query routing."""
        decision = route_query(query, time_context)
        return decision.to_dict()

    def demo():
        """Demo with various query types."""
        queries = [
            "What did I do today?",
            "When did I last use Discord?",
            "Search the web for the latest React documentation",
            "What's new with TypeScript since I was learning it last year?",
            "What was I working on while listening to Spotify?",
            "How has my coding time changed this month?",
            "Google the current Python version",
            "What projects have I been focusing on?",
        ]

        print("Query Routing Demo")
        print("=" * 60)

        for query in queries:
            print(f"\nQuery: {query}")
            decision = route_query(query)
            print(f"  Type: {decision.query_type}")
            print(f"  Web Search: {decision.needs_web_search}")
            if decision.web_search_query:
                print(f"  Search Query: {decision.web_search_query}")
            print(f"  Reasoning: {decision.reasoning}")

    fire.Fire({"test": test, "demo": demo})

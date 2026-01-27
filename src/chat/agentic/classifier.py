"""
Query Complexity Classifier for Agentic Pipeline

Determines if a query needs agentic (multi-step) processing or can be
handled by simpler single-pass methods. Uses a hybrid approach:
1. Fast pattern matching for obvious cases
2. LLM-assisted classification for ambiguous queries
"""

import json
import logging
import re
from typing import ClassVar

from src.chat.agentic.schemas import ClassificationResult, QueryType

logger = logging.getLogger(__name__)

# Model for classification (fast, cheap model)
CLASSIFIER_MODEL = "gpt-4o-mini"

ROUTER_PROMPT = """You are a query classifier for a personal activity tracker app.

Classify this query into exactly ONE category:

Query: "{query}"

Categories:
- SIMPLE_RETRIEVAL: Basic time-filtered activity lookup ("What did I do yesterday?", "Summary of today")
- ENTITY_TEMPORAL: Finding when something was last used/seen ("When did I last use Discord?", "How long since I talked to John?")
- RELATIONSHIP: How entities relate or co-occur ("What was I working on while listening to music?")
- COMPARISON: Comparing time periods or entities ("How has my coding time changed?")
- MEMORY_RECALL: Trying to remember something vague ("There was something about...")
- CORRELATION: Looking for patterns or habits ("Do I usually work late on Fridays?")
- MULTI_ENTITY: Questions about multiple entities ("Both X and Y")
- CLARIFICATION_NEEDED: Query is too ambiguous to process

Respond with ONLY valid JSON (no markdown):
{{"category": "CATEGORY_NAME", "confidence": 0.0-1.0, "entities": ["list", "of", "entities"], "reasoning": "brief explanation"}}
"""


class QueryClassifier:
    """
    Classifies queries by complexity to determine routing.

    Simple queries → existing ChatAPI handlers
    Complex queries → agentic planning and execution
    """

    # Pattern signals for different query types
    COMPLEXITY_SIGNALS: ClassVar[dict[QueryType, list[str]]] = {
        "entity_temporal": [
            # "When did I last use X?" patterns
            r"\bwhen\s+(?:did|was)\s+(?:i|the)\s+(?:last|most\s+recently)\s+(?:use|open|visit|see|talk|speak|meet)",
            r"\blast\s+time\s+i\s+(?:used|opened|visited|saw|talked|spoke|met|worked)",
            r"\bhow\s+long\s+(?:since|ago)\s+(?:i|we)\s+(?:used|saw|visited|talked|worked)",
            # "When was the last time..." patterns
            r"\bwhen\s+was\s+the\s+last\s+time\b",
            # "Last time I..." patterns
            r"\bthe\s+last\s+time\s+i\b",
            # "How long since..." patterns
            r"\bhow\s+long\s+(?:has\s+it\s+been\s+)?since\s+i\b",
        ],
        "relationship": [
            r"\bwhile\b.*\bwhat\b",
            r"\bwhen\b.*\bwhat\b",
            r"\bduring\b.*\bwhat\b",
            r"\balongside\b",
            r"\btogether with\b",
            r"\bat the same time\b",
            r"\blistening to\b.*\bwhile\b",
            r"\bwatching\b.*\bwhile\b",
            r"\bwhat.*\bwhen\b.*\bwas\b",
        ],
        "comparison": [
            r"\bcompare\b",
            r"\bvs\.?\b",
            r"\bversus\b",
            r"\bdifference\s+between\b",
            r"\bchanged\b.*\bover\b",
            r"\bhow\b.*\bchanged\b",
            r"\bfrom\b.*\bto\b.*\bperiod\b",
            r"\bjanuary\b.*\bvs\b",
            r"\blast\s+(?:week|month|year)\b.*\bthis\s+(?:week|month|year)\b",
        ],
        "memory_recall": [
            r"\bi\s+remember\b",
            r"\bthere\s+was\b.*\babout\b",
            r"\bsomething\s+about\b",
            r"\bwhat\s+was\s+it\b",
            r"\bwhat\s+did\s+i\s+learn\b",
            r"\bcan't\s+recall\b",
            r"\btrying\s+to\s+remember\b",
            r"\bwhat\s+was\s+the\b.*\bthat\b",
        ],
        "correlation": [
            r"\bpattern\b",
            r"\busually\b",
            r"\btend\s+to\b",
            r"\bafter\b.*\bdo\s+i\b",
            r"\bbefore\b.*\bdo\s+i\b",
            r"\btypically\b",
            r"\bwhat\s+do\s+i\s+(?:usually|typically)\b",
            r"\bis\s+there\s+a\s+(?:pattern|correlation)\b",
            r"\bhow\s+often\b",
        ],
        "web_augmented": [
            # Explicit latest/current info requests
            r"\blatest\b",
            r"\bcurrent\b.*\b(?:news|events|developments|version|release)\b",
            r"\brecent\s+(?:news|updates|changes)\b",
            r"\bsince\s+then\b",
            r"\bdevelopments\b",
            r"\bwhat\s+(?:is|are)\s+the\s+(?:latest|current|new)\b",
            r"\bwhat\s+happened\b.*\bworld\b",
            r"\bconnect\b.*\bwith\s+current\b",
            # Timeline/evolution queries
            r"\bhow\s+(?:has|have|did)\s+.+\s+(?:changed|evolved|progressed)\b",
            r"\bwhat\s+(?:happened|changed)\s+(?:since|after|with)\b",
            r"\bhistory\s+of\b",
            r"\btimeline\s+of\b",
            # External context queries
            r"\b(?:official\s+)?(?:documentation|docs)\s+(?:for|about|on)\b",
            r"\b(?:compare|comparison)\s+(?:with|to|between)\b.*(?:now|currently|today)\b",
            # More info requests (often benefit from web)
            r"\bmore\s+(?:info|information|details|context)\s+(?:about|on)\b",
            r"\bwhat\s+(?:else|more)\s+(?:can|should)\s+(?:i|you)\s+know\b",
        ],
        "multi_entity": [
            r"\bboth\b.*\band\b",
            r"\brelationship\s+between\b",
            r"\bhow\s+are\b.*\brelated\b",
            r"\bconnection\s+between\b",
            r"\b\w+\s+and\s+\w+\s+(?:together|related)\b",
        ],
    }

    # Minimum confidence to classify as complex
    COMPLEXITY_THRESHOLD = 0.4

    # Confidence threshold for using LLM fallback
    LLM_FALLBACK_THRESHOLD = 0.6

    # Signals that indicate simple queries (override complexity)
    SIMPLE_SIGNALS: ClassVar[list[str]] = [
        r"^what\s+did\s+i\s+do\s+(?:today|yesterday|this\s+week)\??$",
        r"^(?:tell\s+me\s+)?about\s+\w+\??$",
        r"^what\s+(?:apps?|sites?|topics?)\b",
        r"^(?:most|top)\s+\w+\s+(?:apps?|sites?|topics?|artists?)\b",
        r"^summary\s+of\s+(?:today|yesterday|this\s+week)\b",
    ]

    # Map from LLM category names to our QueryType
    CATEGORY_MAP: ClassVar[dict[str, QueryType]] = {
        "SIMPLE_RETRIEVAL": "simple",
        "ENTITY_TEMPORAL": "entity_temporal",
        "RELATIONSHIP": "relationship",
        "COMPARISON": "comparison",
        "MEMORY_RECALL": "memory_recall",
        "CORRELATION": "correlation",
        "MULTI_ENTITY": "multi_entity",
        "WEB_AUGMENTED": "web_augmented",
        "CLARIFICATION_NEEDED": "simple",
    }

    def __init__(self, api_key: str | None = None, use_llm_fallback: bool = True) -> None:
        """
        Initialize the classifier with compiled regex patterns.

        Args:
            api_key: Optional OpenAI API key for LLM-assisted classification
            use_llm_fallback: Whether to use LLM for ambiguous queries
        """
        self._api_key = api_key
        self._use_llm_fallback = use_llm_fallback
        self._client = None

        self._complexity_patterns: dict[QueryType, list[re.Pattern[str]]] = {}
        for query_type, patterns in self.COMPLEXITY_SIGNALS.items():
            self._complexity_patterns[query_type] = [re.compile(p, re.IGNORECASE) for p in patterns]

        self._simple_patterns = [re.compile(p, re.IGNORECASE) for p in self.SIMPLE_SIGNALS]

    def _get_client(self):
        """Get or create the OpenAI client."""
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=self._api_key) if self._api_key else OpenAI()
        return self._client

    def classify(self, query: str) -> ClassificationResult:
        """
        Classify a query's complexity and type.

        Args:
            query: The user's query string

        Returns:
            ClassificationResult with complexity decision and detected type
        """
        query = query.strip()

        # Check for simple query patterns first
        for pattern in self._simple_patterns:
            if pattern.search(query):
                return ClassificationResult(
                    is_complex=False,
                    query_type="simple",
                    confidence=0.9,
                    signals=["simple_pattern_match"],
                    reasoning="Query matches simple pattern, no agentic processing needed",
                )

        # Check for complexity signals
        detected_signals: list[str] = []
        type_scores: dict[QueryType, float] = {}

        for query_type, patterns in self._complexity_patterns.items():
            matches = 0
            for pattern in patterns:
                if pattern.search(query):
                    matches += 1
                    detected_signals.append(f"{query_type}:{pattern.pattern}")

            if matches > 0:
                # Score based on number of matching patterns
                type_scores[query_type] = min(1.0, matches * 0.4)

        if not type_scores:
            # No complexity signals detected - try LLM if enabled
            if self._use_llm_fallback:
                llm_result = self._classify_with_llm(query)
                if llm_result:
                    return llm_result

            return ClassificationResult(
                is_complex=False,
                query_type="simple",
                confidence=0.7,
                signals=[],
                reasoning="No complexity signals detected",
            )

        # Find the best matching query type
        best_type = max(type_scores, key=lambda k: type_scores[k])
        best_score = type_scores[best_type]

        # If confidence is low, try LLM for better classification
        if best_score < self.LLM_FALLBACK_THRESHOLD and self._use_llm_fallback:
            llm_result = self._classify_with_llm(query)
            if llm_result and llm_result.confidence > best_score:
                return llm_result

        is_complex = best_score >= self.COMPLEXITY_THRESHOLD

        # Build reasoning
        if is_complex:
            reasoning = f"Detected {best_type} query with {len(detected_signals)} signal(s)"
        else:
            reasoning = f"Low confidence ({best_score:.2f}) for {best_type} classification"

        return ClassificationResult(
            is_complex=is_complex,
            query_type=best_type if is_complex else "simple",
            confidence=best_score,
            signals=detected_signals[:5],  # Limit to top 5 signals
            reasoning=reasoning,
        )

    def _classify_with_llm(self, query: str) -> ClassificationResult | None:
        """
        Use LLM for classification when pattern matching is uncertain.

        Args:
            query: The user's query string

        Returns:
            ClassificationResult or None if LLM call fails
        """
        try:
            client = self._get_client()

            response = client.chat.completions.create(
                model=CLASSIFIER_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": ROUTER_PROMPT.format(query=query),
                    }
                ],
                max_tokens=200,
                temperature=0.1,
            )

            content = response.choices[0].message.content or "{}"
            data = json.loads(content)

            category = data.get("category", "SIMPLE_RETRIEVAL")
            query_type = self.CATEGORY_MAP.get(category, "simple")
            confidence = float(data.get("confidence", 0.7))
            reasoning = data.get("reasoning", "LLM classification")

            is_complex = query_type != "simple" and confidence >= self.COMPLEXITY_THRESHOLD

            logger.debug(f"LLM classified '{query[:30]}...' as {query_type} ({confidence:.2f})")

            return ClassificationResult(
                is_complex=is_complex,
                query_type=query_type,
                confidence=confidence,
                signals=["llm_classification"],
                reasoning=f"LLM: {reasoning}",
            )

        except Exception as e:
            logger.warning(f"LLM classification failed: {e}")
            return None

    def is_complex(self, query: str) -> bool:
        """
        Quick check if a query needs agentic processing.

        Args:
            query: The user's query string

        Returns:
            True if the query should be handled by the agentic pipeline
        """
        return self.classify(query).is_complex

    def get_query_type(self, query: str) -> QueryType:
        """
        Get the detected query type.

        Args:
            query: The user's query string

        Returns:
            The detected query type
        """
        return self.classify(query).query_type

    def should_augment_with_web(self, query: str, notes_age_days: int | None = None) -> bool:
        """
        Check if a query would benefit from web search augmentation.

        This considers:
        1. Explicit web augmentation patterns in the query
        2. Age of the notes (older notes may benefit from updated context)
        3. Types of entities mentioned (tech/software evolves quickly)

        Args:
            query: The user's query string
            notes_age_days: Age of the oldest relevant note in days

        Returns:
            True if web search would likely improve the answer
        """
        # Check if query type is explicitly web_augmented
        classification = self.classify(query)
        if classification.query_type == "web_augmented":
            return True

        # Check for web augmentation patterns
        for pattern in self._complexity_patterns.get("web_augmented", []):
            if pattern.search(query):
                return True

        # If notes are old (>30 days), web might have updated info
        if notes_age_days is not None and notes_age_days > 30:
            # Additional check: is this about something that changes?
            evolving_topics = [
                r"\bsoftware\b",
                r"\bapp\b",
                r"\btool\b",
                r"\bframework\b",
                r"\blibrary\b",
                r"\bproject\b",
                r"\btech\b",
                r"\bai\b",
                r"\bpython\b",
                r"\breact\b",
                r"\bnode\b",
                r"\brust\b",
            ]
            for topic in evolving_topics:
                if re.search(topic, query, re.IGNORECASE):
                    return True

        return False

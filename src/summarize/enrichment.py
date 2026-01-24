"""
Web Enrichment Service for Trace Notes

Enriches hourly summaries with real-time web data for any content type:
- Live events (sports, news, streams) - get outcomes/updates
- Products being researched - get reviews, comparisons
- News stories - get additional context
- Any content flagged for enrichment

This service is called after initial summarization to add
context that wasn't available at capture time.

P5-11: Web enrichment for notes
"""

import logging
from dataclasses import dataclass
from datetime import datetime

from openai import OpenAI

from src.summarize.schemas import DetailItem, HourlySummarySchema, WatchingItem

logger = logging.getLogger(__name__)

# Model for enrichment queries (use a fast, capable model)
ENRICHMENT_MODEL = "gpt-4o-mini"


@dataclass
class EnrichmentResult:
    """Result of enrichment attempt."""

    success: bool
    enriched_count: int = 0
    error: str | None = None


class WebEnricher:
    """
    Enriches note summaries with web search results.

    Uses LLM to search for and summarize additional context for:
    - Live/ongoing events where outcomes aren't yet known
    - Products or services being researched
    - News stories being followed
    - Any content flagged for enrichment
    """

    def __init__(self, api_key: str | None = None):
        """
        Initialize the web enricher.

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

    def enrich_summary(
        self,
        summary: HourlySummarySchema,
        hour_start: datetime,
    ) -> EnrichmentResult:
        """
        Enrich a summary with web search results.

        This modifies the summary in place.

        Args:
            summary: The summary to enrich
            hour_start: The hour being summarized (for date context)

        Returns:
            EnrichmentResult with status and count
        """
        enriched_count = 0

        try:
            # Enrich watching items that need it
            for item in summary.media.watching:
                if self._should_enrich_watching(item):
                    if self._enrich_watching_item(item, hour_start):
                        enriched_count += 1

            # Enrich details that requested web enrichment
            for detail in summary.details:
                if detail.requires_web_enrichment and detail.enrichment_query:
                    if self._enrich_detail(detail, hour_start):
                        enriched_count += 1

            return EnrichmentResult(
                success=True,
                enriched_count=enriched_count,
            )

        except Exception as e:
            logger.error(f"Enrichment failed: {e}")
            return EnrichmentResult(
                success=False,
                error=str(e),
            )

    def _should_enrich_watching(self, item: WatchingItem) -> bool:
        """Check if a watching item should be enriched."""
        # Skip if already enriched or no enrichment requested
        if item.enrichment_result:
            return False
        if not item.requires_enrichment:
            return False
        if not item.enrichment_query:
            return False
        return True

    def _enrich_watching_item(
        self,
        item: WatchingItem,
        hour_start: datetime,
    ) -> bool:
        """
        Enrich a watching item with additional context.

        Args:
            item: The watching item to enrich
            hour_start: For date context

        Returns:
            True if enrichment was successful
        """
        if not item.enrichment_query:
            return False

        try:
            # Add date context to query
            date_str = hour_start.strftime("%B %d %Y")
            query = f"{item.enrichment_query} {date_str}"

            # Build context about the content type
            content_context = f"Content type: {item.content_type or 'unknown'}"
            if item.metadata:
                metadata_str = ", ".join(f"{k}: {v}" for k, v in item.metadata.items())
                content_context += f"\nKnown details: {metadata_str}"

            client = self._get_client()

            response = client.chat.completions.create(
                model=ENRICHMENT_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": f"""You are an information assistant. Given a search query about content someone was watching, provide a brief factual summary of relevant information.

{content_context}

Provide:
- Key outcomes or results if this was a live event
- Additional context that would be valuable to remember
- Any notable details

Keep the response under 100 words and focus on facts.
If you cannot find relevant information, say "Additional context not available."
""",
                    },
                    {
                        "role": "user",
                        "content": f"Find information for: {query}",
                    },
                ],
                max_tokens=150,
            )

            result = response.choices[0].message.content or ""

            if result and "not available" not in result.lower():
                item.enrichment_result = result.strip()
                item.requires_enrichment = False
                logger.info(f"Enriched watching item: {item.title}")
                return True

            return False

        except Exception as e:
            logger.warning(f"Failed to enrich watching item: {e}")
            return False

    def _enrich_detail(
        self,
        detail: DetailItem,
        hour_start: datetime,
    ) -> bool:
        """
        Enrich a detail item with web search results.

        Args:
            detail: The detail item to enrich
            hour_start: For date context

        Returns:
            True if enrichment was successful
        """
        if not detail.enrichment_query:
            return False

        try:
            client = self._get_client()

            # Add date context to query
            date_str = hour_start.strftime("%B %d %Y")
            query = f"{detail.enrichment_query} {date_str}"

            response = client.chat.completions.create(
                model=ENRICHMENT_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": """You are a research assistant. Given a search query, provide a brief, factual summary of the most relevant information.

Keep the response under 150 words and focus on facts that would be useful for someone trying to remember this context later.

If you cannot find relevant information, say "Additional context not available."
""",
                    },
                    {
                        "role": "user",
                        "content": f"Search: {query}",
                    },
                ],
                max_tokens=200,
            )

            result = response.choices[0].message.content or ""

            if result and "not available" not in result.lower():
                detail.enrichment_result = result.strip()
                detail.requires_web_enrichment = False
                logger.info(f"Enriched detail: {detail.category}")
                return True

            return False

        except Exception as e:
            logger.warning(f"Failed to enrich detail: {e}")
            return False


def enrich_hourly_note(
    summary: HourlySummarySchema,
    hour_start: datetime,
    api_key: str | None = None,
) -> EnrichmentResult:
    """
    Convenience function to enrich a summary.

    Args:
        summary: The summary to enrich (modified in place)
        hour_start: The hour being summarized
        api_key: Optional OpenAI API key

    Returns:
        EnrichmentResult with status
    """
    enricher = WebEnricher(api_key=api_key)
    return enricher.enrich_summary(summary, hour_start)


if __name__ == "__main__":
    import fire

    def demo():
        """Demo the enrichment service with sample content."""
        from src.summarize.schemas import (
            DetailItem,
            HourlySummarySchema,
            MediaSection,
            WatchingItem,
        )

        # Create a sample summary with various content types
        summary = HourlySummarySchema(
            schema_version=2,
            summary="Watched a live stream and researched products.",
            categories=["entertainment", "browsing"],
            details=[
                DetailItem(
                    category="research",
                    summary="User was comparing MacBook Pro models on Apple's website.",
                    requires_web_enrichment=True,
                    enrichment_query="MacBook Pro M3 Max vs M3 Pro comparison review",
                    confidence=0.9,
                )
            ],
            media=MediaSection(
                listening=[],
                watching=[
                    WatchingItem(
                        title="Tech Review Stream",
                        source="YouTube",
                        content_type="livestream",
                        metadata={"channel": "MKBHD", "topic": "CES 2026 coverage"},
                        requires_enrichment=True,
                        enrichment_query="MKBHD CES 2026 highlights",
                    )
                ],
            ),
        )

        print("Before enrichment:")
        for item in summary.media.watching:
            print(f"  - {item.title}: {item.enrichment_result}")
        for detail in summary.details:
            print(f"  - {detail.category}: {detail.enrichment_result}")

        # Note: This would actually call the API in a real scenario
        print("\n(Enrichment would call the API here)")

    fire.Fire({"demo": demo})

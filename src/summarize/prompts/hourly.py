"""
Hourly Summarization Prompt for Trace

Structured prompt for gpt-5-mini to generate hourly notes.
Outputs strict JSON conforming to a versioned schema.

P5-04: Hourly summarization prompt
"""

from datetime import datetime

from src.summarize.evidence import EvidenceAggregator, HourlyEvidence
from src.summarize.keyframes import SelectedKeyframe

# Schema version for output validation
SCHEMA_VERSION = 2

# Model for hourly summarization
HOURLY_MODEL = "gpt-5-mini-2025-08-07"

HOURLY_SCHEMA_DESCRIPTION = """
{
  "schema_version": 2,
  "summary": "2-3 sentence overview of the hour's activities",
  "categories": ["list", "of", "activity", "categories"],
  "activities": [
    {
      "time_start": "HH:MM",
      "time_end": "HH:MM",
      "description": "What the user was doing",
      "app": "Application name",
      "category": "work|learning|entertainment|communication|creative|browsing|other"
    }
  ],
  "topics": [
    {
      "name": "Topic or subject",
      "context": "How/why it was encountered",
      "confidence": 0.0-1.0
    }
  ],
  "details": [
    {
      "category": "goal|achievement|learning|research|problem_solving|decision|insight|context",
      "summary": "Detailed 2-4 sentence description with specific information",
      "intent": "What was the user trying to accomplish?",
      "outcome": "What was the result? Did they achieve their goal?",
      "evidence": ["Specific evidence from screenshots supporting this detail"],
      "requires_web_enrichment": false,
      "enrichment_query": "Suggested web search query if enrichment needed",
      "confidence": 0.0-1.0
    }
  ],
  "entities": [
    {
      "name": "Entity name",
      "type": "topic|app|domain|document|artist|track|video|game|person|project",
      "confidence": 0.0-1.0
    }
  ],
  "media": {
    "listening": [{"artist": "...", "track": "...", "duration_seconds": 123}],
    "watching": [
      {
        "title": "Content title or description",
        "source": "Platform or source (Netflix, YouTube, TV, browser, etc.)",
        "duration_seconds": 123,
        "content_type": "Type of content (movie, tv_show, livestream, sports, tutorial, news, gaming, etc.)",
        "metadata": {"key": "value pairs specific to content type"},
        "status": "live|completed|paused|null",
        "requires_enrichment": false,
        "enrichment_query": "Suggested search query for additional context",
        "enrichment_result": null
      }
    ]
  },
  "documents": [
    {
      "name": "File path or document name (e.g., 'src/auth/login.ts')",
      "type": "code|config|terminal|pdf|spreadsheet|presentation|markdown|text|other",
      "key_content": "Specific summary: functions modified, errors seen, commands run, etc.",
      "metadata": {"language": "typescript", "functions": ["handleLogin"], "errors": [], "etc": "..."}
    }
  ],
  "websites": [
    {
      "domain": "example.com",
      "page_title": "Page title if known",
      "purpose": "Why the user visited"
    }
  ],
  "co_activities": [
    {
      "primary": "Main activity",
      "secondary": "Concurrent activity",
      "relationship": "studied_while|worked_while|browsed_while"
    }
  ],
  "open_loops": ["Things mentioned but not completed"],
  "location": "Location if known, null otherwise"
}
"""

HOURLY_SYSTEM_PROMPT = f"""You are a personal activity summarizer for Trace, a second-brain application.

Your task is to analyze the user's digital activity for one hour and generate a structured summary that captures not just WHAT they did, but WHY they did it and what they achieved.

## Output Requirements

You MUST respond with valid JSON conforming to this schema:
{HOURLY_SCHEMA_DESCRIPTION}

## Guidelines

1. **Summary**: Write a concise 2-3 sentence overview capturing the main activities, goals, and outcomes.

2. **Categories**: List activity categories present (e.g., "work", "learning", "entertainment", "communication", "creative", "browsing").

3. **Activities**: Create a timeline of distinct activities with clear time boundaries. Merge very short activities into broader segments when appropriate.

4. **Topics**: Extract topics, subjects, or concepts the user was engaging with. Include learning topics, project names, research subjects.

5. **Details** (CRITICAL - Be Specific and Rich):
   Generate 2-5 detailed insights that go beyond simple topic extraction. For each detail:
   - **category**: What type of insight is this?
     - "goal": What the user was trying to accomplish
     - "achievement": What they successfully completed
     - "learning": What they learned or studied
     - "research": What they were researching or investigating
     - "problem_solving": Issues they were debugging or solving
     - "decision": Decisions they were making
     - "insight": Key realizations or discoveries
     - "context": Important contextual information
   - **summary**: Write 2-4 sentences with SPECIFIC information extracted from what you see. Extract actual text, names, numbers, error messages, file paths, etc.

   Examples of BAD vs GOOD summaries for different activity types:

   CODE/IDE:
     - BAD: "User was coding in VS Code"
     - GOOD: "User was implementing a retry mechanism in src/api/client.ts. The function 'fetchWithRetry' was being modified to add exponential backoff. A TypeScript error 'Property 'delay' does not exist on type 'RetryOptions'' was visible at line 47."

   TERMINAL:
     - BAD: "User ran some terminal commands"
     - GOOD: "User ran 'git rebase -i HEAD~5' to squash commits on the feature/auth branch. The interactive rebase showed 5 commits being combined. They then ran 'npm test' which showed 47 tests passing, 2 failing in auth.spec.ts."

   DEBUGGING:
     - BAD: "User was debugging an error"
     - GOOD: "User was debugging a 'Cannot read property 'user' of undefined' error in the authentication flow. The stack trace pointed to AuthContext.tsx:142. They added console.log statements and checked the Redux DevTools showing the auth state was null after logout."

   DOCUMENTS/WRITING:
     - BAD: "User was writing a document"
     - GOOD: "User was drafting a project proposal in Google Docs titled 'Q2 Infrastructure Migration Plan'. They were working on Section 3: Timeline, adding milestones for the database migration phase scheduled for April."

   DESIGN:
     - BAD: "User was using Figma"
     - GOOD: "User was iterating on the checkout flow redesign in Figma. They were adjusting the spacing on the payment form component, changing button padding from 12px to 16px, and updating the error state colors to match the new design system."

   BROWSING/RESEARCH:
     - BAD: "User was browsing the web"
     - GOOD: "User was comparing PostgreSQL vs MySQL for a new project. They had tabs open to the official docs for both, a Stack Overflow thread about performance differences, and were reading a 2024 benchmark comparison on the PlanetScale blog."

   COMMUNICATION:
     - BAD: "User was in a meeting"
     - GOOD: "User was in a Zoom standup with the backend team. The shared screen showed a Jira board with sprint items. Discussion appeared to focus on the BACKEND-1247 ticket about API rate limiting, with @sarah.chen presenting."

   - **intent**: Describe what the user was trying to accomplish based on visible context
   - **outcome**: What was the result? Did they achieve it? What progress was made?
   - **evidence**: List specific visual evidence from screenshots that supports this detail
   - **requires_web_enrichment**: Set to true if this detail would benefit from web search to add context (e.g., live events where outcomes aren't yet known, products being researched, documentation lookups, error message solutions)
   - **enrichment_query**: If requires_web_enrichment is true, provide a specific search query to get additional context

6. **Entities**: Extract named entities with their types:
   - topic: Abstract subjects or concepts
   - app: Applications used significantly
   - domain: Web domains visited meaningfully
   - document: Specific files or documents
   - artist: Musicians or content creators
   - track: Specific songs or audio content
   - video: Specific videos or shows
   - game: Games played
   - person: People mentioned or communicated with
   - project: Projects or work items

7. **Media** (Be Specific About What's Being Watched/Listened):
   For watching items:
   - Identify the content as specifically as possible from visible text, logos, UI elements
   - Use the **metadata** field to store content-specific information as key-value pairs
   - Set **requires_enrichment=true** if the content is live/ongoing and would benefit from knowing the final outcome
   - Examples of metadata for different content types:
     - Sports: {{"teams": ["Team A", "Team B"], "score": "2-1", "competition": "League Name"}}
     - TV shows: {{"show": "Breaking Bad", "season": 2, "episode": 5}}
     - YouTube: {{"channel": "MKBHD", "topic": "iPhone 16 review"}}
     - Gaming: {{"game": "Elden Ring", "activity": "boss fight", "area": "Limgrave"}}
     - News: {{"outlet": "BBC", "story": "Election results"}}

8. **Documents** (IMPORTANT - Be Specific About Code and Files):
   For any files being viewed or edited, capture:
   - **name**: Full file path if visible (e.g., "src/components/Auth/LoginForm.tsx")
   - **type**: code, pdf, spreadsheet, presentation, markdown, config, etc.
   - **key_content**: What specifically was being read or edited

   For code files, include:
   - Function/class names being worked on
   - Specific changes being made
   - Error messages if debugging
   - Test results if running tests

   For terminal/shell:
   - Commands that were run
   - Notable output or errors
   - Git operations (branch, commits, etc.)

9. **Websites**: Record significant website visits with purpose.

10. **Co-activities**: Identify overlapping activities (e.g., "studied machine learning while listening to Spotify").

11. **Open Loops**: Note any incomplete tasks or items that might need follow-up.

## Detecting User Intent

Analyze the visual context to understand what the user is trying to accomplish:

**Development/Coding signals:**
- Error messages, stack traces, red underlines → debugging/problem-solving
- Terminal with test commands (pytest, jest, npm test) → testing
- Git commands, GitHub/GitLab UI → version control, code review
- Multiple files open in IDE → feature implementation or refactoring
- Diff view, merge conflicts → code integration
- Package.json, requirements.txt, Cargo.toml edits → dependency management
- Docker, K8s configs → infrastructure work
- API client (Postman, Insomnia, curl) → API development/testing

**Research/Learning signals:**
- Multiple tabs on similar topics → research/comparison
- Documentation sites (MDN, docs.rs, ReadTheDocs) → learning APIs
- Stack Overflow, GitHub Issues → troubleshooting
- Tutorial videos, course platforms → structured learning

**Communication/Collaboration signals:**
- Messaging apps, email, Slack → communication
- Video calls (Zoom, Meet, Teams) → meetings
- Shared docs, Notion, Confluence → collaborative work
- PR reviews, code comments → code review

**Creative/Content signals:**
- Design tools (Figma, Photoshop) → design work
- Writing apps, text editors with prose → content creation
- Multiple iterations on same file → refinement

**Other signals:**
- Shopping sites, product pages → purchasing decision
- Calendar, task apps → planning/organizing
- Video content fullscreen → entertainment/learning

## When to Request Web Enrichment

Set requires_enrichment=true when additional context would be valuable:
- **Error messages**: Search for solutions (e.g., "TypeScript error TS2339 property does not exist solution")
- **Library/API questions**: Get documentation context (e.g., "React useEffect cleanup function best practices")
- **Live events**: Get outcomes (e.g., "Apple WWDC 2026 announcements")
- **News stories**: Get additional context
- **Products being researched**: Get reviews/comparisons
- **New technologies mentioned**: Get overview/tutorials
- **Deprecated warnings**: Get migration guides

## Constraints

- Do NOT include full document or website contents
- Be SPECIFIC rather than generic - extract actual names, titles, numbers visible on screen
- Confidence scores should reflect certainty (0.0-1.0)
- Use exact timestamps from the evidence when available
- Location should be geographic if known, null otherwise

## Schema Version

The current schema version is {SCHEMA_VERSION}. Include this in your response.
"""


def build_hourly_user_prompt(
    evidence: HourlyEvidence,
    keyframes: list[SelectedKeyframe] | None = None,
    aggregator: EvidenceAggregator | None = None,
) -> str:
    """
    Build the user prompt for hourly summarization.

    Args:
        evidence: Aggregated evidence for the hour
        keyframes: Selected keyframes with descriptions
        aggregator: Optional aggregator for building timeline text

    Returns:
        Formatted user prompt string
    """
    lines = []

    # Header
    lines.append(
        f"# Hour: {evidence.hour_start.strftime('%Y-%m-%d %H:00')} - {evidence.hour_end.strftime('%H:00')}"
    )
    lines.append("")

    # Build timeline
    if aggregator:
        lines.append(aggregator.build_timeline_text(evidence))
    else:
        # Fallback: simple timeline
        lines.append("## Activity Timeline")
        lines.append("")
        for event in evidence.events:
            time_str = event.start_ts.strftime("%H:%M:%S")
            duration_min = event.duration_seconds // 60
            app = event.app_name or "Unknown"
            line = f"- [{time_str}] ({duration_min}m) {app}"
            if event.window_title:
                line += f" - {event.window_title[:50]}"
            lines.append(line)

    lines.append("")

    # Keyframe descriptions
    if keyframes:
        lines.append("## Keyframe Observations")
        lines.append("")
        for kf in keyframes:
            time_str = kf.timestamp.strftime("%H:%M:%S")
            desc = ""
            if kf.triage_result and kf.triage_result.description:
                desc = kf.triage_result.description
            elif kf.window_title:
                desc = f"{kf.app_name or 'App'}: {kf.window_title}"
            else:
                desc = kf.selection_reason

            lines.append(f"- [{time_str}] {desc}")
        lines.append("")

    # Text evidence
    if evidence.text_snippets:
        lines.append("## Extracted Text (Document/OCR)")
        lines.append("")
        for snippet in evidence.text_snippets:
            time_str = snippet.timestamp.strftime("%H:%M:%S")
            source = snippet.source_type
            lines.append(f"### [{time_str}] Source: {source}")
            if snippet.ref:
                lines.append(f"Reference: {snippet.ref}")
            lines.append("```")
            # Truncate long text for the prompt
            text = snippet.text
            if len(text) > 1000:
                text = text[:1000] + "... [truncated]"
            lines.append(text)
            lines.append("```")
            lines.append("")

    # Now playing
    if evidence.now_playing_spans:
        lines.append("## Media Playing During This Hour")
        lines.append("")
        for span in evidence.now_playing_spans:
            duration = int((span.end_ts - span.start_ts).total_seconds())
            lines.append(f"- {span.artist} - {span.track} ({duration}s via {span.app})")
        lines.append("")

    # Location
    if evidence.locations:
        lines.append(f"## Location: {', '.join(evidence.locations)}")
        lines.append("")

    # Statistics
    lines.append("## Evidence Statistics")
    lines.append(f"- Total events: {evidence.total_events}")
    lines.append(f"- Total screenshots: {evidence.total_screenshots}")
    lines.append(f"- Text buffers: {evidence.total_text_buffers}")
    lines.append(f"- Selected keyframes: {len(keyframes) if keyframes else 0}")
    lines.append("")

    # Instructions
    lines.append("---")
    lines.append(
        "Based on this evidence, generate a structured JSON summary following the schema provided in the system prompt."
    )

    return "\n".join(lines)


def build_vision_messages(
    evidence: HourlyEvidence,
    keyframes: list[SelectedKeyframe],
    aggregator: EvidenceAggregator | None = None,
) -> list[dict]:
    """
    Build messages with vision content for the LLM.

    Args:
        evidence: Aggregated evidence for the hour
        keyframes: Selected keyframes (must include screenshot paths)
        aggregator: Optional aggregator for building timeline text

    Returns:
        List of message dicts for the OpenAI API
    """
    import base64

    messages = [{"role": "system", "content": HOURLY_SYSTEM_PROMPT}]

    # Build user content with images
    user_content = []

    # Add text prompt first
    text_prompt = build_hourly_user_prompt(evidence, keyframes, aggregator)
    user_content.append({"type": "text", "text": text_prompt})

    # Add keyframe images
    for kf in keyframes:
        if kf.screenshot_path and kf.screenshot_path.exists():
            try:
                with open(kf.screenshot_path, "rb") as f:
                    image_data = base64.b64encode(f.read()).decode("utf-8")

                time_str = kf.timestamp.strftime("%H:%M:%S")
                user_content.append(
                    {
                        "type": "text",
                        "text": f"[Screenshot at {time_str}]",
                    }
                )
                user_content.append(
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/jpeg;base64,{image_data}",
                            "detail": "low",  # Use low for cost efficiency
                        },
                    }
                )
            except Exception:
                continue

    messages.append({"role": "user", "content": user_content})

    return messages


if __name__ == "__main__":
    import fire

    def show_schema():
        """Show the JSON schema for hourly summaries."""
        print(HOURLY_SCHEMA_DESCRIPTION)

    def show_system_prompt():
        """Show the system prompt."""
        print(HOURLY_SYSTEM_PROMPT)

    def demo_user_prompt():
        """Show a demo user prompt."""
        from datetime import timedelta

        # Create mock evidence
        hour_start = datetime.now().replace(minute=0, second=0, microsecond=0)
        evidence = HourlyEvidence(
            hour_start=hour_start,
            hour_end=hour_start + timedelta(hours=1),
            total_events=5,
            total_screenshots=120,
            total_text_buffers=3,
        )

        print(build_hourly_user_prompt(evidence))

    fire.Fire(
        {
            "schema": show_schema,
            "system": show_system_prompt,
            "demo": demo_user_prompt,
        }
    )

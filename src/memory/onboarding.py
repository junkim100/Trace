"""
Conversational Onboarding Service for Trace

This module handles the interactive chat-based onboarding experience that
learns about the user and populates MEMORY.md with their profile information.

Uses a hybrid approach:
1. Guided questions for key information (name, occupation, interests)
2. Free-form conversation for additional context
3. LLM-based extraction to populate memory structure
"""

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from openai import OpenAI

from src.core.config import get_api_key
from src.memory.memory import get_memory_manager

logger = logging.getLogger(__name__)

# Model for onboarding chat - fast responses for conversation
ONBOARDING_CHAT_MODEL = "gpt-5-mini-2025-08-07"
# Model for final extraction - comprehensive analysis
EXTRACTION_MODEL = "gpt-5.2-2025-12-11"


class ConversationPhase(str, Enum):
    """Phases of the onboarding conversation."""

    GREETING = "greeting"
    NAME = "name"
    OCCUPATION = "occupation"
    INTERESTS = "interests"
    OPEN_ENDED = "open_ended"
    CONFIRMING = "confirming"
    COMPLETE = "complete"


@dataclass
class Message:
    """A message in the conversation."""

    role: str  # "assistant" or "user"
    content: str


@dataclass
class ExtractedInfo:
    """Information extracted from conversation."""

    name: str = ""
    preferred_name: str = ""
    current_role: str = ""
    company: str = ""
    industry: str = ""
    interests_professional: list[str] = field(default_factory=list)
    interests_personal: list[str] = field(default_factory=list)
    technical_stack: list[str] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    key_facts: list[str] = field(default_factory=list)
    goals: list[str] = field(default_factory=list)
    additional_context: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "preferred_name": self.preferred_name,
            "current_role": self.current_role,
            "company": self.company,
            "industry": self.industry,
            "interests_professional": self.interests_professional,
            "interests_personal": self.interests_personal,
            "technical_stack": self.technical_stack,
            "tools": self.tools,
            "key_facts": self.key_facts,
            "goals": self.goals,
            "additional_context": self.additional_context,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ExtractedInfo":
        return cls(
            name=data.get("name", ""),
            preferred_name=data.get("preferred_name", ""),
            current_role=data.get("current_role", ""),
            company=data.get("company", ""),
            industry=data.get("industry", ""),
            interests_professional=data.get("interests_professional", []),
            interests_personal=data.get("interests_personal", []),
            technical_stack=data.get("technical_stack", []),
            tools=data.get("tools", []),
            key_facts=data.get("key_facts", []),
            goals=data.get("goals", []),
            additional_context=data.get("additional_context", []),
        )

    def has_minimum_info(self) -> bool:
        """Check if we have enough info to proceed."""
        return bool(self.name) and (
            bool(self.current_role)
            or bool(self.interests_professional)
            or bool(self.interests_personal)
        )


# Scripted prompts for guided phases
PHASE_PROMPTS = {
    ConversationPhase.GREETING: (
        "Hi! I'm Trace, your digital memory assistant. I'll help you keep track of "
        "your digital activities and turn them into searchable notes. Let's get to know "
        "each other so I can personalize your experience. What should I call you?"
    ),
    ConversationPhase.NAME: "What should I call you?",
    ConversationPhase.OCCUPATION: "Nice to meet you{name_part}! What do you do? Feel free to share your role, industry, or what you're currently working on.",
    ConversationPhase.INTERESTS: "Great! What are you interested in or passionate about? Could be hobbies, topics you're learning, or professional interests.",
    ConversationPhase.OPEN_ENDED: "Is there anything else you'd like me to know about you? This could be tools you use, work preferences, goals, or anything that helps me understand you better.",
    ConversationPhase.CONFIRMING: "Thanks for sharing{name_part}! I've learned a lot about you. You can always update this information later in Settings. Ready to continue?",
}


class OnboardingChatService:
    """
    Manages the conversational onboarding experience.

    Handles conversation flow, LLM interactions for dynamic responses,
    and information extraction to populate MEMORY.md.
    """

    def __init__(self, api_key: str | None = None):
        """Initialize the onboarding service."""
        self.api_key = api_key or get_api_key()
        if not self.api_key:
            raise ValueError("No API key available for onboarding chat")
        self.client = OpenAI(api_key=self.api_key)

    def get_initial_message(self, mode: str = "initial") -> dict[str, Any]:
        """
        Get the initial greeting message for the conversation.

        Args:
            mode: 'initial', 'update', or 'restart'

        Returns:
            Dict with assistant message and initial state
        """
        if mode == "update":
            # Load existing memory for context
            manager = get_memory_manager()
            memory = manager.get_memory()

            # Build a summary of what we know
            known_parts = []
            if memory.profile.name:
                known_parts.append(f"Name: {memory.profile.name}")
            if memory.profile.current_role:
                known_parts.append(f"Role: {memory.profile.current_role}")
            if memory.interests.professional:
                known_parts.append(f"Interests: {', '.join(memory.interests.professional[:3])}")

            if known_parts:
                summary = "\n".join(f"- {p}" for p in known_parts)
                message = (
                    f"Welcome back! Here's what I know about you:\n\n{summary}\n\n"
                    "What would you like to update or add?"
                )
            else:
                message = (
                    "Welcome back! I don't have much information about you yet. "
                    "What would you like to share?"
                )

            return {
                "message": message,
                "phase": ConversationPhase.OPEN_ENDED.value,
                "extracted": ExtractedInfo().to_dict(),
            }

        elif mode == "restart":
            # Clear memory first
            manager = get_memory_manager()
            manager._memory = None
            # Delete the file
            if manager.memory_path.exists():
                manager.memory_path.unlink()

        # Initial or restart - start fresh
        return {
            "message": PHASE_PROMPTS[ConversationPhase.GREETING],
            "phase": ConversationPhase.GREETING.value,
            "extracted": ExtractedInfo().to_dict(),
        }

    def process_message(
        self,
        phase: str,
        user_message: str,
        history: list[dict[str, str]],
        extracted_so_far: dict[str, Any],
        mode: str = "initial",
    ) -> dict[str, Any]:
        """
        Process a user message and generate a response.

        Args:
            phase: Current conversation phase
            user_message: The user's message
            history: Previous messages in the conversation
            extracted_so_far: Information already extracted
            mode: 'initial', 'update', or 'restart'

        Returns:
            Dict with response, updated extraction, and state changes
        """
        current_phase = ConversationPhase(phase)
        extracted = ExtractedInfo.from_dict(extracted_so_far)

        # Extract information from this message
        extraction_result = self._extract_from_message(user_message, current_phase, extracted)
        extracted = extraction_result["extracted"]

        # Determine next phase and response
        response_data = self._generate_response(
            current_phase, user_message, history, extracted, mode
        )

        return {
            "response": response_data["response"],
            "extracted": extracted.to_dict(),
            "phase": response_data["next_phase"],
            "should_advance": response_data["should_advance"],
            "completion_detected": response_data["completion_detected"],
            "is_ready_to_continue": extracted.has_minimum_info(),
        }

    def _extract_from_message(
        self,
        message: str,
        phase: ConversationPhase,
        extracted: ExtractedInfo,
    ) -> dict[str, Any]:
        """Extract information from a user message."""
        # Build extraction prompt
        prompt = f"""Extract information from this user message in an onboarding conversation.

Current phase: {phase.value}
Already extracted: {json.dumps(extracted.to_dict(), indent=2)}

User message: "{message}"

Extract any new information and return as JSON:
{{
    "name": "user's name if mentioned",
    "preferred_name": "nickname or preferred name if different",
    "current_role": "job title or role if mentioned",
    "company": "company or organization if mentioned",
    "industry": "industry or field if mentioned",
    "interests_professional": ["professional interests or topics"],
    "interests_personal": ["hobbies, personal interests"],
    "technical_stack": ["programming languages, frameworks, technologies"],
    "tools": ["software tools, apps, platforms they use"],
    "key_facts": ["important facts about them"],
    "goals": ["goals or aspirations mentioned"],
    "additional_context": ["other relevant info"]
}}

Rules:
- Only include fields with actual new information from this message
- Don't repeat information already extracted
- Be specific and accurate
- Return valid JSON only"""

        try:
            response = self.client.chat.completions.create(
                model=ONBOARDING_CHAT_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You extract structured information from conversation messages. Return only valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.1,
                max_completion_tokens=500,
            )

            result_text = response.choices[0].message.content or "{}"

            # Parse JSON
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0]
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0]

            new_info = json.loads(result_text.strip())

            # Merge with existing
            if new_info.get("name") and not extracted.name:
                extracted.name = new_info["name"]
            if new_info.get("preferred_name"):
                extracted.preferred_name = new_info["preferred_name"]
            if new_info.get("current_role") and not extracted.current_role:
                extracted.current_role = new_info["current_role"]
            if new_info.get("company") and not extracted.company:
                extracted.company = new_info["company"]
            if new_info.get("industry") and not extracted.industry:
                extracted.industry = new_info["industry"]

            # Merge lists (avoiding duplicates)
            for field in [
                "interests_professional",
                "interests_personal",
                "technical_stack",
                "tools",
                "key_facts",
                "goals",
                "additional_context",
            ]:
                new_items = new_info.get(field, [])
                existing = getattr(extracted, field)
                for item in new_items:
                    if item and item not in existing:
                        existing.append(item)

        except Exception as e:
            logger.warning(f"Extraction failed: {e}")

        return {"extracted": extracted}

    def _generate_response(
        self,
        current_phase: ConversationPhase,
        user_message: str,
        history: list[dict[str, str]],
        extracted: ExtractedInfo,
        mode: str,
    ) -> dict[str, Any]:
        """Generate the assistant's response and determine next phase."""
        name_part = f", {extracted.name}" if extracted.name else ""
        completion_signals = [
            "no",
            "nope",
            "that's all",
            "that's it",
            "i'm good",
            "nothing else",
            "done",
            "ready",
        ]

        # Check for completion in open-ended phase
        user_lower = user_message.lower().strip()
        completion_detected = any(signal in user_lower for signal in completion_signals)

        # Determine next phase based on current phase
        if current_phase == ConversationPhase.GREETING:
            # Greeting already asks for name, so skip to occupation
            next_phase = ConversationPhase.OCCUPATION.value
            response = PHASE_PROMPTS[ConversationPhase.OCCUPATION].format(name_part=name_part)
            should_advance = True

        elif current_phase == ConversationPhase.NAME:
            next_phase = ConversationPhase.OCCUPATION.value
            response = PHASE_PROMPTS[ConversationPhase.OCCUPATION].format(name_part=name_part)
            should_advance = True

        elif current_phase == ConversationPhase.OCCUPATION:
            next_phase = ConversationPhase.INTERESTS.value
            response = PHASE_PROMPTS[ConversationPhase.INTERESTS]
            should_advance = True

        elif current_phase == ConversationPhase.INTERESTS:
            next_phase = ConversationPhase.OPEN_ENDED.value
            response = PHASE_PROMPTS[ConversationPhase.OPEN_ENDED]
            should_advance = True

        elif current_phase == ConversationPhase.OPEN_ENDED:
            # After user answers the open-ended question, move to confirming
            # Don't keep asking follow-up questions - let them know they can update later
            next_phase = ConversationPhase.CONFIRMING.value
            response = PHASE_PROMPTS[ConversationPhase.CONFIRMING].format(name_part=name_part)
            should_advance = True

        elif current_phase == ConversationPhase.CONFIRMING:
            # Check if they're ready
            affirmative_signals = [
                "yes",
                "yeah",
                "yep",
                "sure",
                "ready",
                "let's go",
                "continue",
                "ok",
                "okay",
            ]
            if any(signal in user_lower for signal in affirmative_signals):
                next_phase = ConversationPhase.COMPLETE.value
                response = "Great! Let's finish setting up Trace."
                completion_detected = True
            else:
                # They want to add more
                next_phase = ConversationPhase.OPEN_ENDED.value
                response = "No problem! What else would you like to share?"
            should_advance = True

        else:
            # Default fallback
            next_phase = current_phase.value
            response = "I'm not sure I understood. Could you rephrase that?"
            should_advance = False

        # For update mode, handle differently
        if mode == "update" and next_phase == ConversationPhase.CONFIRMING.value:
            next_phase = ConversationPhase.COMPLETE.value
            response = (
                "Got it! I've updated your profile. You can come back here anytime to add more."
            )
            completion_detected = True

        return {
            "response": response,
            "next_phase": next_phase,
            "should_advance": should_advance,
            "completion_detected": completion_detected
            and next_phase == ConversationPhase.COMPLETE.value,
        }

    def _generate_dynamic_response(
        self,
        user_message: str,
        history: list[dict[str, str]],
        extracted: ExtractedInfo,
    ) -> str:
        """Generate a dynamic conversational response for open-ended phase."""
        # Build conversation context
        conv_history = "\n".join(
            f"{'Assistant' if msg['role'] == 'assistant' else 'User'}: {msg['content']}"
            for msg in history[-6:]  # Last 6 messages for context
        )

        prompt = f"""You are Trace's onboarding assistant having a friendly conversation to learn about the user.

Conversation so far:
{conv_history}
User: {user_message}

Information already known:
{json.dumps(extracted.to_dict(), indent=2)}

Generate a brief, friendly response (1-2 sentences) that:
1. Acknowledges what they shared
2. Optionally asks a natural follow-up OR invites them to share more if they want
3. Doesn't repeat questions about info you already have

Keep it conversational and warm. If they seem done, acknowledge and ask if they're ready to continue."""

        try:
            response = self.client.chat.completions.create(
                model=ONBOARDING_CHAT_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a friendly onboarding assistant. Keep responses brief and warm.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.7,
                max_completion_tokens=150,
            )

            return (
                response.choices[0].message.content
                or "Thanks for sharing! Anything else you'd like to add?"
            )

        except Exception as e:
            logger.warning(f"Dynamic response generation failed: {e}")
            return "Thanks for sharing! Is there anything else you'd like me to know?"

    def finalize_and_save(
        self,
        history: list[dict[str, str]],
        extracted: dict[str, Any],
    ) -> dict[str, Any]:
        """
        Finalize the conversation and save to MEMORY.md.

        Args:
            history: Full conversation history
            extracted: Extracted information from conversation

        Returns:
            Dict with success status and summary
        """
        extracted_info = ExtractedInfo.from_dict(extracted)

        # Do a final comprehensive extraction from the full conversation
        final_extraction = self._final_extraction(history, extracted_info)

        # Save to memory
        manager = get_memory_manager()
        memory = manager.get_memory()

        items_added = 0

        # Update profile
        if final_extraction.name and not memory.profile.name:
            memory.profile.name = final_extraction.name
            items_added += 1
        if final_extraction.preferred_name and not memory.profile.preferred_name:
            memory.profile.preferred_name = final_extraction.preferred_name
            items_added += 1
        if final_extraction.current_role and not memory.profile.current_role:
            memory.profile.current_role = final_extraction.current_role
            items_added += 1
        if final_extraction.company and not memory.profile.company:
            memory.profile.company = final_extraction.company
            items_added += 1
        if final_extraction.industry and not memory.profile.industry:
            memory.profile.industry = final_extraction.industry
            items_added += 1

        # Add interests
        for interest in final_extraction.interests_professional:
            if interest and interest not in memory.interests.professional:
                memory.interests.professional.append(interest)
                items_added += 1
        for interest in final_extraction.interests_personal:
            if interest and interest not in memory.interests.personal_hobbies:
                memory.interests.personal_hobbies.append(interest)
                items_added += 1

        # Add technical info
        for tech in final_extraction.technical_stack:
            if tech and tech not in memory.technical.primary_stack:
                memory.technical.primary_stack.append(tech)
                items_added += 1
        for tool in final_extraction.tools:
            if tool and tool not in memory.technical.tools_platforms:
                memory.technical.tools_platforms.append(tool)
                items_added += 1

        # Add key facts
        for fact in final_extraction.key_facts:
            if fact and fact not in memory.context.key_facts:
                memory.context.key_facts.append(fact)
                items_added += 1

        # Add goals
        for goal in final_extraction.goals:
            if goal and goal not in memory.context.goals_aspirations:
                memory.context.goals_aspirations.append(goal)
                items_added += 1

        # Add memory log entry
        from datetime import datetime

        from src.memory.memory import MemoryLogEntry

        memory.memory_log.append(
            MemoryLogEntry(
                timestamp=datetime.now(),
                content="Profile updated via onboarding conversation",
                category="onboarding",
            )
        )

        # Save
        manager.save()

        logger.info(f"Onboarding finalized. Added {items_added} items to memory.")

        return {
            "success": True,
            "items_added": items_added,
            "summary": self._build_summary(final_extraction),
        }

    def _final_extraction(
        self,
        history: list[dict[str, str]],
        current_extraction: ExtractedInfo,
    ) -> ExtractedInfo:
        """Do a comprehensive final extraction from the full conversation."""
        # Build conversation transcript
        transcript = "\n".join(
            f"{'Assistant' if msg['role'] == 'assistant' else 'User'}: {msg['content']}"
            for msg in history
        )

        prompt = f"""Analyze this complete onboarding conversation and extract comprehensive user information.

CONVERSATION:
{transcript}

ALREADY EXTRACTED:
{json.dumps(current_extraction.to_dict(), indent=2)}

Do a final comprehensive extraction. Include everything relevant from the conversation.
Return JSON with this structure:
{{
    "name": "user's full name",
    "preferred_name": "nickname or how they prefer to be called",
    "current_role": "their job title or role",
    "company": "company or organization",
    "industry": "industry or field",
    "interests_professional": ["professional interests, topics they follow"],
    "interests_personal": ["hobbies, personal interests, activities"],
    "technical_stack": ["technologies, languages, frameworks they use"],
    "tools": ["software, apps, platforms they use"],
    "key_facts": ["important facts about them that affect how to assist"],
    "goals": ["goals, aspirations, what they want to achieve"]
}}

Be thorough but accurate. Only include information actually stated or clearly implied."""

        try:
            response = self.client.chat.completions.create(
                model=EXTRACTION_MODEL,
                messages=[
                    {
                        "role": "system",
                        "content": "You extract comprehensive user information from conversations. Return only valid JSON.",
                    },
                    {"role": "user", "content": prompt},
                ],
                temperature=0.2,
                max_completion_tokens=1000,
            )

            result_text = response.choices[0].message.content or "{}"

            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0]
            elif "```" in result_text:
                result_text = result_text.split("```")[1].split("```")[0]

            final_data = json.loads(result_text.strip())
            return ExtractedInfo.from_dict(final_data)

        except Exception as e:
            logger.warning(f"Final extraction failed: {e}")
            return current_extraction

    def _build_summary(self, extracted: ExtractedInfo) -> str:
        """Build a human-readable summary of what was learned."""
        parts = []
        if extracted.name:
            parts.append(f"Name: {extracted.name}")
        if extracted.current_role:
            role_str = extracted.current_role
            if extracted.company:
                role_str += f" at {extracted.company}"
            parts.append(f"Role: {role_str}")
        if extracted.interests_professional or extracted.interests_personal:
            all_interests = extracted.interests_professional + extracted.interests_personal
            parts.append(f"Interests: {', '.join(all_interests[:5])}")
        if extracted.technical_stack:
            parts.append(f"Tech: {', '.join(extracted.technical_stack[:5])}")

        if parts:
            return "I learned:\n" + "\n".join(f"- {p}" for p in parts)
        return "Ready to get started!"


def get_memory_summary() -> str:
    """Get a brief summary of current memory for display."""
    manager = get_memory_manager()
    memory = manager.get_memory()

    parts = []
    if memory.profile.name:
        parts.append(f"Name: {memory.profile.name}")
    if memory.profile.current_role:
        role_str = memory.profile.current_role
        if memory.profile.company:
            role_str += f" at {memory.profile.company}"
        parts.append(f"Role: {role_str}")
    if memory.interests.professional:
        parts.append(f"Professional interests: {', '.join(memory.interests.professional[:3])}")
    if memory.interests.personal_hobbies:
        parts.append(f"Hobbies: {', '.join(memory.interests.personal_hobbies[:3])}")
    if memory.technical.primary_stack:
        parts.append(f"Tech stack: {', '.join(memory.technical.primary_stack[:3])}")

    if parts:
        return "\n".join(f"- {p}" for p in parts)
    return "No information stored yet."


def clear_memory() -> bool:
    """Clear all memory data."""
    manager = get_memory_manager()
    try:
        if manager.memory_path.exists():
            manager.memory_path.unlink()
        manager._memory = None
        logger.info("Memory cleared")
        return True
    except Exception as e:
        logger.error(f"Failed to clear memory: {e}")
        return False

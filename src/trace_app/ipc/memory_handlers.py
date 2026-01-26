"""IPC handlers for user memory functionality.

This module registers IPC handlers for the memory API, allowing the Electron
frontend to interact with the user's memory (MEMORY.md).
"""

import logging
from typing import Any

from src.memory.memory import get_memory_manager
from src.trace_app.ipc.server import handler

logger = logging.getLogger(__name__)


@handler("memory.get")
def handle_get_memory(params: dict[str, Any]) -> dict[str, Any]:
    """Get the current user memory.

    Returns:
        Complete memory as dict with profile, interests, preferences, etc.
    """
    manager = get_memory_manager()
    memory = manager.get_memory()
    return {
        "success": True,
        "memory": memory.to_dict(),
    }


@handler("memory.get_context")
def handle_get_memory_context(params: dict[str, Any]) -> dict[str, Any]:
    """Get memory context formatted for LLM prompts.

    Returns:
        Formatted context string.
    """
    manager = get_memory_manager()
    memory = manager.get_memory()
    return {
        "success": True,
        "context": memory.get_context_for_llm(),
    }


@handler("memory.get_raw")
def handle_get_raw_memory(params: dict[str, Any]) -> dict[str, Any]:
    """Get the raw markdown content of the memory file.

    Returns:
        Raw markdown string.
    """
    manager = get_memory_manager()
    memory = manager.get_memory()
    return {
        "success": True,
        "content": memory.to_markdown(),
    }


@handler("memory.update_profile")
def handle_update_profile(params: dict[str, Any]) -> dict[str, Any]:
    """Update user profile fields.

    Params:
        name: Optional user name
        age: Optional age
        languages: Optional languages
        location: Optional location
        occupation: Optional occupation

    Returns:
        Success status.
    """
    manager = get_memory_manager()

    profile_data = {}
    for field in ["name", "age", "languages", "location", "occupation"]:
        if field in params:
            profile_data[field] = params[field]

    if not profile_data:
        return {"success": False, "error": "No profile fields provided"}

    success = manager.update_profile(profile_data)
    return {"success": success}


@handler("memory.add_item")
def handle_add_item(params: dict[str, Any]) -> dict[str, Any]:
    """Add an item to a memory section.

    Params:
        section: Section name (interests, preferences, facts, work, patterns, insights)
        item: Item text to add

    Returns:
        Success status.
    """
    section = params.get("section", "").lower()
    item = params.get("item", "").strip()

    if not section:
        return {"success": False, "error": "section parameter is required"}
    if not item:
        return {"success": False, "error": "item parameter is required"}

    manager = get_memory_manager()

    section_methods = {
        "interests": manager.add_interest,
        "interest": manager.add_interest,
        "preferences": manager.add_preference,
        "preference": manager.add_preference,
        "facts": manager.add_fact,
        "fact": manager.add_fact,
        "important_facts": manager.add_fact,
        "work": manager.add_work_project,
        "work_projects": manager.add_work_project,
        "project": manager.add_work_project,
        "patterns": manager.add_pattern,
        "pattern": manager.add_pattern,
        "learned_patterns": manager.add_pattern,
        "insights": manager.add_insight,
        "insight": manager.add_insight,
        "conversation_insights": manager.add_insight,
    }

    method = section_methods.get(section)
    if not method:
        return {"success": False, "error": f"Unknown section: {section}"}

    success = method(item)
    return {"success": success}


@handler("memory.remove_item")
def handle_remove_item(params: dict[str, Any]) -> dict[str, Any]:
    """Remove an item from a memory section.

    Params:
        section: Section name
        item: Item text to remove

    Returns:
        Success status.
    """
    section = params.get("section", "")
    item = params.get("item", "")

    if not section:
        return {"success": False, "error": "section parameter is required"}
    if not item:
        return {"success": False, "error": "item parameter is required"}

    manager = get_memory_manager()
    success = manager.remove_item(section, item)
    return {"success": success}


@handler("memory.bulk_update")
def handle_bulk_update(params: dict[str, Any]) -> dict[str, Any]:
    """Perform bulk updates to memory.

    Params:
        updates: Dictionary with section names as keys and lists/dicts as values
            - profile: {name, age, languages, location, occupation}
            - interests: [list of interests]
            - preferences: [list of preferences]
            - facts: [list of facts]
            - work: [list of work/projects]
            - patterns: [list of patterns]
            - insights: [list of insights]

    Returns:
        Success status.
    """
    updates = params.get("updates", {})

    if not updates:
        return {"success": False, "error": "updates parameter is required"}

    manager = get_memory_manager()
    success = manager.bulk_update(updates)
    return {"success": success}


@handler("memory.learn_from_response")
def handle_learn_from_response(params: dict[str, Any]) -> dict[str, Any]:
    """Learn new information from a user's response to a follow-up question.

    This handler processes the user's answer and extracts relevant memory updates.

    Params:
        question: The follow-up question that was asked
        answer: The user's response
        context: Optional context about what triggered the question

    Returns:
        Success status and any extracted information.
    """
    question = params.get("question", "")
    answer = params.get("answer", "").strip()
    # context is stored for potential future use with LLM-based extraction
    _ = params.get("context", "")

    if not answer:
        return {"success": False, "error": "answer parameter is required"}

    manager = get_memory_manager()

    # Simple extraction based on question type
    # This will be enhanced with LLM-based extraction later
    extracted = []

    # Check for name-related questions
    if any(word in question.lower() for word in ["name", "call you", "who are you"]):
        if answer and len(answer) < 100:  # Reasonable name length
            manager.update_profile({"name": answer})
            extracted.append(f"Learned name: {answer}")

    # Check for occupation-related questions
    elif any(
        word in question.lower()
        for word in ["work", "job", "occupation", "profession", "do for a living"]
    ):
        if answer:
            manager.update_profile({"occupation": answer})
            extracted.append(f"Learned occupation: {answer}")

    # Check for interest-related questions
    elif any(
        word in question.lower() for word in ["interest", "hobby", "enjoy", "like to do", "fun"]
    ):
        if answer:
            # Split by common delimiters
            import re

            items = re.split(r"[,;]|\band\b", answer)
            for item in items:
                item = item.strip()
                if item and len(item) > 2:
                    manager.add_interest(item)
                    extracted.append(f"Learned interest: {item}")

    # Check for project-related questions
    elif any(word in question.lower() for word in ["project", "working on", "building"]):
        if answer:
            manager.add_work_project(answer)
            extracted.append(f"Learned project: {answer}")

    # Check for preference-related questions
    elif any(word in question.lower() for word in ["prefer", "like better", "rather"]):
        if answer:
            manager.add_preference(answer)
            extracted.append(f"Learned preference: {answer}")

    # Default: add as insight if we couldn't categorize
    else:
        insight = f"Q: {question[:50]}... A: {answer[:100]}"
        manager.add_insight(insight)
        extracted.append("Added as conversation insight")

    return {
        "success": True,
        "extracted": extracted,
    }


@handler("memory.migrate_from_config")
def handle_migrate_from_config(params: dict[str, Any]) -> dict[str, Any]:
    """Migrate user profile from config.json to MEMORY.md.

    This is a one-time migration to move existing user profile data.

    Returns:
        Success status and migration details.
    """
    from src.core.config import get_user_profile

    # Get existing profile from config
    config_profile = get_user_profile()

    if not config_profile:
        return {"success": True, "migrated": False, "message": "No profile in config to migrate"}

    manager = get_memory_manager()

    # Map config fields to memory fields
    profile_data = {}

    if config_profile.get("name"):
        profile_data["name"] = config_profile["name"]

    if config_profile.get("age"):
        profile_data["age"] = config_profile["age"]

    if config_profile.get("languages"):
        profile_data["languages"] = config_profile["languages"]

    # Config has 'interests' as a string, memory has it as a list
    if config_profile.get("interests"):
        interests_str = config_profile["interests"]
        # Split by common delimiters
        import re

        interests = re.split(r"[,;]", interests_str)
        for interest in interests:
            interest = interest.strip()
            if interest:
                manager.add_interest(interest)

    # Config has 'additional_info' which can go to facts
    if config_profile.get("additional_info"):
        manager.add_fact(config_profile["additional_info"])

    if profile_data:
        manager.update_profile(profile_data)

    return {
        "success": True,
        "migrated": True,
        "message": "Profile migrated to MEMORY.md",
        "fields": list(profile_data.keys()),
    }

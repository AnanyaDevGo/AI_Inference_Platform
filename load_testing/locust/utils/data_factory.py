"""
Data factory — random prompt and user data generators for realistic load testing.
Ensures varied payloads that prevent caching from masking real performance issues.
"""
from __future__ import annotations

import random
import string
import uuid

from config import SHORT_PROMPTS, MEDIUM_PROMPTS, LARGE_PROMPTS, MODEL_NAME, MAX_TOKENS


def random_prompt(size: str = "mixed") -> str:
    """
    Return a random prompt based on size category.
    size: "short" | "medium" | "large" | "mixed"
    """
    if size == "short":
        return random.choice(SHORT_PROMPTS)
    if size == "medium":
        return random.choice(MEDIUM_PROMPTS)
    if size == "large":
        return random.choice(LARGE_PROMPTS)
    # mixed: 60% short, 30% medium, 10% large (mimics real usage distribution)
    roll = random.random()
    if roll < 0.60:
        return random.choice(SHORT_PROMPTS)
    if roll < 0.90:
        return random.choice(MEDIUM_PROMPTS)
    return random.choice(LARGE_PROMPTS)


def random_conversation(turns: int = 5) -> list[dict]:
    """
    Build a multi-turn conversation payload to simulate a real chat session.
    Each turn alternates user/assistant messages.
    """
    messages = []
    for i in range(turns):
        messages.append({"role": "user", "content": random_prompt("short")})
        if i < turns - 1:
            # Simulate previous AI response so the context window grows
            messages.append({
                "role": "assistant",
                "content": f"That's a great question. Here is my answer for turn {i + 1}..."
            })
    return messages


def chat_completion_payload(
    prompt: str | None = None,
    stream: bool = False,
    size: str = "mixed",
    max_tokens: int = MAX_TOKENS,
) -> dict:
    """Build an OpenAI-compatible chat completion request body."""
    return {
        "model": MODEL_NAME,
        "messages": [
            {"role": "user", "content": prompt or random_prompt(size)}
        ],
        "stream": stream,
        "max_tokens": max_tokens,
        "temperature": 0.7,
    }


def multi_turn_payload(turns: int = 4, stream: bool = False) -> dict:
    """Build a multi-turn conversation payload."""
    return {
        "model": MODEL_NAME,
        "messages": random_conversation(turns),
        "stream": stream,
        "max_tokens": MAX_TOKENS,
    }


def random_email() -> str:
    """Generate a unique email for registration tests."""
    return f"load_{uuid.uuid4().hex[:8]}@infervoyage.local"


def random_password() -> str:
    """Generate a valid test password."""
    return "Test@" + "".join(random.choices(string.ascii_letters + string.digits, k=10))


def random_org_name() -> str:
    """Generate a unique org name for multi-tenant tests."""
    return f"LoadOrg-{uuid.uuid4().hex[:6]}"

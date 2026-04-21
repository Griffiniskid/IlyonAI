"""Post-processing utilities for agent output."""
import re

_RE_THOUGHT = re.compile(r"^\s*(Thought|Action|Observation|Action Input):.*$", re.MULTILINE)


def clean_agent_output(text: str) -> str:
    """Strip ReAct scaffolding lines from the agent's final answer."""
    return _RE_THOUGHT.sub("", text or "").strip()


def normalize_short_swap_query(text: str) -> str:
    """Normalize terse swap queries like ``Swap SOL->USDC`` into full sentences."""
    m = re.match(
        r"^[^\w]*Swap\s+([A-Z]{2,6})\s*[>→➜-]+\s*([A-Z]{2,6})\s*$",
        text.strip(),
    )
    if m:
        return f"Swap 1 {m.group(1)} for {m.group(2)}"
    return text

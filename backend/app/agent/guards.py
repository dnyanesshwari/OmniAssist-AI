"""Deterministic guards: injection screening, escalation triggers, yes/no parsing. No LLM involved."""
import re

INJECTION = re.compile(
    r"(ignore|disregard|forget|override)\s+(all\s+|any\s+|the\s+|your\s+)?(previous|prior|above|earlier|system)?\s*"
    r"(instructions|rules|prompts?|polic(y|ies)|guidelines)"
    r"|(reveal|show|print|repeat)\s+(me\s+)?(your|the)\s+(system\s+)?(prompt|instructions)"
    r"|\byou\s+are\s+now\b|developer\s+mode|\bjailbreak\b|\bdan\s+mode\b"
    r"|act\s+as\s+(an?\s+)?(admin|administrator|developer|root)"
    r"|customer[_ ]?id\s*[=:]|(as|i\s+am)\s+(an?\s+)?(admin|administrator)\b", re.I)

SENSITIVE = re.compile(
    r"\b(stole|stolen|theft|steal(ing)?|harass\w*|assault\w*|molest\w*|threat(en|ened|ening)\w*|"
    r"inappropriate(ly)?|misbehav\w*|abus(e|ed|ive)\w*|injur\w*|hurt\s+(me|my)|fraud\w*|scam\w*|"
    r"police|lawyer|legal\s+action|consumer\s+court|unsafe)\b", re.I)

HUMAN = re.compile(
    r"\b(human(\s+agent)?|real\s+person|live\s+agent|representative|customer\s+care|"
    r"(talk|speak)\s+(to|with)\s+(a\s+)?(person|someone|agent|manager))\b", re.I)

_YES_CORE = {"yes", "y", "yeah", "yep", "yup", "sure", "ok", "okay", "confirm", "confirmed", "haan", "ha", "ji"}
_YES_FILL = _YES_CORE | {"please", "go", "ahead", "do", "it", "thanks", "thank", "you", "theek", "hai", "book", "that"}
_NO_CORE = {"no", "nope", "nah", "nahi", "stop", "dont", "don't", "never", "mind"}
_NO_FILL = _NO_CORE | {"please", "thanks", "thank", "you", "it", "that", "na", "keep", "cancel"}


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z']+", text.lower())


def is_injection(text: str) -> bool:
    return bool(INJECTION.search(text))


def escalation_reason(text: str) -> str | None:
    if SENSITIVE.search(text):
        return "sensitive_complaint"
    if HUMAN.search(text):
        return "customer_request"
    return None


def parse_yes_no(text: str) -> str | None:
    """Strict: only short, unambiguous replies count. 'yes but make it 5pm' -> None."""
    toks = _tokens(text)
    if not toks or len(toks) > 5:
        return None
    if set(toks) <= _YES_FILL and set(toks) & _YES_CORE:
        return "yes"
    if set(toks) <= _NO_FILL and set(toks) & _NO_CORE:
        return "no"
    return None

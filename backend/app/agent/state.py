import operator
from typing import Annotated, Any, TypedDict


class AgentState(TypedDict, total=False):
    # inputs (set by runner; identity always comes from auth, never from the LLM)
    customer_id: int
    conversation_id: int
    user_text: str
    modality: str
    history: list[dict]
    simulate: str | None
    # persisted across turns (stored in conversations.state)
    slots: dict
    pending: dict | None
    failures: int
    # per-turn outputs
    intent: str
    query: str
    reply: str
    citations: list[dict]
    appointment: dict | None
    handoff: str | None          # reason, when escalation is needed
    handoff_ticket_id: int | None
    tool_calls: Annotated[list[dict], operator.add]
    abstained: bool

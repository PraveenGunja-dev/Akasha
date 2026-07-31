from __future__ import annotations

from typing import Annotated, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class AkashaState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    conversation_summary: NotRequired[str | None]
    user_id: NotRequired[str]
    tenant_id: NotRequired[str]
    session_id: NotRequired[str]
    user_role: NotRequired[str]
    owner_key: NotRequired[str]
    run_id: NotRequired[str]
    request_id: NotRequired[str]
    current_user_message_id: NotRequired[int]
    current_assistant_message_id: NotRequired[int]
    transcript_cursor: NotRequired[int]
    active_project_ids: NotRequired[list[str]]
    intent: NotRequired[str | None]
    requested_domains: NotRequired[list[str]]
    tool_names: NotRequired[list[str]]
    evidence: NotRequired[list[dict]]
    visualizations: NotRequired[list[dict]]
    turn_status: NotRequired[str]
    model_name: NotRequired[str | None]
    agent_iterations: NotRequired[int]

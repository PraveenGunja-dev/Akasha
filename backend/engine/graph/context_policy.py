from __future__ import annotations

from dataclasses import dataclass

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, ToolMessage
from langchain_core.messages.utils import count_tokens_approximately


@dataclass(frozen=True)
class ContextBudget:
    context_window: int
    output_reserve: int = 2_048
    system_and_tools_reserve: int = 4_096
    summarize_at: float = 0.60
    hard_limit_at: float = 0.80
    minimum_recent_turns: int = 4

    @property
    def usable_tokens(self) -> int:
        return max(1_024, self.context_window - self.output_reserve - self.system_and_tools_reserve)

    @property
    def summary_threshold(self) -> int:
        return int(self.usable_tokens * self.summarize_at)

    @property
    def hard_threshold(self) -> int:
        return int(self.usable_tokens * self.hard_limit_at)


@dataclass(frozen=True)
class CompactionPlan:
    messages_to_summarize: list[BaseMessage]
    messages_to_keep: list[BaseMessage]
    estimated_tokens: int
    requires_hard_trim: bool


def group_complete_turns(messages: list[BaseMessage]) -> list[list[BaseMessage]]:
    """Group messages on human boundaries without splitting AI/tool exchanges."""
    turns: list[list[BaseMessage]] = []
    current: list[BaseMessage] = []
    for message in messages:
        if isinstance(message, HumanMessage) and current:
            turns.append(current)
            current = []
        current.append(message)
    if current:
        turns.append(current)
    return turns


def tool_groups_are_complete(messages: list[BaseMessage]) -> bool:
    pending: set[str] = set()
    for message in messages:
        if isinstance(message, AIMessage):
            if pending:
                return False
            pending = {
                str(call.get("id"))
                for call in (message.tool_calls or [])
                if call.get("id") is not None
            }
        elif isinstance(message, ToolMessage):
            call_id = str(message.tool_call_id)
            if call_id not in pending:
                return False
            pending.remove(call_id)
        elif pending:
            return False
    return not pending


def build_compaction_plan(
    messages: list[BaseMessage],
    budget: ContextBudget,
) -> CompactionPlan | None:
    estimated = count_tokens_approximately(messages)
    if estimated <= budget.summary_threshold:
        return None

    turns = group_complete_turns(messages)
    keep_count = min(len(turns), budget.minimum_recent_turns)
    old_turns = turns[:-keep_count] if keep_count else turns
    recent_turns = turns[-keep_count:] if keep_count else []
    old_messages = [message for turn in old_turns for message in turn]
    kept_messages = [message for turn in recent_turns for message in turn]

    return CompactionPlan(
        messages_to_summarize=old_messages,
        messages_to_keep=kept_messages,
        estimated_tokens=estimated,
        requires_hard_trim=estimated > budget.hard_threshold,
    )


def render_summary_input(messages: list[BaseMessage], max_chars: int = 80_000) -> str:
    lines = []
    for message in messages:
        role = getattr(message, "type", "message")
        content = message.content if isinstance(message.content, str) else str(message.content)
        lines.append(f"{role}: {content}")
    return "\n".join(lines)[:max_chars]


def bound_recent_messages(messages: list[BaseMessage], max_chars_per_message: int) -> list[BaseMessage]:
    """Bound payload size while retaining complete turn and tool-call structure."""
    bounded: list[BaseMessage] = []
    for message in messages:
        content = message.content
        if isinstance(content, str) and len(content) > max_chars_per_message:
            content = content[:max_chars_per_message] + "\n[Context payload truncated]"
            bounded.append(message.model_copy(update={"content": content}))
        else:
            bounded.append(message)
    return bounded

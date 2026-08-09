from __future__ import annotations

import logging
import os
import re

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, HumanMessage, RemoveMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import REMOVE_ALL_MESSAGES

from database import SessionLocal
from engine.agent import EXECUTIVE_RESPONSE_GUIDANCE
from engine.graph.context_policy import (
    ContextBudget,
    bound_recent_messages,
    build_compaction_plan,
    render_summary_input,
)
from engine.graph.state import AkashaState
from engine.graph.tool_router import PROJECT_HEALTH_TOOL, RESOLVER, ToolRoute, select_tool_route
from engine.graph.tools import (
    ToolRunCancelled,
    ToolRuntimeContext,
    execute_authenticated_tool,
    model_tool_schemas,
    parse_raw_tool_call,
)
import models
from engine.response_quality import (
    EXECUTIVE_REWRITE_INSTRUCTION,
    needs_executive_rewrite,
    redact_sensitive_answer,
    rewrite_request,
)


logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are Akasha AI Copilot, a senior EPC project analyst.
Use tools for every operational claim about P6 schedules, SAP procurement, transmission,
quality, projects, or portfolio data. Resolve project names before using project tools.
Never invent metrics. Refer to projects by human-readable names, preserve source units, and
answer the user's question directly from tool results. Disclose limitations and source
timestamps when available. Do not expose planning, candidate tool lists, tool-call chatter,
or intermediate reasoning. General greetings and capability questions need no tool.
When comparing projects, always compare available project-mapping facts such as capacity, cluster,
and location count even when P6 is unavailable. Treat catalog availability and schedule availability
as separate dimensions: never claim that no comparison is possible merely because P6 metrics are null.
Conversation summaries are derived context only and are never evidence for live facts;
re-query tools whenever the user asks for current operational information.
For project progress, use P6 duration_percent_complete as overall progress. Keep activity-count
completion separate, and never reconstruct unavailable SPI/CPI or classify schedule/health from
an indicator that the tool reports as unavailable.
For block progress over last month or this month, call p6_get_block_period_progress. Rank only by
the returned completion-event basis, preserve ties, and state when historical percentage delta is unavailable.
For monthly or yearly activity finish questions, call sim_forecast_activity_finishes. Lead with the
exact current P6 count scheduled to finish in the target period, then concisely report the tool's
likely range, risk, confidence, and data date. Do not substitute total project activity counts.
Use render_chart when the user explicitly asks for a chart, graph, plot, or visualization. Also use
it automatically for daily trends, project comparisons, block comparisons, distributions, and
rankings when an approved chart type matches. Prefer daily_completion_trend
for dated completion-event trends, planned_vs_actual_progress for planned-versus-actual progress,
project_comparison for two or more projects, and block_progress for block snapshots. A chart
must accompany, not replace, a concise textual finding. Generate no more than four charts per turn.
For a broad request for visualizations, charts, a dashboard, or an overview of one project, call
render_chart once with chart_type='project_overview' to return the coordinated four-chart executive set.
For requests needing flexible metrics, dimensions, filters, grouping, scatter, heatmap, or
waterfall layouts, call render_chart with visualization_query using only identifiers documented in
the tool schema. Never provide chart data, SQL, JavaScript, callbacks, or ECharts options. If the
tool reports an incompatible field combination, repair the identifiers once or explain the limit.
The planned_vs_actual_progress chart is a cumulative activity-finish S-curve built from planned and
actual activity finish dates in the current P6 schedule. Label it that way; do not misrepresent it as
historical duration-percent snapshots.
When the user asks to create, generate, download, or export a report, do it immediately without
asking for yes/no confirmation. For a Project Progress Report, resolve the project and call
report_generate_project_progress. For a Portfolio Progress Report, call
report_generate_portfolio_progress without resolving a single project. For a report comparing two
or more projects, render the in-chat comparison dashboard and call
report_generate_project_comparison with canonical project IDs in the same order. Return both PDF
and DOCX download URLs exactly as Markdown links and state their expiry. Use a report_preview tool
only when the user explicitly asks to preview or review the report scope before files are created.

""" + EXECUTIVE_RESPONSE_GUIDANCE


class GraphRunCancelled(RuntimeError):
    pass


class InvalidModelResponse(RuntimeError):
    pass


def _response_text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if isinstance(block, str):
            parts.append(block)
        elif isinstance(block, dict):
            text = block.get("text") or block.get("content")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts).strip()


def _contains_raw_tool_markup(content: str) -> bool:
    return bool(re.search(r"<\s*(?:tool_call\b|function\s*=)", content, re.IGNORECASE))


def _response_model_name(response: AIMessage) -> str | None:
    metadata = response.response_metadata or {}
    for key in ("model_name", "model", "model_id"):
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _ensure_run_active(state: AkashaState) -> None:
    run_id = state.get("run_id")
    if not run_id:
        return
    db = SessionLocal()
    try:
        status = db.query(models.ChatRun.status).filter(models.ChatRun.run_id == run_id).scalar()
        if status in {"cancel_requested", "cancelled", "interrupted"}:
            raise GraphRunCancelled("Chat run was cancelled.")
    finally:
        db.close()


def _runtime(state: AkashaState) -> ToolRuntimeContext:
    return ToolRuntimeContext(
        user_id=state["user_id"],
        tenant_id=state["tenant_id"],
        role=state["user_role"],
        session_id=state["session_id"],
        run_id=state["run_id"],
        request_id=state["request_id"],
        active_project_ids=tuple(state.get("active_project_ids") or []),
    )


def build_chat_graph(
    model: BaseChatModel,
    checkpointer=None,
    *,
    context_window: int | None = None,
):
    if context_window is None:
        profile = getattr(model, "profile", None) or {}
        context_window = int(profile.get("max_input_tokens") or 0)
    if context_window < 8_192:
        raise ValueError(
            "The selected model context window could not be resolved or is below 8192 tokens."
        )
    budget = ContextBudget(context_window=context_window)
    all_tool_schemas = model_tool_schemas()
    all_tool_names = tuple(
        str((schema.get("function") or {}).get("name") or "")
        for schema in all_tool_schemas
        if (schema.get("function") or {}).get("name")
    )
    non_health_tool_names = tuple(
        name for name in all_tool_names if name != PROJECT_HEALTH_TOOL
    )
    schemas_by_name = {
        str(schema["function"]["name"]): schema
        for schema in all_tool_schemas
    }
    all_tool_model = model.bind_tools(all_tool_schemas)
    routed_models = {all_tool_names: all_tool_model}
    max_model_calls = int(os.getenv("AKASHA_GRAPH_MAX_MODEL_CALLS", "12"))
    if max_model_calls < 2 or max_model_calls > 30:
        raise ValueError("AKASHA_GRAPH_MAX_MODEL_CALLS must be between 2 and 30.")

    def model_for_route(route: ToolRoute):
        if not route.tool_names:
            return model
        cached = routed_models.get(route.tool_names)
        if cached is None:
            schemas = [schemas_by_name[name] for name in route.tool_names]
            cached = model.bind_tools(schemas)
            routed_models[route.tool_names] = cached
        return cached

    def route_for_state(state: AkashaState) -> ToolRoute:
        human_messages = [
            _response_text(message.content)
            for message in state.get("messages") or []
            if isinstance(message, HumanMessage)
        ]
        latest_question = human_messages[-1] if human_messages else ""
        prior_questions = human_messages[:-1][-3:]
        context_parts = [*(prior_questions or [])]
        if state.get("conversation_summary"):
            context_parts.append(str(state["conversation_summary"]))
        return select_tool_route(
            latest_question,
            context="\n".join(context_parts),
            available_tool_names=all_tool_names,
        )

    def validate_context(state: AkashaState) -> dict:
        _ensure_run_active(state)
        expected_owner = f"{state['tenant_id']}:{state['user_id']}"
        persisted_owner = state.get("owner_key")
        if persisted_owner and persisted_owner != expected_owner:
            raise PermissionError("Conversation checkpoint ownership mismatch.")
        return {"owner_key": expected_owner, "turn_status": "running"}

    def compact_context(state: AkashaState) -> dict:
        _ensure_run_active(state)
        messages = list(state.get("messages") or [])
        plan = build_compaction_plan(messages, budget)
        if plan is None or not plan.messages_to_summarize:
            return {}

        previous_summary = state.get("conversation_summary") or ""
        prompt = (
            "Summarize the older conversation for continuity. Preserve stable project selections, "
            "user instructions, unresolved questions, and decisions. Do not present operational "
            "numbers as current evidence.\n\nExisting summary:\n"
            f"{previous_summary}\n\nOlder conversation:\n"
            f"{render_summary_input(plan.messages_to_summarize)}"
        )
        try:
            summary_response = model.invoke([
                SystemMessage(content="Produce a concise derived conversation summary."),
                SystemMessage(content=prompt),
            ])
            summary = str(summary_response.content)
        except Exception as exc:
            logger.warning("Conversation summarization failed (%s)", type(exc).__name__)
            if not plan.requires_hard_trim:
                return {}
            summary = previous_summary or "Older context was compacted after summarization was unavailable."

        max_chars = max(2_000, int((budget.hard_threshold * 4) / max(1, len(plan.messages_to_keep))))
        kept = bound_recent_messages(plan.messages_to_keep, max_chars)
        return {
            "conversation_summary": summary,
            "messages": [RemoveMessage(id=REMOVE_ALL_MESSAGES), *kept],
        }

    def call_model(state: AkashaState) -> dict:
        _ensure_run_active(state)
        iteration = int(state.get("agent_iterations") or 0) + 1
        force_final = iteration >= max_model_calls
        route = route_for_state(state)
        recovery_model = (
            all_tool_model
            if PROJECT_HEALTH_TOOL in route.tool_names
            else model_for_route(ToolRoute(non_health_tool_names, ("all",), "recovery", True, False))
        )
        if iteration == 1:
            logger.info(
                "Selected tool route (request_id=%s intent=%s domains=%s tool_count=%s all_tools=%s)",
                state.get("request_id"),
                route.intent,
                ",".join(route.domains),
                len(route.tool_names),
                route.uses_all_tools,
            )
        system_content = SYSTEM_PROMPT
        if state.get("conversation_summary"):
            system_content += f"\n\nDerived conversation summary:\n{state['conversation_summary']}"
        if force_final:
            system_content += (
                "\n\nThe tool-call budget for this turn is exhausted. Do not request more tools. "
                "Produce the best complete answer possible from tool results already present. "
                "Clearly disclose any requested scope that was not checked rather than guessing."
            )
        model_messages = [
            SystemMessage(content=system_content),
            *(state.get("messages") or []),
        ]
        active_model = model if force_final else model_for_route(route)
        response = active_model.invoke(model_messages)
        response_text = _response_text(response.content)
        raw_markup = _contains_raw_tool_markup(response_text)

        executed_tools = set(state.get("tool_names") or [])
        required_evidence_tools = set(route.required_evidence_tools)
        missing_evidence_tools = required_evidence_tools - executed_tools
        route_requires_domain_evidence = any(name != RESOLVER for name in route.tool_names)
        has_relevant_evidence = (
            not missing_evidence_tools
            if required_evidence_tools
            else any(name != RESOLVER for name in executed_tools)
            if route_requires_domain_evidence
            else bool(executed_tools)
        )
        if (
            not force_final
            and route.operational
            and not has_relevant_evidence
            and not response.tool_calls
            and not response.invalid_tool_calls
            and response_text
            and not raw_markup
        ):
            logger.warning(
                "Retrying operational answer with required evidence tools after no evidence call "
                "(request_id=%s iteration=%s intent=%s)",
                state.get("request_id"),
                iteration,
                route.intent,
            )
            evidence_recovery_model = recovery_model
            next_evidence_tools = set(missing_evidence_tools)
            if (
                missing_evidence_tools
                and RESOLVER in route.tool_names
                and RESOLVER not in executed_tools
            ):
                next_evidence_tools = {RESOLVER}
            if next_evidence_tools:
                evidence_recovery_model = model.bind_tools(
                    [schemas_by_name[name] for name in sorted(next_evidence_tools)],
                    tool_choice="required",
                )
            response = evidence_recovery_model.invoke([
                SystemMessage(content=(
                    "The latest request is operational and requires current evidence, but the prior "
                    "attempt did not call a data tool. Re-answer now using the supplied tool "
                    "catalog. Resolve project names first when needed. "
                    + (
                        "You must call the following next evidence tool before answering: "
                        f"{', '.join(sorted(next_evidence_tools))}. A generic project summary "
                        "does not contain the requested period ranking. "
                        if next_evidence_tools else ""
                    )
                    + "Do not answer from memory or describe tool availability."
                )),
                *model_messages,
            ])
            response_text = _response_text(response.content)
            raw_markup = _contains_raw_tool_markup(response_text)
            if (
                missing_evidence_tools
                and not response.tool_calls
                and not response.invalid_tool_calls
                and response_text
                and not raw_markup
            ):
                raise InvalidModelResponse(
                    "The model answered without calling the required evidence tool."
                )
        parsed_raw_call = parse_raw_tool_call(response_text) if raw_markup else None
        if parsed_raw_call is not None and parsed_raw_call[0] not in route.tool_names:
            parsed_raw_call = None

        if parsed_raw_call is not None and not force_final:
            name, arguments = parsed_raw_call
            logger.warning(
                "Normalized provider tool markup (request_id=%s iteration=%s tool=%s)",
                state.get("request_id"), iteration, name,
            )
            response = AIMessage(
                content="",
                tool_calls=[{
                    "name": name,
                    "args": arguments,
                    "id": f"normalized-{state.get('request_id')}-{iteration}",
                }],
                response_metadata=response.response_metadata,
            )
        elif not force_final and (response.invalid_tool_calls or raw_markup or (not response_text and not response.tool_calls)):
            reason = (
                "invalid_native_tool_call" if response.invalid_tool_calls else
                "raw_tool_markup" if raw_markup else "empty_response"
            )
            logger.warning(
                "Retrying invalid provider response with tools enabled "
                "(request_id=%s iteration=%s reason=%s)",
                state.get("request_id"), iteration, reason,
            )
            repair_model = recovery_model if route.operational else model
            response = repair_model.invoke([
                SystemMessage(content=(
                    "Your previous response was not usable. Re-answer the latest user request now. "
                    "Use only provider-native tool calls from the supplied tool definitions when data "
                    "is needed. Do not emit XML, tool-call markup, candidate actions, or an empty response."
                )),
                *model_messages,
            ])
            response_text = _response_text(response.content)
            raw_markup = _contains_raw_tool_markup(response_text)
            parsed_raw_call = parse_raw_tool_call(response_text) if raw_markup else None
            if parsed_raw_call is not None and parsed_raw_call[0] not in route.tool_names:
                parsed_raw_call = None
            if parsed_raw_call is not None:
                name, arguments = parsed_raw_call
                logger.warning(
                    "Normalized repaired provider tool markup "
                    "(request_id=%s iteration=%s tool=%s)",
                    state.get("request_id"), iteration, name,
                )
                response = AIMessage(
                    content="",
                    tool_calls=[{
                        "name": name,
                        "args": arguments,
                        "id": f"normalized-repair-{state.get('request_id')}-{iteration}",
                    }],
                    response_metadata=response.response_metadata,
                )
            elif response.invalid_tool_calls or raw_markup or (not response_text and not response.tool_calls):
                repaired_reason = (
                    "invalid_native_tool_call" if response.invalid_tool_calls else
                    "raw_tool_markup" if raw_markup else "empty_response"
                )
                logger.warning(
                    "Provider response remained invalid after tool-enabled retry "
                    "(request_id=%s iteration=%s reason=%s)",
                    state.get("request_id"), iteration, repaired_reason,
                )
                raise InvalidModelResponse("The model returned an invalid response after tool-enabled repair.")
        elif response.invalid_tool_calls:
            raise InvalidModelResponse("The model returned invalid tool calls.")
        if not response.tool_calls and state.get("current_assistant_message_id"):
            response.id = f"chat-message:{state['current_assistant_message_id']}"
        return {
            "messages": [response],
            "model_name": _response_model_name(response) or state.get("model_name"),
            "agent_iterations": iteration,
            "intent": route.intent,
            "requested_domains": list(route.domains),
        }

    def call_tools(state: AkashaState) -> dict:
        _ensure_run_active(state)
        last_message = state["messages"][-1]
        if not isinstance(last_message, AIMessage):
            raise RuntimeError("Tool node requires an AI message.")

        results = []
        visualizations = list(state.get("visualizations") or [])
        tool_names = list(state.get("tool_names") or [])
        evidence = list(state.get("evidence") or [])
        runtime = _runtime(state)
        for call in last_message.tool_calls:
            name = str(call.get("name") or "")
            try:
                execution = execute_authenticated_tool(name, call.get("args") or {}, runtime)
            except ToolRunCancelled as exc:
                raise GraphRunCancelled(str(exc)) from exc
            results.append(ToolMessage(
                content=execution.content,
                tool_call_id=str(call.get("id")),
                name=name,
                status="error" if execution.status == "error" else "success",
            ))
            if name and name not in tool_names:
                tool_names.append(name)
            emitted = execution.visualizations or (
                (execution.visualization,) if execution.visualization is not None else ()
            )
            for visualization in emitted:
                if len(visualizations) >= 4:
                    break
                visualizations.append(visualization)
            for item in execution.evidence:
                evidence_item = {**item, "tool_call_id": str(call.get("id"))}
                if evidence_item not in evidence:
                    evidence.append(evidence_item)
        return {
            "messages": results,
            "tool_names": tool_names,
            "evidence": evidence,
            "visualizations": visualizations,
        }

    def continue_agent(state: AkashaState) -> str:
        last_message = state["messages"][-1]
        return "tools" if isinstance(last_message, AIMessage) and last_message.tool_calls else "end"

    agent = StateGraph(AkashaState)
    agent.add_node("model", call_model)
    agent.add_node("tools", call_tools)
    agent.add_edge(START, "model")
    agent.add_conditional_edges("model", continue_agent, {"tools": "tools", "end": END})
    agent.add_edge("tools", "model")
    agent_subgraph = agent.compile()

    def finalize(state: AkashaState) -> dict:
        _ensure_run_active(state)
        last_message = state["messages"][-1]
        if not isinstance(last_message, AIMessage) or last_message.tool_calls:
            raise InvalidModelResponse("The graph did not produce a final synthesis response.")
        content = _response_text(last_message.content)
        repair_model_name = None
        if not content or _contains_raw_tool_markup(content):
            repaired = model.invoke([
                SystemMessage(content=(
                    "Answer the user's latest question directly and concisely for an executive reader from the supplied "
                    "conversation and tool results. Do not call tools, expose reasoning, emit tool-call "
                    "markup, discuss internal capabilities, or return an empty response. Include only "
                    "facts relevant to the request and do not add unsolicited next steps or offers. If "
                    "the available evidence did not provide the requested detail, state only which "
                    "business data is unavailable instead of inventing a tool call."
                )),
                *(state.get("messages") or []),
            ])
            content = _response_text(repaired.content)
            repair_model_name = _response_model_name(repaired)
        if not content or _contains_raw_tool_markup(content):
            raise InvalidModelResponse("The model returned an invalid final answer after repair.")

        latest_question = next(
            (
                _response_text(message.content)
                for message in reversed(state.get("messages") or [])
                if isinstance(message, HumanMessage)
            ),
            "",
        )
        if needs_executive_rewrite(latest_question, content):
            try:
                rewritten = model.invoke([
                    SystemMessage(content=EXECUTIVE_REWRITE_INSTRUCTION),
                    HumanMessage(content=rewrite_request(latest_question, content)),
                ])
                candidate = _response_text(rewritten.content)
                if (
                    candidate
                    and not _contains_raw_tool_markup(candidate)
                    and not needs_executive_rewrite(latest_question, candidate)
                ):
                    content = candidate
                    repair_model_name = _response_model_name(rewritten) or repair_model_name
                else:
                    logger.warning(
                        "Executive answer rewrite did not satisfy quality guard (request_id=%s)",
                        state.get("request_id"),
                    )
            except Exception as exc:
                logger.warning(
                    "Executive answer rewrite failed (request_id=%s error=%s)",
                    state.get("request_id"),
                    type(exc).__name__,
                )
        content = redact_sensitive_answer(content)
        if not content:
            raise InvalidModelResponse("The final answer contained only protected internal data.")
        final_message = AIMessage(
            content=content,
            id=f"chat-message:{state['current_assistant_message_id']}",
        )
        return {
            "messages": [final_message],
            "turn_status": "completed",
            "model_name": repair_model_name or state.get("model_name"),
        }

    parent = StateGraph(AkashaState)
    parent.add_node("validate_context", validate_context)
    parent.add_node("compact_context", compact_context)
    parent.add_node("agent", agent_subgraph)
    parent.add_node("finalize", finalize)
    parent.add_edge(START, "validate_context")
    parent.add_edge("validate_context", "compact_context")
    parent.add_edge("compact_context", "agent")
    parent.add_edge("agent", "finalize")
    parent.add_edge("finalize", END)
    return parent.compile(checkpointer=checkpointer)

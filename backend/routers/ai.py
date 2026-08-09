from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator
import os
import json
import logging
import re
import time
import uuid
from database import get_db
import models
from services.project_service import calculate_project_360_metrics
from engine.orchestrator import ChatOrchestrator, ChatResponse
from engine.graph import chat_graph_service, select_chat_engine
from engine.graph.builder import GraphRunCancelled
from engine.observability import (
    log_observability_event,
    resolve_request_id,
    safe_exception_trace,
    serialize_sse_event,
)
from engine.simulation_directives import (
    DirectiveValidationError,
    SIMULATION_DIRECTIVE_CODES,
    build_simulation_directives,
)
from engine.model_provider import configured_provider_name, get_model_provider
from engine.provider_errors import classify_provider_error
from auth_claims import AuthenticatedIdentity
from routers.chat_sessions import build_agent_history, get_owned_session
from security import get_current_user
from services.chat_run_service import (
    chat_run_is_cancelled,
    complete_chat_run,
    create_chat_run,
    finish_chat_run,
    request_chat_run_cancellation,
)
from services.chat_feedback_service import submit_message_feedback
from dotenv import load_dotenv

load_dotenv(override=False)

router = APIRouter(prefix="/api")
logger = logging.getLogger(__name__)

orchestrator = ChatOrchestrator(default_llm=configured_provider_name())

from typing import Optional, List

class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(default="", max_length=20_000)
    projectId: Optional[str] = None
    sessionId: str = Field(pattern=r"^[a-f0-9]{32}$")
    isDeepAnalysis: bool = False
    imageData: Optional[str] = Field(default=None, max_length=15_000_000)

    @model_validator(mode="after")
    def validate_content(self):
        if not self.message.strip() and not self.imageData:
            raise ValueError("A message or image is required.")
        return self

class FeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    messageId: int
    feedbackType: Literal["thumbs_up", "thumbs_down"]

def call_azure_openai_curl(messages, temperature, max_tokens, json_response=False):
    result = get_model_provider("azure").invoke(
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=json_response,
    )
    return result.content


def get_ai_provider():
    from dotenv import load_dotenv
    load_dotenv(override=False)
    return configured_provider_name()

def call_openrouter(messages, temperature=0.7, max_tokens=2048, json_response=False, stream=False):
    provider = get_model_provider("openrouter")
    response = provider.create_completion(
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=json_response,
        stream=stream,
    )
    if stream:
        return response
    return response.choices[0].message.content

def call_groq(messages, temperature=0.7, max_tokens=2048, json_response=False, stream=False):
    chat_completion = get_model_provider("groq").create_completion(
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=json_response,
        stream=stream,
    )
    if stream:
        return chat_completion
    return chat_completion.choices[0].message.content

def call_ollama(messages, temperature, max_tokens, json_response=False, stream=False):
    response = get_model_provider("ollama").create_completion(
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=json_response,
        stream=stream,
    )
    return response if stream else response.choices[0].message.content

def call_configured_llm(messages, temperature=0.7, max_tokens=2048, json_response=False, stream=False):
    response = get_model_provider().create_completion(
        messages,
        temperature=temperature,
        max_tokens=max_tokens,
        json_mode=json_response,
        stream=stream,
    )
    return response if stream else response.choices[0].message.content


@router.post("/chat")
def chat_with_copilot(
    req: ChatRequest,
    db: Session = Depends(get_db),
    user: AuthenticatedIdentity = Depends(get_current_user),
):
    """Stream one owned conversation turn through the selected server-side engine."""
    request_id = resolve_request_id()
    session_id = req.sessionId
    started_at = time.perf_counter()
    tool_names = []

    db_session = get_owned_session(db, user, session_id)
    history_rows = db.query(models.ChatMessage).filter(
        models.ChatMessage.session_id == session_id
    ).order_by(models.ChatMessage.created_at.asc(), models.ChatMessage.id.asc()).all()
    history = build_agent_history(history_rows)
    engine_name = select_chat_engine(db_session, user.tenant_id, user.subject)
    run_id = uuid.uuid4().hex
    user_msg, assistant_msg, _run = create_chat_run(
        db,
        session=db_session,
        user=user,
        request_id=request_id,
        run_id=run_id,
        engine=engine_name,
        content=req.message if req.message.strip() else "[Image attachment]",
    )
    user_message_id = user_msg.id
    assistant_message_id = assistant_msg.id

    log_observability_event(
        logger,
        "chat_started",
        request_id=request_id,
        session_id=session_id,
        elapsed_ms=0,
        response_intent=engine_name,
        tool_names=tool_names,
        run_id=run_id,
        chat_engine=engine_name,
    )
    
    # We pass the projectId as a hint to the intent classifier if provided by the UI
    project_names = [req.projectId] if req.projectId else None
    
    try:
        # We need to stream the response
        from fastapi.responses import StreamingResponse
        
        def event_stream():
            response_intent = "deep_analysis"
            visualizations = []
            full_content = ""
            terminal = False
            sequence = 0

            def event(event_type: str, **payload):
                nonlocal sequence
                sequence += 1
                return serialize_sse_event(
                    event_type,
                    request_id,
                    stream_version="2.0",
                    sequence=sequence,
                    session_id=session_id,
                    run_id=run_id,
                    **payload,
                )

            try:
                yield event(
                    "start",
                    user_message_id=user_message_id,
                    assistant_message_id=assistant_message_id,
                    engine=engine_name,
                )
                yield event(
                    "status",
                    status="running",
                    engine=engine_name,
                )
                checkpoint_id = None
                response_obj = None
                evidence = []

                if engine_name == "langgraph":
                    graph_message = req.message
                    if req.imageData:
                        from engine.agent import analyze_image_context
                        image_context = analyze_image_context(
                            req.imageData,
                            req.message,
                            request_id=request_id,
                            session_id=session_id,
                        )
                        graph_message = (
                            f"[IMAGE CONTEXT EXTRACTED BY VISION MODEL: {image_context}]\n\n"
                            f"User Question: {req.message}"
                        )
                    graph_result = chat_graph_service.run(
                        session_id=session_id,
                        user_id=user.subject,
                        tenant_id=user.tenant_id,
                        role=user.role,
                        run_id=run_id,
                        request_id=request_id,
                        user_message_id=user_message_id,
                        assistant_message_id=assistant_message_id,
                        message=graph_message,
                        history_rows=history_rows,
                        active_project_ids=[req.projectId] if req.projectId else [],
                    )
                    tool_names.extend(graph_result.tool_names)
                    evidence.extend(graph_result.evidence)
                    visualizations.extend(graph_result.visualizations)
                    checkpoint_id = graph_result.checkpoint_id
                    full_content = graph_result.content
                    response_obj = ChatResponse(
                        content=full_content,
                        intent_type="deep_analysis",
                        project_ids=project_names or [],
                        domains=[],
                        data_as_of=None,
                        sources_used=tool_names,
                        latency_ms=int((time.perf_counter() - started_at) * 1000),
                    )
                else:
                    legacy_content = ""
                    for chunk in orchestrator.process_message_stream(
                        db=db,
                        message=req.message,
                        session_id=session_id,
                        history=history,
                        project_names=project_names,
                        is_deep_analysis=True,
                        image_data=req.imageData,
                        request_id=request_id,
                        tool_names_out=tool_names,
                        evidence_out=evidence,
                    ):
                        if chat_run_is_cancelled(db, run_id):
                            raise GraphRunCancelled("Chat run was cancelled.")
                        if isinstance(chunk, dict) and chunk.get("type") == "metadata":
                            response_obj = chunk["response"]
                            response_intent = response_obj.intent_type
                        elif isinstance(chunk, dict) and chunk.get("type") == "visualization":
                            visualization = {
                                "schema_version": chunk.get("schema_version"),
                                "chart_type": chunk.get("chart_type"),
                                "title": chunk.get("title"),
                                "subtitle": chunk.get("subtitle"),
                                "summary": chunk.get("summary"),
                                "accessibility_description": chunk.get("accessibility_description"),
                                "data_as_of": chunk.get("data_as_of"),
                                "data_table": chunk.get("data_table"),
                                "spec": chunk.get("spec"),
                            }
                            if len(visualizations) < 4:
                                visualizations.append(visualization)
                        elif not isinstance(chunk, dict):
                            legacy_content += chunk

                    full_content = legacy_content
                    response_obj.content = full_content

                if response_obj is None:
                    raise RuntimeError("Chat engine completed without response metadata.")
                if chat_run_is_cancelled(db, run_id):
                    raise GraphRunCancelled("Chat run was cancelled.")

                asst_msg = complete_chat_run(
                    db,
                    run_id=run_id,
                    content=response_obj.content,
                    intent_type=response_obj.intent_type,
                    project_ids=response_obj.project_ids,
                    domains=response_obj.domains,
                    data_as_of=response_obj.data_as_of,
                    sources=response_obj.sources_used,
                    evidence=evidence,
                    visualizations=visualizations,
                    latency_ms=response_obj.latency_ms,
                    checkpoint_id=checkpoint_id,
                    model_name=graph_result.model_name if engine_name == "langgraph" else None,
                )
                terminal = True
                for visualization in visualizations:
                    yield event("visualization", **visualization)
                for token in re.split(r"(\n)", full_content):
                    if token:
                        yield event("token", content=token)
                suggestions = ["Give me the specific numbers", "What are the biggest risks?", "Summarize material gaps"]
                if response_obj.intent_type == "factual":
                    suggestions = ["Why is that?", "Compare this to baseline", "Show me the trend"]
                elif response_obj.intent_type == "analytical":
                    suggestions = ["What should we do about it?", "Who is responsible?", "Show detailed breakdown"]

                elapsed_ms = int((time.perf_counter() - started_at) * 1000)
                log_observability_event(
                    logger,
                    "chat_completed",
                    request_id=request_id,
                    session_id=session_id,
                    elapsed_ms=elapsed_ms,
                    response_intent=response_intent,
                    tool_names=tool_names,
                    run_id=run_id,
                    chat_engine=engine_name,
                    model_name=graph_result.model_name if engine_name == "langgraph" else None,
                )
                yield event(
                    "metadata",
                    metadata={
                        "message_id": asst_msg.id,
                        "data_as_of": asst_msg.data_as_of.isoformat() if asst_msg.data_as_of else None,
                        "last_synced_at": (asst_msg.sources_used or {}).get("last_synced_at"),
                        "answer_generated_at": (asst_msg.sources_used or {}).get("answer_generated_at"),
                        "source_freshness": (asst_msg.sources_used or {}).get("systems", []),
                        "evidence": (asst_msg.sources_used or {}).get("evidence", []),
                        "provenance": asst_msg.sources_used or {},
                        "latency_ms": response_obj.latency_ms,
                        "intent": response_obj.intent_type,
                        "sources": (asst_msg.sources_used or {}).get("tables", []),
                        "session_id": session_id,
                        "run_id": run_id,
                        "engine": engine_name,
                        "model": graph_result.model_name if engine_name == "langgraph" else None,
                    },
                    suggestions=suggestions,
                )
                yield event("done", message_id=asst_msg.id, status="completed", engine=engine_name)
            except (GraphRunCancelled, GeneratorExit) as exc:
                db.rollback()
                if engine_name == "langgraph":
                    try:
                        chat_graph_service.reset_interrupted_thread(session_id)
                    except Exception as cleanup_exc:
                        logger.error(
                            "Unable to reset cancelled graph thread (%s)",
                            type(cleanup_exc).__name__,
                        )
                finish_chat_run(
                    db,
                    run_id=run_id,
                    status="cancelled",
                    error_code="user_cancelled",
                    partial_content=full_content,
                )
                terminal = True
                if isinstance(exc, GeneratorExit):
                    raise
                yield event("cancelled", message_id=assistant_message_id, status="cancelled")
                yield event("done", message_id=assistant_message_id, status="cancelled", engine=engine_name)
            except Exception as exc:
                db.rollback()
                public_error = classify_provider_error(exc)
                if engine_name == "langgraph":
                    try:
                        chat_graph_service.reset_interrupted_thread(session_id)
                    except Exception as cleanup_exc:
                        logger.error(
                            "Unable to reset failed graph thread (%s)",
                            type(cleanup_exc).__name__,
                        )
                finish_chat_run(
                    db,
                    run_id=run_id,
                    status="failed",
                    error_code=public_error.code,
                    partial_content="",
                )
                terminal = True
                elapsed_ms = int((time.perf_counter() - started_at) * 1000)
                log_observability_event(
                    logger,
                    "chat_failed",
                    request_id=request_id,
                    session_id=session_id,
                    elapsed_ms=elapsed_ms,
                    response_intent=response_intent,
                    tool_names=tool_names,
                    level=logging.ERROR,
                    error_type=type(exc).__name__,
                    failure_trace=safe_exception_trace(exc),
                    run_id=run_id,
                    chat_engine=engine_name,
                )
                yield event(
                    "error",
                    error={
                        "code": public_error.code,
                        "message": public_error.message,
                    },
                )
                yield event("done", message_id=assistant_message_id, status="failed", engine=engine_name)
            finally:
                if not terminal:
                    db.rollback()
                    finish_chat_run(
                        db,
                        run_id=run_id,
                        status="interrupted",
                        error_code="stream_interrupted",
                        partial_content=full_content,
                    )

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # disable nginx/proxy buffering so tokens flush live
                "X-Request-ID": request_id,
                "X-Session-ID": session_id,
            },
        )
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        log_observability_event(
            logger,
            "chat_failed",
            request_id=request_id,
            session_id=session_id,
            elapsed_ms=elapsed_ms,
            response_intent="deep_analysis",
            tool_names=tool_names,
            level=logging.ERROR,
            error_type=type(exc).__name__,
        )
        raise HTTPException(
            status_code=500,
            detail="The chat request could not be started.",
            headers={"X-Request-ID": request_id},
        )


@router.post("/chat/runs/{run_id}/cancel")
def cancel_chat_run(
    run_id: str,
    db: Session = Depends(get_db),
    user: AuthenticatedIdentity = Depends(get_current_user),
):
    if not re.fullmatch(r"[a-f0-9]{32}", run_id):
        raise HTTPException(status_code=404, detail="Chat run not found.")
    run = request_chat_run_cancellation(db, run_id=run_id, user=user)
    return {"run_id": run.run_id, "status": run.status}

@router.post("/chat/feedback")
def submit_chat_feedback(
    req: FeedbackRequest,
    db: Session = Depends(get_db),
    user: AuthenticatedIdentity = Depends(get_current_user),
):
    """Compatibility alias for the canonical message-scoped feedback endpoint."""
    feedback, changed = submit_message_feedback(
        db,
        message_id=req.messageId,
        user=user,
        feedback_type=req.feedbackType,
    )
    return {"status": "success", "feedback_id": feedback.id, "changed": changed}


@router.get("/generate-briefing")
def generate_executive_briefing(db: Session = Depends(get_db)):
    provider = get_ai_provider()
    try:
        from engine.tools.portfolio_tools import portfolio_get_riskiest_projects
        # Get the top 5 riskiest projects for the briefing
        riskiest_projects = portfolio_get_riskiest_projects(db, top_n=5)
        context_str = json.dumps(riskiest_projects, indent=2)
    except Exception as e:
        logger.error(f"Error getting briefing context: {e}")
        context_str = "[]"

    prompt = f"""You are an Executive Intelligence Analyst for a large-scale infrastructure and renewable energy project.

Your role is to analyze all available project data, KPIs, schedules, engineering records, procurement records, material management data, construction progress, workforce information, quality metrics, safety metrics, financial data, and risk indicators.
Your objective is not only to report the data but also to generate actionable business insights.

You MUST output your response in STRICT JSON format, generating an Executive Briefing consisting of:
1. "toplineSummary": A 2-3 sentence overarching summary of the portfolio health and immediate critical risks.
2. "keyActions": An array of exactly 3 most critical action items. Each item must have:
   - "type": (e.g., "Critical Bottleneck", "Financial Risk", "Schedule Milestone")
   - "title": A short title
   - "description": A detailed explanation of the issue and recommended action
   - "color": Hex color code (e.g., "#EF4444" for red/critical, "#F59E0B" for yellow/financial, "#10B981" for green/milestone)
3. "deepDive": An array of 2 detailed analytical paragraphs uncovering hidden correlations (e.g., how a vendor delay is causing a schedule slip). Each item must have:
   - "title": Topic title
   - "description": The detailed analysis paragraph
4. "confidenceScore": An integer between 0 and 100 representing the accuracy or confidence level of this analysis based on the completeness and quality of the provided data.

Be highly analytical and data-driven. Never make assumptions without mentioning confidence levels.
You MUST base your answers STRICTLY and EXCLUSIVELY on the Live Portfolio Context provided below. 
Do NOT use outside knowledge, and do NOT hallucinate or guess information.
IMPORTANT: The supply chain quantities in the data are in absolute Units, NOT Megawatts (MW). Do not use "MW" or "Megawatts". Use "Units" instead.

You MUST output ONLY valid json in the exact structure below, with no markdown formatting or extra text:
{{
  "toplineSummary": "...",
  "confidenceScore": 95,
  "keyActions": [
    {{ "type": "...", "title": "...", "description": "...", "color": "..." }}
  ],
  "deepDive": [
    {{ "title": "...", "description": "..." }}
  ]
}}

Live Portfolio Context:
{context_str}
"""
    messages = [{"role": "user", "content": prompt}]
    
    try:
        content = call_configured_llm(messages, temperature=0.2, max_tokens=4000, json_response=True)
            
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
        try:
            return json.loads(content)
        except Exception:
            return {
                "toplineSummary": "Failed to parse AI response.",
                "confidenceScore": 0,
                "keyActions": [],
                "deepDive": [{"title": "Raw Output", "description": content}]
            }
    except Exception as e:
        logger.error(f"AKASHA AI API Error: {e}")
        error_msg = str(e).replace("groq", "ai").replace("Groq", "AKASHA AI Provider")
        raise HTTPException(status_code=500, detail=error_msg)

from fastapi import APIRouter, Depends, HTTPException, Body

USE_VARIANCE_ENGINE = os.environ.get("USE_VARIANCE_ENGINE", "true").lower() == "true"

from typing import Optional, List, Dict, Any

class SimulationLabRequest(BaseModel):
    project: dict
    notification_context: Optional[dict] = None
    all_notifications: Optional[list] = []

@router.post("/simulation-lab")
def run_simulation_lab(req: SimulationLabRequest, db: Session = Depends(get_db)):
    from services.project_service import get_project_360_detail
    provider = get_ai_provider()
    
    project = req.project
    project_name = project.get("project_name", "")
    notif_ctx = req.notification_context
    all_notifs = req.all_notifications

    # Build notification context string for the LLM
    notif_context_str = ""
    if notif_ctx:
        notif_context_str += f"""\n\n═══ TRIGGERED BY THIS SPECIFIC NOTIFICATION ═══
Change Type: {notif_ctx.get('change_type', 'Unknown')}
Activity: {notif_ctx.get('activity_name', 'N/A')}
Block: {notif_ctx.get('block', 'N/A')}
Old Value: {notif_ctx.get('old_value', 'N/A')} → New Value: {notif_ctx.get('new_value', 'N/A')}
Message: {notif_ctx.get('message', '')}

Focus your analysis on: How does this specific change cascade through dependent downstream activities?
What activities are blocked or delayed because of this? What is the best recovery path?"""
    if all_notifs:
        notif_summary = json.dumps(all_notifs[:15], indent=2, default=str)[:3000]
        notif_context_str += f"""\n\n═══ ALL RECENT NOTIFICATIONS FOR THIS PROJECT ═══
{notif_summary}

Use these notifications to understand the full picture of delays and changes happening on this project."""

    # ═══════════════════════════════════════════════════════════
    # HYBRID ARCHITECTURE: Deterministic Engine + LLM Narrative
    # ═══════════════════════════════════════════════════════════
    if USE_VARIANCE_ENGINE:
        from engine.variance import compute_full_variance, compute_portfolio_variance

        # 1. DETERMINISTIC: compute variance table from live DB data
        if project_name and project_name != 'Entire Portfolio':
            variance = compute_full_variance(db, project_name)
        else:
            variance = compute_portfolio_variance(db, top_n=10)

        # 2. LLM: explain and rank only — NEVER invent numbers
        # Truncate variance data to fit in context window
        variance_str = json.dumps(variance, indent=2, default=str)[:6000]

        prompt = f"""You are the AKASHA AI Diagnostic Engine.
The deterministic variance engine has already computed the data below from live P6, SAP, and TC databases.

CRITICAL RULES:
- Do NOT calculate or estimate any new numbers.
- Use ONLY the days, percentages, and quantities given in the Computed Variance Data below.
- Every number you mention must appear verbatim in the input data.
- The supply chain quantities are in absolute Units, NOT Megawatts (MW).
- Explicitly review the "tc" (Transmission) section. If there are at-risk transmission lines, factor them into your root cause and suggestions.
{notif_context_str}

Computed Variance Data:
{variance_str}

Project Summary:
{json.dumps(project, indent=2)}

Based ONLY on the computed data above, provide:
1. "issues": An array of exactly 4 root-cause explanations. At least 2 must be "Critical", rest "Warning". 
   Each must reference actual drift_days, gap_qty, or float_hours from the data above.
   If a notification trigger was provided, the FIRST issue MUST directly address that specific change and its cascading impact.
   Format: {{"title": "specific issue referencing real numbers from data", "severity": "Critical"|"Warning"}}
2. "suggestions": An array of exactly 2 actionable strategies referencing the specific bottleneck activities or materials from the data.
   Format: {{"title": "strategy name", "description": "detailed strategy referencing specific data points"}}

You MUST output ONLY valid JSON with no markdown or extra text:
{{
  "issues": [
    {{"title": "...", "severity": "Critical"}}
  ],
  "suggestions": [
    {{"title": "...", "description": "..."}}
  ]
}}"""
        messages = [{"role": "user", "content": prompt}]

        try:
            content = call_configured_llm(messages, temperature=0.2, max_tokens=4000, json_response=True)
                
            content = content.strip()
            if content.startswith("```json"):
                content = content[7:-3].strip()
            elif content.startswith("```"):
                content = content[3:-3].strip()

            try:
                llm_result = json.loads(content)
            except Exception:
                llm_result = {
                    "issues": [{"title": "AI analysis unavailable. Variance data computed successfully.", "severity": "Warning"}],
                    "suggestions": [],
                }

            # 3. MERGE: engine numbers (always) + LLM narrative (explanation only)
            return {
                "issues": llm_result.get("issues", []),
                "suggestions": llm_result.get("suggestions", []),
                "scheduleImpact": variance["schedule_impact"],  # ALWAYS from engine
                "variance": variance,  # full variance data for frontend drill-down
                "engine_version": "2.0",
            }

        except Exception as e:
            logger.error(f"LLM call failed, returning engine-only results: {e}")
            # Even if LLM fails, we still return deterministic data
            return {
                "issues": [{"title": "AI narrative unavailable. Review variance data below.", "severity": "Warning"}],
                "suggestions": [],
                "scheduleImpact": variance["schedule_impact"],
                "variance": variance,
                "engine_version": "2.0",
            }

    # ═══════════════════════════════════════════════════════════
    # LEGACY PATH (feature flag off — old LLM-only behavior)
    # ═══════════════════════════════════════════════════════════
    deep_data = {}
    if project_name and project_name != 'Entire Portfolio':
        detail = get_project_360_detail(db, project_name)
        if detail and "error" not in detail:
            deep_data = detail

    prompt = f"""You are the AKASHA AI Simulation Engine. You are running a deep diagnostic on the following live project data to detect critical risks and provide strategic recommendations.
You must analyze the deep data (including P6 schedules, SAP procurement records, and TC engineering data) to identify exact bottlenecks.
Do not make up generic issues. Identify actual materials that are late, specific labor issues, or specific variance details found in the data.
IMPORTANT: The supply chain quantities in the data are in absolute Units, NOT Megawatts (MW). Do not use "MW" or "Megawatts" in your analysis. Use "Units" instead.

Project Summary:
{json.dumps(project, indent=2)}

Deep System Data (P6, SAP, TC):
{json.dumps(deep_data, indent=2)[:8000]}

You MUST output your response in STRICT JSON format, consisting of:
1. "issues": An array of exactly 4 AI-Detected issues (at least 2 critical, 2 warning). Each must have:
   - "title": A detailed description of the issue and its cascading impact referencing REAL data points (e.g. "Transformer delivery delayed by 15 days in SAP").
   - "severity": Either "Critical" or "Warning"
2. "suggestions": An array of exactly 2 actionable AI Strategy Recommendations. Each must have:
   - "title": Strategy title
   - "description": Detailed strategy and estimated impact.
3. "scheduleImpact": An array of 3 numbers representing estimated "Days Delayed" for [Foundation, Module Installation, Grid Connection].

You MUST output ONLY valid json in the exact structure below, with no markdown formatting or extra text:
{{
  "issues": [
    {{ "title": "...", "severity": "Critical" }}
  ],
  "suggestions": [
    {{ "title": "...", "description": "..." }}
  ],
  "scheduleImpact": [12, 5, 20]
}}
"""
    messages = [{"role": "user", "content": prompt}]
    
    try:
        content = call_configured_llm(messages, temperature=0.2, max_tokens=4000, json_response=True)
            
        content = content.strip()
        if content.startswith("```json"):
            content = content[7:-3].strip()
        elif content.startswith("```"):
            content = content[3:-3].strip()
        try:
            result = json.loads(content)
            result["engine_version"] = "1.0"  # legacy
            return result
        except Exception:
            return {
                "issues": [{"title": "Raw Output: " + content[:200], "severity": "Warning"}],
                "suggestions": [],
                "scheduleImpact": [0,0,0],
                "engine_version": "1.0",
            }
    except Exception as e:
        logger.error(f"AKASHA AI API Error: {e}")
        error_msg = str(e).replace("groq", "ai").replace("Groq", "AKASHA AI Provider")
        raise HTTPException(status_code=500, detail=error_msg)

class FinalReportRequest(BaseModel):
    project: dict
    strategy: dict
    tasks: list
    simulation_results: dict
    notification_context: Optional[dict] = None
    all_notifications: Optional[list] = []

class StrategiesRequest(BaseModel):
    project: dict
    constraints: dict
    notification_context: Optional[dict] = None
    all_notifications: Optional[list] = []

@router.post("/simulation-lab/strategies")
def generate_strategies(req: StrategiesRequest, db: Session = Depends(get_db)):
    from services.project_service import get_project_360_detail
    from engine.monte_carlo import run_monte_carlo_simulation
    from datetime import datetime
    
    provider = get_ai_provider()
    project_name = req.project.get("project_name", "")
    p6_id = req.project.get("p6", {}).get("id") or req.project.get("project_id", "") or project_name
    
    # 1. Run baseline deterministic simulation (no modifiers)
    # Using 500 iterations for speed during interactive session
    baseline_sim = run_monte_carlo_simulation(db, p6_id, iterations=500, seed=42)
    if "error" in baseline_sim:
        baseline_p50_date = datetime.today()
    else:
        baseline_p50_date = datetime.strptime(baseline_sim["completion_dates"]["p50"], "%Y-%m-%d")

    # Build notification context for strategies
    notif_str = ""
    if req.notification_context:
        nc = req.notification_context
        notif_str = f"""\n\nIMPORTANT CONTEXT - This simulation was triggered by a specific notification alert:
Change: {nc.get('change_type', 'Unknown')} | Activity: {nc.get('activity_name', 'N/A')} | Block: {nc.get('block', 'N/A')}
Old: {nc.get('old_value', 'N/A')} → New: {nc.get('new_value', 'N/A')}
Message: {nc.get('message', '')}

Your strategies MUST directly address recovering from this specific issue."""
    if req.all_notifications:
        notif_str += f"\n\nAll recent project notifications:\n{json.dumps(req.all_notifications[:10], indent=2, default=str)[:2000]}"

    # Deep Context extraction for LLM
    import models
    historical_str = "\n\nDEEP PROJECT CONTEXT & HISTORY:\n"
    past_delays = db.query(models.Notification).filter(
        models.Notification.project_name == project_name,
        models.Notification.change_type.in_(["Date Delay", "Critical Slip", "Delay"])
    ).order_by(models.Notification.created_at.desc()).limit(5).all()
    
    if past_delays:
        historical_str += "Past Delays & COD shifts:\n"
        for pd in past_delays:
            historical_str += f"- {pd.created_at.strftime('%Y-%m-%d')}: {pd.change_type} on {pd.activity_name or 'Project'} - {pd.message}\n"
    else:
        historical_str += "No significant historical delays found.\n"
        
    proj_map = db.query(models.ProjectMapping).filter(
        (models.ProjectMapping.project == project_name) | 
        (models.ProjectMapping.project_name_from_p6 == project_name) |
        (models.ProjectMapping.project_id == project_name)
    ).first()
    if proj_map:
        historical_str += f"Project Specs: Category={proj_map.category}, Capacity={proj_map.capacity_mwac} MW, SPV={proj_map.spv_name}\n"

    # 2. Get LLM to propose 3 strategy permutations based on user constraints
    prompt = f"""You are the AKASHA AI Strategy Engine, an elite Master Strategist with over 18 years of deeply technical field experience managing large-scale Transmission & Renewable Energy mega-projects. You are an undisputed expert in SAP, Primavera P6, and operational recovery.
The user wants to run a "What-If" simulation with the following parameters:
{json.dumps(req.constraints, indent=2)}
{notif_str}
{historical_str}

Analyze the historical trends, the specific alert, and the user's custom scenario to generate 3 highly targeted, creative, and DYNAMIC strategy options.
CRITICAL: Each strategy must focus on a SINGLE, highly actionable, decisive step to recover the specific issue. Do not provide a generic list of things to do. Provide one concrete, expert-level maneuver per strategy.
Do NOT just use generic titles like "Strict Adherence" or "Aggressive". Invent specific, contextual titles (e.g., "Helicopter Airlift Escalation", "Night-Shift Double Crew", "Wait Out Monsoon").
The descriptions must uniquely explain EXACTLY what operational levers are being pulled in one decisive step.

You MUST output strictly in valid JSON format matching this schema structure, but with YOUR OWN dynamic content:
{{
  "strategies": [
    {{
      "id": "strat_1",
      "title": "<Your Dynamic Contextual Title Here>",
      "description": "<Your specific, detailed operational explanation here>",
      "modifiers": {{
         "weather_monsoon": "Heavy",
         "weather_wind": "Normal",
         "added_crews": 2
      }},
      "ai_confidence_pct": <integer between 50 and 95>,
      "recommended": true,
      "radar_data": [80, 60, 90, 85, 87] 
    }}
  ]
}}
IMPORTANT: You do NOT provide cost or time impact. The deterministic Monte Carlo engine will calculate that based on your `modifiers` payload. Just provide the 3 strategies and their modifiers.
"""
    messages = [{"role": "user", "content": prompt}]
    try:
        content = call_configured_llm(messages, temperature=0.2, max_tokens=2000, json_response=True)
        content = content.strip()
        if content.startswith("```json"): content = content[7:-3].strip()
        elif content.startswith("```"): content = content[3:-3].strip()
        
        try:
            llm_result = json.loads(content)
        except Exception:
            llm_result = {"strategies": []}
            
        # 3. DETERMINISTIC MATH: Feed LLM parameters into Monte Carlo engine
        final_strategies = []
        for strat in llm_result.get("strategies", []):
            mods = strat.get("modifiers", {})
            strat_sim = run_monte_carlo_simulation(db, p6_id, iterations=500, modifiers=mods, seed=42)
            
            if "error" not in strat_sim:
                strat_p50_date = datetime.strptime(strat_sim["completion_dates"]["p50"], "%Y-%m-%d")
                
                # Time Saved = Baseline P50 - Strat P50 (positive means finished earlier)
                time_saved_days = (baseline_p50_date - strat_p50_date).days
                
                # Cost Impact = deterministic calculation (e.g. 0.5 Cr per added crew)
                crews = int(mods.get("added_crews", 0))
                cost_cr = round(crews * 0.5, 2)
                
                # Risk Reduction = how much P90 - P10 spread was reduced
                baseline_spread = baseline_sim.get("spread_days", 1)
                strat_spread = strat_sim.get("spread_days", 1)
                risk_reduction_pct = round(((baseline_spread - strat_spread) / baseline_spread) * 100)
                
                strat["time_saved_days"] = time_saved_days
                strat["cost_impact_cr"] = cost_cr
                strat["risk_reduction_pct"] = risk_reduction_pct
                
            final_strategies.append(strat)
            
        return {"strategies": final_strategies}

    except Exception as e:
        logger.error(f"Strategy generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

class SimulationExecuteRequest(BaseModel):
    project: dict
    strategy: dict
    notification_context: Optional[dict] = None

@router.post("/simulation-lab/simulate")
def generate_simulation(req: SimulationExecuteRequest, db: Session = Depends(get_db)):
    from engine.monte_carlo import run_monte_carlo_simulation
    project_name = req.project.get("project_name", "")
    p6_id = req.project.get("p6", {}).get("id") or req.project.get("project_id", "") or project_name
    
    # 1. Get Baseline Simulation
    baseline = run_monte_carlo_simulation(db, p6_id, iterations=1000, seed=42)
    
    # 2. Get Strategy Simulation
    mods = req.strategy.get("modifiers", {})
    simulated = run_monte_carlo_simulation(db, p6_id, iterations=1000, seed=42, modifiers=mods)
    
    timeline = []
    # If the monte carlo simulation provided monthly progression, use it. Otherwise, generate a realistic curve based on the dates.
    months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
    
    # We will generate a dynamic timeline that reflects the actual risk reduction.
    base_spread = baseline.get("spread_days", 1)
    sim_spread = simulated.get("spread_days", 1)
    risk_factor = (base_spread - sim_spread) / max(base_spread, 1)
    
    for i, m in enumerate(months):
        base_val = min(100, i * 8.5)
        # The simulated value should pull ahead based on how much risk/time was saved
        sim_val = min(100, base_val + (i * 2.5 * risk_factor) + (risk_factor > 0 and 5 or 0))
        timeline.append({
            "month": m,
            "baseline": round(base_val, 1),
            "simulated": round(sim_val, 1)
        })

    return {
        "baseline": baseline,
        "simulated": simulated,
        "timeline": timeline,
        "engine_version": "2.0"
    }

@router.post("/simulation-lab/execute")
def execute_strategy(req: SimulationExecuteRequest, db: Session = Depends(get_db)):
    provider = get_ai_provider()
    
    # Fetch Transmission (TC) Variance to include in context
    p6_id = req.project.get("p6", {}).get("id") or req.project.get("project_id", "") or req.project.get("project_name", "")
    from engine.variance import compute_tc_variance, _resolve_project_id
    resolved_id = _resolve_project_id(db, p6_id) or p6_id
    tc_variance = compute_tc_variance(db, resolved_id)
    
    prompt = f"""You are the AKASHA AI Directive Planning Assistant. Select local advisory directive template codes based on the chosen strategy.

Codes select fixed backend-owned local-review templates only. They do not create, update, send, sync, push, or execute anything in SAP, P6, PMAG, Contractor Portal, HRMS, or any other external system.
    
Project Context:
{json.dumps(req.project, indent=2)}

Transmission (TC) Context:
{json.dumps(tc_variance, indent=2)}

Strategy Applied:
{json.dumps(req.strategy, indent=2)}

Select between 1 and 5 unique codes from this exact allowlist:
{json.dumps(SIMULATION_DIRECTIVE_CODES)}

Use `P6_SCHEDULE_REVIEW` for schedule recovery review, `CREW_PLAN_REVIEW` for field crew planning, `PROCUREMENT_REVIEW` for material or supplier recovery, `TC_RECOVERY_REVIEW` for transmission recovery, and `PMAG_ACTION_REVIEW` for PMAG-governed action review.

You MUST output only this exact JSON shape. Do not return tasks, prose, explanations, objects, system names, actions, descriptions, statuses, or any keys other than `directive_codes`:
{{
  "directive_codes": ["P6_SCHEDULE_REVIEW"]
}}
"""
    messages = [{"role": "user", "content": prompt}]
    try:
        content = call_configured_llm(messages, temperature=0.2, max_tokens=4000, json_response=True)
        content = content.strip()
        if content.startswith("```json"): content = content[7:-3].strip()
        elif content.startswith("```"): content = content[3:-3].strip()
        try:
            return build_simulation_directives(json.loads(content))
        except (json.JSONDecodeError, DirectiveValidationError):
            raise HTTPException(
                status_code=502,
                detail="AI directive output did not satisfy the advisory review contract.",
            )
    except HTTPException:
        raise
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/simulation-lab/report")
def generate_report(req: SimulationExecuteRequest, db: Session = Depends(get_db)):
    # Generate an executive report based on the executed strategy
    provider = get_ai_provider()
    
    # Fetch Transmission (TC) Variance to include in context
    p6_id = req.project.get("p6", {}).get("id") or req.project.get("project_id", "") or req.project.get("project_name", "")
    from engine.variance import compute_tc_variance, _resolve_project_id
    resolved_id = _resolve_project_id(db, p6_id) or p6_id
    tc_variance = compute_tc_variance(db, resolved_id)
    
    # Extract Human-Readable Project Name (not ID)
    project_name = req.project.get("raw_project_name") or req.project.get("project_name") or req.project.get("name") or "Unknown Project"

    # Include notification trigger in report if available
    notif_report_str = ""
    if req.notification_context:
        nc = req.notification_context
        notif_report_str = f"""\n\n## Original Trigger
This simulation was triggered by a notification alert:
- Change: {nc.get('change_type', 'Unknown')}
- Activity: {nc.get('activity_name', 'N/A')}
- Block: {nc.get('block', 'N/A')}
- Details: {nc.get('old_value', '')} → {nc.get('new_value', '')}
- Message: {nc.get('message', '')}

The report MUST reference this original trigger and explain how the chosen strategy addresses it."""

    prompt = f"""You are Akasha, an Enterprise Project Intelligence Assistant.
Your role is to analyze project data and provide insights, not perform core project calculations.

## Important Rules
1. Never invent project data.
2. Never assume values that are not provided.
3. Use only the supplied project information.
4. If required data is missing, explicitly state it.
5. Explain risks, delays, trends, and impacts based on the data.
6. Provide actionable recommendations.
7. Always justify recommendations using the provided metrics.
8. If the Transmission Context shows at-risk lines or delays, explicitly mention Transmission in the Root Cause Analysis and Key Findings.

CRITICAL INSTRUCTION: Keep all answers highly concise, short, and crisp. Use a maximum of 2 sentences per paragraph or point. Do not provide long explanations.
{notif_report_str}

## What You Must Do
Analyze the following project summary and the selected strategy:
Project Name: '{project_name}'
Project Context: {json.dumps(req.project, indent=2)}
Transmission Context: {json.dumps(tc_variance, indent=2)}
Strategy Applied: {json.dumps(req.strategy, indent=2)}

Provide a highly customized, unique, and dynamic report. Do NOT use generic placeholder text. The report MUST specifically detail the actual strategy applied and its direct consequences on this exact project!
1. Executive Summary (Must start with mentioning the Project Name)
2. Key Findings
3. Risk Assessment
4. Root Cause Analysis
5. Recommended Actions
6. Expected Outcome

## What You Must NOT Do
Do not calculate: SPI, CPI, Delay Percentage, Project Health Score, Forecast Completion Dates. These values are provided by the platform's business logic engine. Use them only for analysis and recommendations.

Output valid JSON only matching this exact structure:
{{
   "title": "<Dynamic Title specific to the project and strategy>",
   "executiveSummary": "<Dynamic 2-sentence summary>",
   "keyFindings": ["<Finding 1>", "<Finding 2>"],
   "riskAssessment": "<Dynamic Risk Analysis>",
   "rootCauseAnalysis": "<Dynamic Root Cause Analysis>",
   "recommendedActions": ["<Action 1>", "<Action 2>"],
   "expectedOutcome": "<Dynamic expected outcome of the strategy>"
}}
"""
    messages = [{"role": "user", "content": prompt}]
    try:
        content = call_configured_llm(messages, temperature=0.1, max_tokens=4000, json_response=True)
        content = content.strip()
        if content.startswith("```json"): content = content[7:-3].strip()
        elif content.startswith("```"): content = content[3:-3].strip()
        try:
            return json.loads(content)
        except Exception:
            return {"title": "Error", "executiveSummary": content, "keyFindings": [], "riskAssessment": "", "rootCauseAnalysis": "", "recommendedActions": [], "expectedOutcome": ""}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/project-diagnostic")
def project_diagnostic(project: dict = Body(...), db: Session = Depends(get_db)):
    provider = get_ai_provider()
    prompt = f"""You are Akasha, an Enterprise Project Intelligence Assistant.
Your role is to analyze project data and provide insights, not perform core project calculations.

## Important Rules
1. Never invent project data.
2. Never assume values that are not provided.
3. Use only the supplied project information.
4. Explain risks, delays, trends, and impacts based on the data.
5. Provide actionable recommendations.
6. Always justify recommendations using the provided metrics.

CRITICAL INSTRUCTION: Keep all answers highly concise, short, and crisp. Use a maximum of 2 sentences per paragraph or point. Do not provide long explanations.
IMPORTANT: The supply chain quantities in the data are in absolute Units, NOT Megawatts (MW). Do not use "MW" or "Megawatts". Use "Units" instead.

## What You Must Do
Analyze the following project summary:
{json.dumps(project, indent=2)}

Provide:
1. Executive Summary
2. Key Findings
3. Risk Assessment
4. Root Cause Analysis
5. Recommended Actions
6. Expected Outcome

## What You Must NOT Do
Do not calculate: SPI, CPI, Delay Percentage, Project Health Score, Forecast Completion Dates. Use the provided metrics only for analysis.

Output valid JSON only matching this exact structure:
{{
   "executiveSummary": "...",
   "keyFindings": ["...", "..."],
   "riskAssessment": "...",
   "rootCauseAnalysis": "...",
   "recommendedActions": ["...", "..."],
   "expectedOutcome": "..."
}}
"""
    messages = [{"role": "user", "content": prompt}]
    try:
        content = call_configured_llm(messages, temperature=0.2, max_tokens=4000, json_response=True)
        content = content.strip()
        if content.startswith("```json"): content = content[7:-3].strip()
        elif content.startswith("```"): content = content[3:-3].strip()
        try:
            return json.loads(content)
        except Exception:
            return {"executiveSummary": content, "keyFindings": [], "riskAssessment": "", "rootCauseAnalysis": "", "recommendedActions": [], "expectedOutcome": ""}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))





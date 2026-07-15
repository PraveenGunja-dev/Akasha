"""
Akasha Engine — Chat Orchestrator (Step 4-5 of Pipeline)

The central brain of the chatbot. Ties together:
1. Intent Classification (What does the user want?)
2. Freshness Check (Is the data stale?)
3. Tools/Data Fetching (Get the right data fast)
4. LLM Generation (Format the response)
5. Memory/Feedback (Learn from past mistakes)
"""

import time
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from sqlalchemy.orm import Session

import models
from engine.intent import classify_intent, ChatIntent
from engine.cache import check_freshness, get_cached_data, update_cache
from engine.memory import build_memory_context, store_feedback

logger = logging.getLogger(__name__)


@dataclass
class ChatResponse:
    content: str
    intent_type: str
    project_ids: list[str]
    domains: list[str]
    data_as_of: str | None
    sources_used: list[str]
    latency_ms: int


class ChatOrchestrator:
    def __init__(self, default_llm: str = "qwen"):
        self.default_llm = default_llm

    def process_message(
        self,
        db: Session,
        message: str,
        session_id: str,
        history: list[dict],
        project_names: list[str] = None,
        is_deep_analysis: bool = False
    ) -> ChatResponse:
        """Main entry point for the 6-step pipeline (or ReAct Agent)."""
        t0 = time.time()
        
        # Branch 1: Deep Analysis Mode (True ReAct Agent)
        if is_deep_analysis:
            from engine.agent import run_deep_analysis_agent
            logger.info("Routing to Deep Analysis Agent (ReAct Loop)")
            content, tools_used = run_deep_analysis_agent(db, message, history)
            latency = int((time.time() - t0) * 1000)
            
            return ChatResponse(
                content=content,
                intent_type="deep_analysis",
                project_ids=project_names or [],
                domains=[],
                data_as_of=None,
                sources_used=tools_used,
                latency_ms=latency,
            )
            
        # Branch 2: Standard Fast Pipeline (Steps 1-5)
        # Step 1: Intent Classification
        intent = classify_intent(message, history, project_names)
        logger.info(f"Intent classified: {intent}")
        
        # Step 2 & 3: Freshness & Data Retrieval
        context_data, freshness_info, sources = self._gather_context(db, intent)
        
        # Determine the freshest timestamp among all data used
        freshest_time = None
        for pid, fresh in freshness_info.items():
            for key in ["p6_synced_at", "sap_synced_at", "tc_synced_at"]:
                ts = fresh["current_sync"].get(key)
                if ts:
                    if not freshest_time or ts > freshest_time:
                        freshest_time = ts
        
        # Step 4: Domain Routing (Factual, Analytical, Advisory)
        if intent.intent_type == "factual":
            content = self._handle_factual(message, context_data, history, intent, db)
        elif intent.intent_type == "analytical":
            content = self._handle_analytical(message, context_data, history, intent, db)
        elif intent.intent_type == "document":
            content = "I don't have access to documents yet. (v2 feature)"
        else:
            content = self._handle_advisory(message, context_data, history, intent, db)
            
        # Step 5: Provenance Tracking
        latency = int((time.time() - t0) * 1000)
        
        response = ChatResponse(
            content=content,
            intent_type=intent.intent_type,
            project_ids=intent.projects,
            domains=intent.domains,
            data_as_of=freshest_time,
            sources_used=sources,
            latency_ms=latency,
        )
        
        # Step 6 is handled in the API router (logging the interaction)
        return response

    def process_message_stream(
        self,
        db: Session,
        message: str,
        session_id: str,
        history: list[dict],
        project_names: list[str] = None,
        is_deep_analysis: bool = False,
        image_data: str = None
    ):
        """Streaming version of process_message."""
        t0 = time.time()
        
        # Image Vision Preprocessing
        if image_data:
            from engine.agent import analyze_image_context
            logger.info("Image uploaded, extracting vision context before ReAct loop.")
            vision_context = analyze_image_context(image_data, message)
            message = f"[IMAGE CONTEXT EXTRACTED BY VISION MODEL: {vision_context}]\n\nUser Question: {message}"
        
        # Branch 1: Deep Analysis Mode
        if is_deep_analysis:
            from engine.agent import run_deep_analysis_agent_stream
            logger.info("Routing to Deep Analysis Agent Stream (ReAct Loop)")
            full_content = ""
            tools_used = []
            
            for chunk in run_deep_analysis_agent_stream(db, message, history):
                if isinstance(chunk, dict) and chunk.get("type") == "tools_used":
                    tools_used = chunk["tools"]
                else:
                    full_content += chunk
                    yield chunk
            
            latency = int((time.time() - t0) * 1000)
            yield {
                "type": "metadata",
                "response": ChatResponse(
                    content=full_content,
                    intent_type="deep_analysis",
                    project_ids=project_names or [],
                    domains=[],
                    data_as_of=None,
                    sources_used=tools_used,
                    latency_ms=latency,
                )
            }
            return
            
        # Branch 2: Standard Fast Pipeline
        intent = classify_intent(message, history, project_names)
        context_data, freshness_info, sources = self._gather_context(db, intent)
        
        freshest_time = None
        for pid, fresh in freshness_info.items():
            for key in ["p6_synced_at", "sap_synced_at", "tc_synced_at"]:
                ts = fresh["current_sync"].get(key)
                if ts and (not freshest_time or ts > freshest_time):
                    freshest_time = ts
                    
        prompt = ""
        if intent.intent_type == "factual":
            prompt = self._build_prompt_factual(message, context_data, history, intent, db)
        elif intent.intent_type == "analytical":
            prompt = self._build_prompt_analytical(message, context_data, history, intent, db)
        elif intent.intent_type == "document":
            yield "I don't have access to documents yet. (v2 feature)"
            full_content = "I don't have access to documents yet. (v2 feature)"
            prompt = None
        else:
            prompt = self._build_prompt_advisory(message, context_data, history, intent, db)
            
        if prompt:
            full_content = ""
            for chunk in self._generate_stream(prompt):
                full_content += chunk
                yield chunk
                
        latency = int((time.time() - t0) * 1000)
        yield {
            "type": "metadata",
            "response": ChatResponse(
                content=full_content,
                intent_type=intent.intent_type,
                project_ids=intent.projects,
                domains=intent.domains,
                data_as_of=freshest_time,
                sources_used=sources,
                latency_ms=latency,
            )
        }

    def _gather_context(self, db: Session, intent: ChatIntent) -> tuple[dict, dict, list]:
        """Gather context data for the requested projects and domains."""
        from engine.tools.portfolio_tools import portfolio_resolve_project_id
        from services.project_service import get_project_360_detail
        
        context_data = {}
        freshness_info = {}
        sources = set()
        
        # Resolve project names to IDs
        resolved_pids = []
        for p in intent.projects:
            result = portfolio_resolve_project_id(db, p)
            if result:
                pid = result["project_id"] if isinstance(result, dict) else result
                resolved_pids.append(pid)
        
        if not resolved_pids:
            if "tc" in intent.domains:
                from engine.tools.tc_tools import tc_get_at_risk_lines, tc_get_network_summary
                context_data["transmission_lines"] = tc_get_at_risk_lines(db, limit=15)
                context_data["transmission_summary"] = tc_get_network_summary(db)
                sources.add("tc_network")
            
            if intent.is_portfolio or "p6" in intent.domains:
                from engine.tools.portfolio_tools import portfolio_get_riskiest_projects
                context_data["portfolio_risks"] = portfolio_get_riskiest_projects(db, top_n=5)
                sources.add("portfolio_aggregate")
            
            return context_data, {}, list(sources)

        # Update intent with resolved IDs
        intent.projects = resolved_pids
        
        for pid in resolved_pids:
            # Step 2: Check freshness
            fresh = check_freshness(db, pid, "project_360")
            freshness_info[pid] = fresh
            
            # Step 3: Conditional Recompute
            if not fresh["is_stale"] and fresh["cache_exists"]:
                logger.info(f"Using cached 360 data for {pid} (source: {fresh['cache_source']})")
                data = get_cached_data(db, pid, "project_360")
                context_data[pid] = data
                sources.add(f"metrics_cache ({fresh['cache_source']})")
            else:
                logger.info(f"Data stale or missing for {pid}, recomputing...")
                data = get_project_360_detail(db, pid)
                update_cache(db, pid, "project_360", data, fresh["current_sync"])
                context_data[pid] = data
                sources.update(["p6_project", "p6_activity", "mt_poamount", "tc_network_edge"])
                
        return context_data, freshness_info, list(sources)

    def _build_prompt_factual(self, message: str, context: dict, history: list, intent: ChatIntent, db: Session) -> str:
        memory = build_memory_context(db, intent.projects[0] if intent.projects else None, message)
        hist_str = ""
        if history:
            hist_str = "\nPrevious conversation:\n"
            for h in history[-4:]:
                r = h.get("role") or h.get("type", "user")
                if r == "bot": r = "assistant"
                hist_str += f"{r.upper()}: {h.get('content', '')}\n"
        return f"""You are the Akasha AI Copilot for EPC project management.
RULES:
1. Answer ONLY what the user asked using ONLY the provided data. No templates, no boilerplate.
2. If they ask a number, give the number. If they ask a list, give the list.
3. If the user asks a general question about your capabilities or greets you, respond conversationally and helpfully.
4. If the user asks a specific data question and the provided data does not contain the answer, say "I don't have that in the current data."

{hist_str}
{memory}

DATA FOR {', '.join(intent.projects)}:
```json
{json.dumps(context, indent=2, default=str)}
```

Question: {message}
"""

    def _build_prompt_analytical(self, message: str, context: dict, history: list, intent: ChatIntent, db: Session) -> str:
        memory = build_memory_context(db, intent.projects[0] if intent.projects else None, message)
        return f"""You are the Akasha AI Copilot — a senior EPC project analyst.
RULES:
1. Write like a senior analyst briefing the CEO — direct, factual, no fluff. Use **bold** for key numbers/variances.
2. If the user asks a general question about your capabilities or greets you, respond conversationally and helpfully.
3. If the user asks a specific data question and the provided data does not contain the answer, say "I don't have that in the current data."

{memory}

DATA FOR {', '.join(intent.projects)}:
```json
{json.dumps(context, indent=2, default=str)}
```

Question: {message}
"""

    def _build_prompt_advisory(self, message: str, context: dict, history: list, intent: ChatIntent, db: Session) -> str:
        memory = build_memory_context(db, intent.projects[0] if intent.projects else None, message)
        hist_str = ""
        if history:
            hist_str = "\nPrevious conversation:\n"
            for h in history[-4:]:
                r = h.get("role") or h.get("type", "user")
                if r == "bot": r = "assistant"
                hist_str += f"{r.upper()}: {h.get('content', '')}\n"
        return f"""You are the Akasha AI Copilot — an expert PMO Director.
RULES:
1. Don't just report data — advise on what to do next. Provide actionable mitigations.
2. Flag critical path risks immediately. Highlight high-severity bottlenecks.
3. Be direct. No filler words. Maximum 3 paragraphs.
4. If the user asks a general question about your capabilities or greets you, respond conversationally and helpfully.
5. If the user asks a specific data question and the provided data does not contain the answer, say "I don't have that in the current data."

{memory}

{hist_str}

CURRENT PROJECT DATA:
```json
{json.dumps(context, indent=2, default=str)}
```

User Request: {message}
"""

    def _generate(self, prompt: str) -> str:
        """Call the appropriate LLM backend."""
        from routers.ai import call_ollama, call_azure_openai_curl
        if self.default_llm == "azure":
            return call_azure_openai_curl([{"role": "user", "content": prompt}], temperature=0.3, max_tokens=2048)
        else:
            return call_ollama([{"role": "user", "content": prompt}], temperature=0.3, max_tokens=2048)

    def _generate_stream(self, prompt: str):
        """Call the appropriate LLM backend with streaming."""
        from routers.ai import call_ollama, call_azure_openai_curl
        if self.default_llm == "azure":
            yield call_azure_openai_curl([{"role": "user", "content": prompt}], temperature=0.3, max_tokens=2048)
        else:
            response = call_ollama([{"role": "user", "content": prompt}], temperature=0.3, max_tokens=2048, stream=True)
            for chunk in response:
                if chunk.choices and chunk.choices[0].delta.content:
                    yield chunk.choices[0].delta.content


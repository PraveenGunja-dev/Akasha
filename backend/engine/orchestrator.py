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
from sqlalchemy.orm import Session

from engine.intent import classify_intent, ChatIntent
from engine.cache import get_current_sync_times
from engine.contracts import ChatResponse, EvidenceItem, SourceFreshness, UserScope
from engine.memory import build_memory_context
from engine.project_resolver import resolve_projects_from_intent
from engine.security import (
    denied_domains,
    denied_projects,
    public_dev_scope,
    scope_allows_portfolio,
)
from engine.verifier import verify_numeric_claims

logger = logging.getLogger(__name__)


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
        is_deep_analysis: bool = False,
        user_scope: UserScope | None = None,
    ) -> ChatResponse:
        """Main entry point for the 6-step pipeline (or ReAct Agent)."""
        t0 = time.time()
        user_scope = user_scope or public_dev_scope()
        
        # Branch 1: Deep Analysis Mode (True ReAct Agent)
        if is_deep_analysis:
            from engine.agent import run_deep_analysis_agent
            logger.info("Routing to Deep Analysis Agent (ReAct Loop)")
            content, tools_used, tool_results = run_deep_analysis_agent(db, message, history, user_scope=user_scope)
            latency = int((time.time() - t0) * 1000)
            freshness, sources, evidence, warnings, domains, project_ids = self._metadata_from_tool_results(tool_results)
            warnings.extend(verify_numeric_claims(content, tool_results))
            
            return ChatResponse(
                content=content,
                intent_type="deep_analysis",
                project_ids=project_names or project_ids,
                domains=domains,
                freshness=freshness,
                evidence=evidence,
                warnings=warnings,
                sources_used=sources or tools_used,
                latency_ms=latency,
            )
            
        # Branch 2: Standard Fast Pipeline (Steps 1-5)
        # Step 1: Intent Classification
        intent = classify_intent(message, history, project_names)
        if project_names and not intent.projects and not intent.is_portfolio:
            intent.projects = project_names
        logger.info(f"Intent classified: {intent}")

        resolution = resolve_projects_from_intent(
            db,
            intent.projects,
            message=message,
            is_portfolio=intent.is_portfolio,
        )
        if resolution.status in ("ambiguous", "not_found"):
            latency = int((time.time() - t0) * 1000)
            return ChatResponse(
                content=resolution.question or "Which project should I use?",
                intent_type=intent.intent_type,
                project_ids=[],
                domains=intent.domains,
                latency_ms=latency,
                status="clarification",
                clarification=resolution.question,
                warnings=["project_resolution_required"],
            )
        if resolution.status == "not_project_specific" and intent.is_portfolio and not scope_allows_portfolio(user_scope):
            return self._unauthorized_response(
                "You are not authorized to access portfolio-wide chatbot data.",
                intent.intent_type,
                [],
                intent.domains,
                int((time.time() - t0) * 1000),
                ["unauthorized_portfolio_access"],
            )
        intent.projects = resolution.project_ids
        intent.domains = self._select_domains(message, intent)

        authorization_failure = self._authorization_failure(intent, user_scope, int((time.time() - t0) * 1000))
        if authorization_failure:
            return authorization_failure
        
        # Step 2 & 3: Freshness & Data Retrieval
        context_data, freshness, sources, evidence, warnings = self._gather_context(db, intent)
        
        # Step 4: Domain Routing (Factual, Analytical, Advisory)
        deterministic_content = self._try_deterministic_answer(message, context_data, intent)
        if deterministic_content:
            content = deterministic_content
        elif intent.intent_type == "factual":
            content = self._handle_factual(message, context_data, history, intent, db)
        elif intent.intent_type == "analytical":
            content = self._handle_analytical(message, context_data, history, intent, db)
        elif intent.intent_type == "document":
            content = "I don't have access to documents yet. (v2 feature)"
        else:
            content = self._handle_advisory(message, context_data, history, intent, db)

        warnings.extend(verify_numeric_claims(content, context_data))
            
        # Step 5: Provenance Tracking
        latency = int((time.time() - t0) * 1000)
        
        response = ChatResponse(
            content=content,
            intent_type=intent.intent_type,
            project_ids=intent.projects,
            domains=intent.domains,
            freshness=freshness,
            evidence=evidence,
            warnings=warnings,
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
        image_data: str = None,
        user_scope: UserScope | None = None,
    ):
        """Streaming version of process_message."""
        t0 = time.time()
        user_scope = user_scope or public_dev_scope()
        
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
            tool_results = []
            
            for chunk in run_deep_analysis_agent_stream(db, message, history, user_scope=user_scope):
                if isinstance(chunk, dict) and chunk.get("type") in ("tools_used", "tool_results"):
                    tools_used = chunk.get("tools", [])
                    tool_results = chunk.get("tool_results", [])
                else:
                    full_content += chunk
                    yield chunk
            
            latency = int((time.time() - t0) * 1000)
            freshness, sources, evidence, warnings, domains, project_ids = self._metadata_from_tool_results(tool_results)
            warnings.extend(verify_numeric_claims(full_content, tool_results))
            yield {
                "type": "metadata",
                "response": ChatResponse(
                    content=full_content,
                    intent_type="deep_analysis",
                    project_ids=project_names or project_ids,
                    domains=domains,
                    freshness=freshness,
                    evidence=evidence,
                    warnings=warnings,
                    sources_used=sources or tools_used,
                    latency_ms=latency,
                )
            }
            return
            
        # Branch 2: Standard Fast Pipeline
        intent = classify_intent(message, history, project_names)
        if project_names and not intent.projects and not intent.is_portfolio:
            intent.projects = project_names
        resolution = resolve_projects_from_intent(
            db,
            intent.projects,
            message=message,
            is_portfolio=intent.is_portfolio,
        )
        if resolution.status in ("ambiguous", "not_found"):
            full_content = resolution.question or "Which project should I use?"
            yield {
                "type": "clarification_required",
                "question": full_content,
                "candidates": [c.dict() for c in resolution.candidates],
            }
            latency = int((time.time() - t0) * 1000)
            yield {
                "type": "metadata",
                "response": ChatResponse(
                    content=full_content,
                    intent_type=intent.intent_type,
                    project_ids=[],
                    domains=intent.domains,
                    latency_ms=latency,
                    status="clarification",
                    clarification=full_content,
                    warnings=["project_resolution_required"],
                )
            }
            return
        if resolution.status == "not_project_specific" and intent.is_portfolio and not scope_allows_portfolio(user_scope):
            full_content = "You are not authorized to access portfolio-wide chatbot data."
            yield full_content
            yield {
                "type": "metadata",
                "response": self._unauthorized_response(
                    full_content,
                    intent.intent_type,
                    [],
                    intent.domains,
                    int((time.time() - t0) * 1000),
                    ["unauthorized_portfolio_access"],
                )
            }
            return

        intent.projects = resolution.project_ids
        intent.domains = self._select_domains(message, intent)
        authorization_failure = self._authorization_failure(intent, user_scope, int((time.time() - t0) * 1000))
        if authorization_failure:
            yield authorization_failure.content
            yield {"type": "metadata", "response": authorization_failure}
            return
        context_data, freshness, sources, evidence, warnings = self._gather_context(db, intent)
                    
        deterministic_content = self._try_deterministic_answer(message, context_data, intent)
        prompt = ""
        if deterministic_content:
            full_content = deterministic_content
            yield full_content
        elif intent.intent_type == "factual":
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

        warnings.extend(verify_numeric_claims(full_content, context_data))
                
        latency = int((time.time() - t0) * 1000)
        yield {
            "type": "metadata",
            "response": ChatResponse(
                content=full_content,
                intent_type=intent.intent_type,
                project_ids=intent.projects,
                domains=intent.domains,
                freshness=freshness,
                evidence=evidence,
                warnings=warnings,
                sources_used=sources,
                latency_ms=latency,
            )
        }

    def _gather_context(
        self,
        db: Session,
        intent: ChatIntent,
    ) -> tuple[dict, dict[str, SourceFreshness], list[str], list[EvidenceItem], list[str]]:
        """Gather context data for the requested projects and domains."""
        from engine.tools.p6_tools import (
            p6_get_activity_status_breakdown,
            p6_get_block_status,
            p6_get_critical_activities,
            p6_get_delayed_activities,
            p6_get_pending_activities,
            p6_get_portfolio_critical_activities,
            p6_get_project_summary,
        )
        from engine.tools.sap_tools import (
            sap_get_inventory,
            sap_get_material_gaps,
            sap_get_po_summary,
            sap_get_vendor_performance,
        )
        from engine.tools.tc_tools import tc_get_at_risk_lines, tc_get_network_summary, tc_get_project_lines
        
        context_data = {}
        freshness: dict[str, SourceFreshness] = {}
        evidence: list[EvidenceItem] = []
        warnings: list[str] = []
        sources = set()

        if not intent.projects:
            if "tc" in intent.domains:
                context_data["transmission_lines"] = tc_get_at_risk_lines(db, limit=15)
                context_data["transmission_summary"] = tc_get_network_summary(db)
                sources.add("tc_network")
                self._merge_freshness(freshness, "tc", None, "tc_network_edge")
                evidence.append(self._evidence("TC", "tc_network_edge"))
            
            if intent.is_portfolio or "p6" in intent.domains:
                from engine.tools.portfolio_tools import portfolio_get_riskiest_projects
                context_data["portfolio_risks"] = portfolio_get_riskiest_projects(db, top_n=5)
                sources.add("portfolio_aggregate")
                evidence.append(self._evidence("Portfolio", "portfolio_aggregate"))

                if self._needs_activity_context(intent.raw_question):
                    context_data["portfolio_critical_activities"] = p6_get_portfolio_critical_activities(db, limit=20)
                    sources.add("p6_activity")
                    evidence.append(self._evidence("P6", "p6_activity"))
            
            return context_data, freshness, list(sources), evidence, warnings

        for pid in intent.projects:
            sync_times = get_current_sync_times(db, pid)
            context_data[pid] = {}
            self._merge_freshness(freshness, "p6", sync_times.get("p6_synced_at"), "p6_project")
            self._merge_freshness(freshness, "sap", sync_times.get("sap_synced_at"), "mt_poamount")
            self._merge_freshness(freshness, "tc", sync_times.get("tc_synced_at"), "tc_network_edge")

            if "p6" in intent.domains:
                summary = p6_get_project_summary(db, pid)
                if summary:
                    context_data[pid]["p6_summary"] = summary
                    sources.add("p6_project")
                    evidence.append(self._evidence("P6", "p6_project", pid, summary.get("last_synced_at")))
                else:
                    warnings.append(f"No P6 project summary found for {pid}.")

                if intent.intent_type in ("analytical", "advisory") or self._needs_activity_context(intent.raw_question):
                    delayed = p6_get_delayed_activities(db, pid, limit=10)
                    critical = p6_get_critical_activities(db, pid, limit=10)
                    status_breakdown = p6_get_activity_status_breakdown(db, pid)
                    context_data[pid]["p6_delayed_activities"] = delayed
                    context_data[pid]["p6_critical_activities"] = critical
                    context_data[pid]["p6_activity_status"] = status_breakdown
                    sources.add("p6_activity")
                    evidence.append(self._evidence("P6", "p6_activity", pid, sync_times.get("p6_synced_at")))

                if self._needs_pending_activity_context(intent.raw_question):
                    context_data[pid]["p6_pending_activities"] = p6_get_pending_activities(db, pid, limit=50)
                    sources.add("p6_activity")
                    evidence.append(self._evidence("P6", "p6_activity", pid, sync_times.get("p6_synced_at")))

                if self._needs_block_context(intent.raw_question):
                    context_data[pid]["p6_block_status"] = p6_get_block_status(db, pid, limit=50)
                    sources.add("p6_activity")
                    sources.add("p6_wbs_node")
                    evidence.append(self._evidence("P6", "p6_activity,p6_wbs_node", pid, sync_times.get("p6_synced_at")))

            if "sap" in intent.domains:
                po_summary = sap_get_po_summary(db, pid)
                context_data[pid]["sap_po_summary"] = po_summary
                sources.add("mt_poamount")
                evidence.append(self._evidence("SAP", "mt_poamount", pid, po_summary.get("_synced_at")))

                if intent.intent_type in ("analytical", "advisory"):
                    context_data[pid]["sap_material_gaps"] = sap_get_material_gaps(db, pid, limit=10)
                    context_data[pid]["sap_vendor_performance"] = sap_get_vendor_performance(db, pid)
                    context_data[pid]["sap_inventory"] = sap_get_inventory(db, pid)

            if "tc" in intent.domains:
                tc_lines = tc_get_project_lines(db, pid)
                context_data[pid]["tc_lines"] = tc_lines
                sources.add("tc_network_edge")
                evidence.append(self._evidence("TC", "tc_network_edge", pid, tc_lines.get("_synced_at")))
                if not tc_lines.get("has_data"):
                    warnings.append(f"No transmission data found for {pid}.")

        return context_data, freshness, list(sources), evidence, warnings

    def _needs_activity_context(self, message: str | None) -> bool:
        msg = (message or "").lower()
        return any(term in msg for term in (
            "critical path",
            "critical activities",
            "which activities",
            "which activity",
            "dictates the overall project duration",
            "dictates overall project duration",
            "bottleneck activity",
            "bottleneck activities",
            "delayed activities",
            "dependencies",
        ))

    def _needs_pending_activity_context(self, message: str | None) -> bool:
        msg = (message or "").lower()
        mentions_activity = any(term in msg for term in ("p6", "activity", "activities", "task", "tasks"))
        mentions_pending = any(term in msg for term in (
            "pending",
            "remaining",
            "not started",
            "in progress",
            "unfinished",
            "open activities",
            "open activity",
        ))
        return mentions_activity and mentions_pending

    def _needs_block_context(self, message: str | None) -> bool:
        msg = (message or "").lower()
        mentions_block = any(term in msg for term in (
            "block",
            "blocks",
            "wtg",
            "cod",
            "trial",
        ))
        mentions_status = any(term in msg for term in (
            "pending",
            "remaining",
            "not completed",
            "not complete",
            "status",
            "cod",
            "trial",
            "commission",
            "commissioned",
        ))
        return mentions_block and mentions_status

    def _authorization_failure(
        self,
        intent: ChatIntent,
        user_scope: UserScope,
        latency_ms: int,
    ) -> ChatResponse | None:
        denied_project_ids = denied_projects(user_scope, intent.projects)
        denied_domain_names = denied_domains(user_scope, intent.domains)

        if denied_project_ids:
            return self._unauthorized_response(
                "You are not authorized to access one or more requested projects.",
                intent.intent_type,
                [],
                intent.domains,
                latency_ms,
                ["unauthorized_project_access"],
            )
        if denied_domain_names:
            return self._unauthorized_response(
                "You are not authorized to access one or more requested data domains.",
                intent.intent_type,
                intent.projects,
                [],
                latency_ms,
                ["unauthorized_domain_access"],
            )
        return None

    def _unauthorized_response(
        self,
        content: str,
        intent_type: str,
        project_ids: list[str],
        domains: list[str],
        latency_ms: int,
        warnings: list[str],
    ) -> ChatResponse:
        return ChatResponse(
            content=content,
            intent_type=intent_type,
            project_ids=project_ids,
            domains=domains,
            latency_ms=latency_ms,
            status="error",
            warnings=warnings,
        )

    def _select_domains(self, message: str, intent: ChatIntent) -> list[str]:
        msg = message.lower()
        domains = set(intent.domains or ["p6"])
        if any(term in msg for term in ("status", "health", "risk", "root cause", "why")):
            domains.update(["p6", "sap", "tc"])
        return sorted(domains)

    def _merge_freshness(
        self,
        freshness: dict[str, SourceFreshness],
        domain: str,
        as_of: str | None,
        source_name: str,
    ) -> None:
        if as_of:
            freshness[domain] = SourceFreshness(as_of=as_of, status="fresh")
        else:
            freshness[domain] = SourceFreshness(as_of=None, status="missing")

    def _evidence(
        self,
        source_system: str,
        source_type: str,
        project_id: str | None = None,
        as_of: str | None = None,
    ) -> EvidenceItem:
        return EvidenceItem(
            source_system=source_system,
            source_type=source_type,
            record_ids=[project_id] if project_id else [],
            project_id=project_id,
            as_of=as_of,
        )

    def _metadata_from_tool_results(
        self,
        tool_results: list[dict],
    ) -> tuple[dict[str, SourceFreshness], list[str], list[EvidenceItem], list[str], list[str], list[str]]:
        freshness: dict[str, SourceFreshness] = {}
        evidence: list[EvidenceItem] = []
        warnings: list[str] = []
        sources: set[str] = set()
        domains: set[str] = set()
        project_ids: list[str] = []

        for result in tool_results:
            tool_name = result.get("tool_name") or "unknown_tool"
            if result.get("status") in ("partial", "not_found", "unauthorized", "error"):
                warnings.append(f"{tool_name}: {result.get('status')}")
            if result.get("error"):
                warnings.append(f"{tool_name}: {result['error']}")
            warnings.extend(result.get("warnings") or [])

            for item in result.get("evidence") or []:
                try:
                    ev = EvidenceItem(**item)
                except Exception:
                    continue
                evidence.append(ev)
                if ev.source_type:
                    sources.add(ev.source_type)
                domain = self._domain_from_source_system(ev.source_system)
                domains.add(domain)
                if ev.project_id and ev.project_id not in project_ids:
                    project_ids.append(ev.project_id)
                if ev.as_of:
                    freshness[domain] = SourceFreshness(as_of=ev.as_of, status="fresh")
                elif domain not in freshness:
                    freshness[domain] = SourceFreshness(as_of=None, status="missing")

            if not result.get("evidence"):
                sources.add(tool_name)

        return freshness, sorted(sources), evidence, warnings, sorted(domains), project_ids

    def _domain_from_source_system(self, source_system: str | None) -> str:
        system = (source_system or "").lower()
        if system == "p6":
            return "p6"
        if system == "sap":
            return "sap"
        if system == "tc":
            return "tc"
        if system == "simulation":
            return "simulation"
        return "portfolio"

    def _try_deterministic_answer(self, message: str, context: dict, intent: ChatIntent) -> str | None:
        if len(intent.projects) != 1:
            return None
        project_data = context.get(intent.projects[0]) or {}
        msg = (message or "").lower()

        if self._needs_block_context(message) and "p6_block_status" in project_data:
            return self._format_block_status_answer(project_data["p6_block_status"])

        if self._needs_pending_activity_context(message) and "p6_pending_activities" in project_data:
            return self._format_pending_activities_answer(project_data["p6_pending_activities"])

        if self._asks_schedule_dates(msg) and "p6_summary" in project_data:
            return self._format_schedule_dates_answer(project_data["p6_summary"])

        if self._asks_duration(msg) and "p6_summary" in project_data:
            return self._format_duration_answer(project_data["p6_summary"])

        if self._asks_cost_or_capex(msg) and "p6_summary" in project_data:
            return self._format_cost_answer(
                project_data["p6_summary"],
                project_data.get("sap_po_summary"),
            )

        if "status" in msg and "p6_summary" in project_data:
            return self._format_project_status_answer(project_data["p6_summary"])

        return None

    def _asks_schedule_dates(self, msg: str) -> bool:
        mentions_date = any(term in msg for term in (
            "date", "dates", "start", "end", "finish", "completion",
            "planned start", "scheduled finish", "baseline finish",
        ))
        return mentions_date and not self._asks_duration(msg)

    def _asks_duration(self, msg: str) -> bool:
        return "duration" in msg or "how long" in msg

    def _asks_cost_or_capex(self, msg: str) -> bool:
        return any(term in msg for term in (
            "capex", "budget", "cost", "planned cost", "actual cost",
            "expenditure", "financial",
        ))

    def _fmt_value(self, value, suffix: str = "") -> str:
        if value is None:
            return "not available"
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return f"{value}{suffix}"

    def _fmt_money(self, value) -> str:
        if value is None:
            return "not available"
        try:
            numeric = float(value)
        except Exception:
            return str(value)
        if numeric == 0:
            return "0"
        crore = numeric / 10000000
        if abs(crore) >= 1:
            return f"INR {crore:,.2f} Cr"
        return f"INR {numeric:,.2f}"

    def _format_schedule_dates_answer(self, summary: dict) -> str:
        name = summary.get("project_name") or summary.get("name") or "this project"
        return "\n".join([
            f'Schedule dates for "{name}":',
            f"- Start date: **{self._fmt_value(summary.get('start_date'))}**",
            f"- Finish date: **{self._fmt_value(summary.get('finish_date'))}**",
            f"- Planned start: **{self._fmt_value(summary.get('planned_start'))}**",
            f"- Scheduled finish: **{self._fmt_value(summary.get('scheduled_finish'))}**",
            f"- Projected finish: **{self._fmt_value(summary.get('projected_finish'))}**",
            f"- Baseline start: **{self._fmt_value(summary.get('baseline_start'))}**",
            f"- Baseline finish: **{self._fmt_value(summary.get('baseline_finish'))}**",
        ])

    def _format_duration_answer(self, summary: dict) -> str:
        name = summary.get("project_name") or summary.get("name") or "this project"
        return "\n".join([
            f'Duration values for "{name}":',
            f"- Planned duration: **{self._fmt_value(summary.get('planned_duration'), ' hours')}**",
            f"- Actual duration: **{self._fmt_value(summary.get('actual_duration'), ' hours')}**",
            f"- Remaining duration: **{self._fmt_value(summary.get('remaining_duration'), ' hours')}**",
            f"- Baseline duration: **{self._fmt_value(summary.get('baseline_duration'), ' hours')}**",
        ])

    def _format_cost_answer(self, summary: dict, sap_po_summary: dict | None = None) -> str:
        name = summary.get("project_name") or summary.get("name") or "this project"
        fields = {
            "Current budget": summary.get("current_budget"),
            "Planned cost": summary.get("planned_cost"),
            "Actual total cost": summary.get("actual_total_cost"),
            "Baseline total cost": summary.get("baseline_total_cost"),
            "Total cost variance": summary.get("total_cost_variance"),
        }
        has_populated_cost = any(value not in (None, 0, 0.0) for value in fields.values())
        lines = [f'Cost/CAPEX values for "{name}":']
        if not has_populated_cost:
            lines.append("- I do not have a populated CAPEX/current budget value in the current P6 project data.")
        for label, value in fields.items():
            lines.append(f"- {label}: **{self._fmt_money(value)}**")

        po_summary = (sap_po_summary or {}).get("summary") or {}
        if po_summary:
            lines.append(f"- SAP PO total value: **{self._fmt_money(po_summary.get('total_value_inr'))}**")
        elif sap_po_summary is not None:
            lines.append("- SAP PO total value: **not available**")
        return "\n".join(lines)

    def _format_project_status_answer(self, summary: dict) -> str:
        name = summary.get("project_name") or summary.get("name") or "This project"
        project_state = summary.get("status") or "not available"
        schedule_status = summary.get("schedule_status") or "not available"
        reason = summary.get("schedule_status_reason")

        lines = [
            f'The P6 project state of "{name}" is **{project_state}**.',
            f"The schedule health status is **{schedule_status}**.",
        ]
        if reason:
            lines.append(f"Reason: {reason}")

        pending = summary.get("pending_activities")
        delayed = summary.get("delayed_activity_count")
        delayed_pending = summary.get("delayed_pending_activity_count")
        delayed_completed = summary.get("delayed_completed_activity_count")
        if pending is not None or delayed is not None:
            lines.append(
                "Activity context: "
                f"**{pending if pending is not None else 'not available'}** pending activities; "
                f"**{delayed if delayed is not None else 'not available'}** delayed vs baseline"
                + (
                    f" (**{delayed_pending}** pending, **{delayed_completed}** completed)."
                    if delayed_pending is not None and delayed_completed is not None
                    else "."
                )
            )

        return "\n".join(lines)

    def _format_pending_activities_answer(self, pending: dict) -> str:
        name = pending.get("project_name") or "this project"
        total = pending.get("total_pending", 0)
        breakdown = pending.get("status_breakdown") or {}
        activities = pending.get("activities") or []

        if total == 0:
            return f'There are no pending activities related to "{name}".'

        lines = [
            f'There are **{total}** pending P6 schedule activities related to "{name}".',
            "",
            "**Summary**",
            f"- In Progress: **{breakdown.get('In Progress', 0)}**",
            f"- Not Started: **{breakdown.get('Not Started', 0)}**",
        ]
        if pending.get("delayed_pending_count") is not None:
            lines.append(f"- Delayed vs baseline among pending activities: **{pending.get('delayed_pending_count')}**")
        if pending.get("critical_pending_count") is not None:
            lines.append(f"- Critical among pending activities: **{pending.get('critical_pending_count')}**")

        lines.extend([
            "",
            "These are schedule activities. If an activity name contains `Block-01`, `Block-02`, or `Block-03`, that does not mean the COD block itself is pending.",
        ])

        grouped = {
            "In Progress": [activity for activity in activities if activity.get("status") == "In Progress"],
            "Not Started": [activity for activity in activities if activity.get("status") == "Not Started"],
        }
        for status, status_activities in grouped.items():
            if not status_activities:
                continue
            lines.extend(["", f"**{status}**"])
            for activity in status_activities:
                name_value = activity.get("name") or activity.get("activity_id") or "Unnamed activity"
                drift = activity.get("drift_days")
                suffix = f"; drift: {drift} days" if drift is not None else ""
                lines.append(f"- {name_value}{suffix}")

        activities = []

        lines.append("")
        for activity in activities:
            status = activity.get("status") or "Unknown"
            name_value = activity.get("name") or activity.get("activity_id") or "Unnamed activity"
            drift = activity.get("drift_days")
            suffix = f" | drift: {drift} days" if drift is not None else ""
            lines.append(f"- {name_value} — {status}{suffix}")

        if pending.get("has_more"):
            lines.append(f"- Showing {pending.get('returned_count')} of {total} pending activities.")

        return "\n".join(lines)

    def _format_block_status_answer(self, block_status: dict) -> str:
        name = block_status.get("project_name") or "this project"
        total = block_status.get("total_blocks", 0)
        pending_count = block_status.get("pending_cod_blocks", 0)
        completed_count = block_status.get("cod_completed_blocks", 0)
        pending_blocks = block_status.get("pending_blocks") or []

        if not block_status.get("has_data"):
            return f'I do not have block/COD status data for "{name}" in the current P6 data.'
        if pending_count == 0:
            return (
                f'There are **0** pending COD blocks related to "{name}". '
                f"All **{completed_count}** of **{total}** blocks have completed COD."
            )

        lines = [
            f'There are **{pending_count}** pending COD blocks related to "{name}".',
            f"COD completed blocks: **{completed_count}** of **{total}**.",
            "",
        ]
        for block in pending_blocks:
            lines.append(f"- {block.get('block')} — {block.get('overall_status')}")
        return "\n".join(lines)

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
4. NEVER hardcode answers, guess, or hallucinate data. If the provided data does not contain the answer, say "I don't have that in the current data."
5. Do not calculate official business values. Use numbers exactly as supplied by deterministic tools.
6. If any needed source is missing in the data, state that plainly.

{hist_str}
{memory}

DATA FOR {', '.join(intent.projects)}:
```json
{json.dumps(context, indent=2, default=str)}
```

Question: {message}
"""

    def _handle_factual(self, message: str, context: dict, history: list, intent: ChatIntent, db: Session) -> str:
        return self._generate(self._build_prompt_factual(message, context, history, intent, db))

    def _handle_analytical(self, message: str, context: dict, history: list, intent: ChatIntent, db: Session) -> str:
        return self._generate(self._build_prompt_analytical(message, context, history, intent, db))

    def _handle_advisory(self, message: str, context: dict, history: list, intent: ChatIntent, db: Session) -> str:
        return self._generate(self._build_prompt_advisory(message, context, history, intent, db))

    def _build_prompt_analytical(self, message: str, context: dict, history: list, intent: ChatIntent, db: Session) -> str:
        memory = build_memory_context(db, intent.projects[0] if intent.projects else None, message)
        return f"""You are the Akasha AI Copilot — a senior EPC project analyst.
RULES:
1. Write like a senior analyst briefing the CEO — direct, factual, no fluff. Use **bold** for key numbers/variances.
2. If the user asks a general question about your capabilities or greets you, respond conversationally and helpfully.
3. NEVER hardcode answers, guess, or hallucinate data. If the provided data does not contain the answer, say "I don't have that in the current data."
4. Do not calculate official business values. Use numbers exactly as supplied by deterministic tools.
5. Separate verified facts from likely relationships and assumptions.
6. Recommendations must be evidence-backed and non-executing.

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
1. Don't just report data — advise on what to do next. Provide actionable mitigations based on the data.
2. Flag critical path risks immediately. Highlight high-severity bottlenecks.
3. Be direct. No filler words. Maximum 3 paragraphs.
4. If the user asks a general question about your capabilities or greets you, respond conversationally and helpfully.
5. NEVER hardcode answers, guess, or hallucinate data. If the provided data does not contain the answer, say "I don't have that in the current data."
6. Do not calculate official business values. Use numbers exactly as supplied by deterministic tools.
7. Recommendations must be evidence-backed and non-executing.

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
        from engine.model_gateway import complete_text

        provider = self.default_llm if self.default_llm in {"azure", "groq", "openrouter", "ollama"} else None
        return complete_text(
            [{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2048,
            provider=provider,
        )

    def _generate_stream(self, prompt: str):
        """Call the appropriate LLM backend with streaming."""
        from engine.model_gateway import stream_text

        provider = self.default_llm if self.default_llm in {"azure", "groq", "openrouter", "ollama"} else None
        yield from stream_text(
            [{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2048,
            provider=provider,
        )


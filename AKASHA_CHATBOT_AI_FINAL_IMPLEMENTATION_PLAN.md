# Akasha Chatbot AI — Final Recommended Implementation Plan

**Status:** Final recommended implementation reference  
**Scope:** Akasha chatbot and chatbot-related AI capabilities only  
**Primary objective:** Add reliable AI and bounded Agentic AI to the existing chatbot without building an unnecessarily complex multi-agent platform  
**Implementation principle:** Improve and harden the existing system; do not rewrite it

---

## 1. Executive Decision

Akasha should be implemented as a **governed hybrid AI copilot**:

- Use a fast, grounded AI flow for ordinary factual and single-domain questions.
- Use one bounded agentic analysis flow for complex, multi-step, cross-platform questions.
- Keep calculations, authorization, validation, and business actions in deterministic application code.
- Allow the LLM to understand questions, select approved read tools, organize evidence, explain findings, and propose recommendations.
- Do not allow the LLM to execute consequential business actions without explicit policy checks and human approval.

The final architecture contains:

- **One Akasha AI orchestrator/runtime.**
- **Zero separately deployed specialist agents in the initial implementation.**
- Multiple typed domain tools for P6, SAP/Module Tracker, transmission, portfolio data, notifications, and validated simulations.
- An evidence verifier and answer composer inside the same governed runtime.

This approach is legitimately agentic. An agentic system does not require many independent agents. It requires a controlled loop in which the system can understand a goal, choose approved tools, inspect results, verify evidence, and complete a bounded task.

---

## 2. Business Goal

Akasha already combines information from P6, SAP-style material data, Module Tracker tables, transmission connectivity, notifications, project mappings, and dashboard calculations. The chatbot should make this information easier to understand and act on.

The target user experience is:

> A user asks one project question in natural language. Akasha resolves the correct project, retrieves the necessary trusted data, explains what is happening, identifies why it may be happening, and recommends the next step while keeping humans responsible for decisions and actions.

### Priority business workflows

The first release must perform these two workflows extremely well:

1. **Grounded project status**
   - Example: “Give me the current status of project X.”
   - Expected behavior: resolve the project, retrieve only the required metrics, show freshness per source, and return exact values with evidence.

2. **Cross-domain risk/root-cause analysis**
   - Example: “Why is project X at risk?”
   - Expected behavior: inspect relevant P6, material/procurement, transmission, and notification evidence; distinguish facts from correlations and assumptions; identify missing evidence; and propose non-executing recommendations.

Everything else is secondary until these two workflows meet the testing and acceptance gates in this document.

---

## 3. Current-State Classification

Implementation must distinguish between capabilities that exist, capabilities that are prototypes, and capabilities that are only targets.

### 3.1 Implemented foundations

- React/Vite chatbot and dashboard frontend.
- FastAPI backend and PostgreSQL/SQLAlchemy data layer.
- P6 projects, WBS, activities, baselines, resources, and risk data.
- SAP/Module Tracker purchase-order, inventory, consumption, transit, and material data.
- Transmission project and network data.
- Project mapping across data sources.
- Standard chatbot intent classification and prompt-based answer generation.
- Project 360 context assembly and freshness-aware caching.
- Optional Deep Analysis ReAct tool loop.
- Allowlisted P6, SAP, transmission, portfolio, notification, and simulation tool definitions.
- Chat session/message/feedback persistence models.
- Multiple model-provider integrations.
- Executive briefing, project diagnostic, notification suggestions, and simulation endpoints.

### 3.2 Prototype capabilities that require hardening

- Authentication exists in the UI/API but tokens are not effectively validated or authorized.
- Project resolution uses first-match fuzzy behavior and has no candidate/clarification contract.
- Standard mode can send an oversized Project 360 context regardless of the exact question.
- Provenance records tool/table labels but not claim-level evidence.
- Freshness is collapsed into one timestamp and has missing-timestamp edge cases.
- Deep Analysis is agent-like but has no explicit evidence/completion verifier.
- Deep Analysis streaming can regenerate the final answer instead of streaming the answer that ended the tool loop.
- Browser history and server history can diverge.
- Feedback corrections can be injected without review or trust metadata.
- Chat clients do not all implement the same SSE contract.
- Provider behavior, streaming, timeouts, and error handling are inconsistent.
- Some tools and SQLAlchemy models have schema drift.
- Existing simulations vary in maturity and are not all validated forecasting models.

### 3.3 Target capabilities — do not describe as currently implemented

- Verified chatbot DPR tools and data contracts.
- Complete CAPEX, cash-flow, and financial forecast tools.
- Claim-level citations and evidence ledger.
- Durable resumable agent tasks.
- Governed write actions and approval workflows.
- Document RAG with ACLs and versioned citations.
- Safe generated SQL.
- Long-term semantic user memory.

---

## 4. Locked Architecture Decisions

These decisions apply unless the product owner explicitly approves a change to this document.

| Area | Final decision |
|---|---|
| Overall approach | Hybrid grounded AI plus bounded Agentic AI |
| Runtime count | One governed chatbot orchestrator/runtime |
| Specialist agents | Do not create separately deployed specialist agents initially |
| Domain capabilities | Implement as typed tools and bounded workflows |
| Default behavior | Use the fast grounded flow for simple questions |
| Agentic behavior | Use only for questions requiring multiple tools or iterative analysis |
| Business calculations | Deterministic Python/SQL services, not LLM-generated numbers |
| Recommendations | Evidence-backed, non-executing, and clearly labeled |
| SQL | Typed tools, views, and parameterized templates first; no free-form SQL agent |
| RAG | Add only for confirmed document-search use cases |
| LangGraph | Do not add initially; reconsider only for durable state, resumability, or HITL branching |
| Redis | Do not add solely for AI; add only when multi-worker state, rate limiting, or job status requires it |
| Vector database | Do not add until document RAG is approved |
| Frontend | Keep React/Vite and select one canonical chatbot client |
| Backend | Keep FastAPI and PostgreSQL |
| Production identity | Require a validated identity and project/role scopes; Entra ID may be the enterprise provider |
| Write actions | Out of scope until the read-only chatbot passes release gates |
| Human approval | Mandatory before consequential writes |

### Explicitly prohibited initial changes

- Do not build an eight-agent or multi-agent swarm architecture.
- Do not create a separate agent for project, logistics, finance, recommendation, simulation, summary, or approval.
- Do not introduce generated SQL in Phase 0 or Phase 1.
- Do not add document embeddings or a vector database in Phase 0 or Phase 1.
- Do not let the LLM calculate official business values.
- Do not expose existing P6 or other write endpoints to the agent.
- Do not introduce autonomous actions to satisfy an “agentic” label.
- Do not perform a broad frontend or backend rewrite.

---

## 5. Target Runtime Architecture

```text
User
  |
  v
Canonical Chat UI
  |
  v
Authenticated Chat API
  |
  v
One Akasha AI Orchestrator
  |
  +--> Request validation and user/project scope
  +--> Intent, entities, and complexity decision
  +--> Deterministic project resolution or clarification
  |
  +--> Fast Grounded Flow
  |      +--> Context selector
  |      +--> Typed read tools/query templates
  |      +--> Evidence verifier
  |      +--> Answer composer
  |
  +--> Bounded Agentic Analysis Flow
         +--> Small inspectable plan
         +--> Approved typed read/simulation tools
         +--> Step/time/token budgets
         +--> Evidence and completion verifier
         +--> Answer/recommendation composer
  |
  v
SSE answer + evidence + freshness + metadata
  |
  v
Trace, audit metadata, feedback, and evaluation
```

### Deterministic and generative responsibilities

| Responsibility | Deterministic code | LLM |
|---|---:|---:|
| Authenticate user | Yes | No |
| Enforce role/project scope | Yes | No |
| Resolve exact known project IDs | Yes | No |
| Return ambiguous project candidates | Yes | No |
| Choose clarification wording | Optional | Yes |
| Query databases | Yes | No direct DB access |
| Calculate SPI/CPI, dates, counts, totals | Yes | No |
| Run validated simulations | Yes | No |
| Select from approved tools in agentic mode | Policy-constrained | Yes |
| Verify numeric consistency | Yes | No |
| Compose explanation | No | Yes |
| Separate facts, assumptions, and recommendations | Contract-validated | Yes |
| Approve business action | Human/policy | No |
| Execute business action | Governed service only | No direct execution |

---

## 6. Runtime Modes and Routing

### 6.1 Fast grounded mode

Use this mode when one retrieval step or one domain can answer the question.

Examples:

- What is the project SPI?
- What is the current finish date?
- How many activities are delayed?
- Show current material availability.
- Which transmission lines are delayed?
- Summarize this project’s status.

Flow:

```text
classify -> resolve project -> select minimal tools -> retrieve -> verify -> answer
```

The fast flow should be the default because it is cheaper, faster, easier to test, and more deterministic.

### 6.2 Bounded agentic analysis mode

Use this mode only when the question requires multiple domains, iterative evidence collection, comparison, or a simulation.

Examples:

- Why is project X at risk?
- Is the schedule delay linked to a material or transmission issue?
- Compare the highest-risk projects and explain the different causes.
- Can an additional crew recover the delay before COD?
- What recovery options should management review?

Flow:

```text
goal -> bounded plan -> tool calls -> evidence ledger -> verification -> completion check -> answer
```

Initial bounds:

- Read-only and validated simulation tools only.
- Maximum tool steps configured centrally.
- Maximum runtime and token budget configured centrally.
- No recursive agent-to-agent delegation.
- No hidden business writes.
- Stop when the required evidence is collected, the goal is satisfied, or a configured budget is reached.
- If evidence is insufficient, state what is missing instead of inventing a conclusion.

### 6.3 Clarification and safe fallback mode

The chatbot must ask a clarification question instead of guessing when:

- More than one project is a credible match.
- No project can be resolved for a project-specific question.
- The requested date range, unit, metric, or scenario input is materially ambiguous.
- The user requests a capability that is not implemented.
- The available sources are missing, stale beyond policy, or contradictory.

### 6.4 Routing implementation

Use the minimum routing complexity needed:

1. Deterministic rules for explicit project IDs, clear domain terms, safety restrictions, and capability boundaries.
2. Structured LLM classification for ambiguous intent/entity extraction.
3. Confidence/candidate gating that leads to clarification, never silent guessing.

Do not add semantic embedding routing initially. Akasha has a small number of related project domains, unlike a consumer platform routing unrelated payment, KYC, support, and product intents. Add semantic routing only if evaluation proves that deterministic plus structured LLM routing cannot meet the agreed accuracy target.

---

## 7. Core Contracts

All contracts should use versioned Pydantic models or equivalent typed structures. Do not pass unvalidated dictionaries between major runtime stages.

### 7.1 Chat request

```json
{
  "message": "Why is project X at risk?",
  "conversation_id": "uuid",
  "project_hint": "optional canonical id or display name",
  "mode": "auto | fast | analysis",
  "image": null,
  "client_version": "string"
}
```

Rules:

- User identity, role, and allowed project scopes come from validated authentication, not request JSON.
- The server owns trusted conversation history.
- `mode=analysis` requests bounded agentic analysis; it does not bypass policy or verification.
- `mode=auto` is the default after routing behavior is tested.

### 7.2 SSE event contract

Use a single shared frontend parser and a versioned event contract.

Required event types:

```text
run_started
status
answer_delta
clarification_required
evidence
warning
error
run_completed
```

`run_completed` must contain:

```json
{
  "run_id": "uuid",
  "conversation_id": "uuid",
  "message_id": 123,
  "mode": "fast | analysis",
  "intent": "factual | analytical | advisory | document | unsupported",
  "project_ids": [],
  "domains": [],
  "sources": [],
  "freshness": {},
  "warnings": [],
  "latency_ms": 0,
  "status": "success | partial | clarification | error"
}
```

The client parser must retain incomplete SSE fragments between network chunks.

### 7.3 Tool input contract

Each tool must declare:

- Stable name and version.
- Typed input schema.
- Required user/project scopes.
- Risk class.
- Timeout policy.
- Result-size limit.
- Freshness behavior.
- Whether retries are safe.

### 7.4 Tool result envelope

```json
{
  "status": "success | partial | not_found | unauthorized | error",
  "data": {},
  "evidence": [
    {
      "source_system": "P6",
      "source_type": "p6_activity",
      "record_ids": [],
      "project_id": "canonical-id",
      "as_of": "ISO-8601",
      "retrieved_at": "ISO-8601",
      "calculation": null,
      "calculation_version": null
    }
  ],
  "warnings": [],
  "error": null
}
```

The LLM must never receive a raw exception or raw database error.

### 7.5 Agentic run state

Use a small typed state object for analysis mode:

```json
{
  "run_id": "uuid",
  "conversation_id": "uuid",
  "user_scope": {"role": "...", "project_ids": []},
  "goal": "Identify evidence-backed causes of project risk",
  "entities": {"project_ids": [], "domains": []},
  "plan": [],
  "tool_results": [],
  "evidence": [],
  "warnings": [],
  "budgets": {"max_steps": 0, "max_seconds": 0, "max_tokens": 0},
  "completion": {"status": "pending", "reason": null},
  "final_answer": null,
  "errors": []
}
```

Do not introduce durable checkpoint infrastructure until a real workflow must survive restarts or wait for approval.

### 7.6 Answer contract

Serious analytical answers must clearly separate:

1. **Answer/summary**
2. **Verified facts**
3. **Analysis or likely relationships**
4. **Assumptions**
5. **Recommendation**
6. **Missing or stale information**
7. **Sources and freshness**

Simple factual questions should remain concise and should not be forced into this long format.

### 7.7 Confidence signals

Do not expose one generic “AI confidence” percentage. Track separate signals:

- `project_resolution_confidence`
- `intent_confidence`
- `evidence_completeness`
- `freshness_status` per source
- `simulation_uncertainty`
- `recommendation_strength`

When a signal is not statistically calibrated, label it as a rule-based status such as `high`, `medium`, `low`, or `insufficient`, and document how it is derived.

---

## 8. Data Grounding and Project Resolution

### 8.1 Project mapping is the integration spine

P6, SAP/Module Tracker, and transmission data must resolve through canonical project identity. The chatbot must not depend on the LLM to invent or infer canonical IDs.

Recommended resolution order:

1. Exact canonical `project_id`.
2. Exact normalized P6 project ID/name.
3. Exact mapped business/SPV/project name.
4. Approved alias table.
5. Ranked fuzzy candidates with a score.
6. User clarification when the best candidate is not uniquely strong.

Never silently convert an unresolved project-specific request into a portfolio request.

### 8.2 Context selection

Do not send the complete Project 360 object for every question.

Create domain-specific context builders or typed tools for:

- P6 schedule summary.
- Critical/delayed activities.
- Material/procurement summary.
- Inventory and consumption.
- Vendor performance.
- Transmission readiness and delayed lines.
- Notifications.
- Portfolio risk.
- Validated simulations.

Each response should retrieve the smallest evidence set that can answer the question.

### 8.3 Freshness

Freshness must be reported per source:

```json
{
  "p6": {"as_of": "...", "status": "fresh | stale | missing"},
  "sap": {"as_of": "...", "status": "fresh | stale | missing"},
  "transmission": {"as_of": "...", "status": "fresh | stale | missing"}
}
```

Do not use the newest source timestamp as the answer’s single “data as of” value. A fresh P6 sync must not hide stale SAP data.

Cache invalidation must treat a missing timestamp, changed timestamp, source addition/removal, or calculation-version change as potentially stale.

### 8.4 Evidence

Every material claim must be traceable to:

- Source system/table or approved view.
- Canonical project ID.
- Record IDs or aggregation/query identifier.
- Source timestamp.
- Retrieval timestamp.
- Calculation name and version when derived.

The UI may initially display a concise source list, but the backend trace must retain full evidence metadata.

---

## 9. Domain Tool Strategy

### 9.1 Initial approved tool domains

- P6 project summary, status, activity, baseline, critical-path, delay, and WBS reads.
- SAP/Module Tracker PO, material gap, inventory, consumption, transit, and vendor reads.
- Transmission project-line, delayed-line, and network reads.
- Portfolio project resolution, list, risk, and notification reads after schema correction.
- Validated deterministic simulations.

### 9.2 Tool implementation rules

- Enforce project scope inside the tool/service, not only in the orchestrator.
- Validate all arguments before querying.
- Set maximum row/result limits.
- Return the typed result envelope.
- Include per-tool timeouts and structured failures.
- Redact sensitive values before prompts, logs, and traces.
- Version business calculations.
- Unit-test tools independently of the LLM.

### 9.3 DPR and financial tools

DPR and finance must not be added merely as labels.

Before exposing either domain to the chatbot:

1. Identify the authoritative source and data owner.
2. Define the canonical project mapping.
3. Create typed models/views.
4. Implement read-only tools.
5. Define freshness and evidence contracts.
6. Validate sample answers with a domain SME.
7. Add golden evaluation cases.

### 9.4 SQL policy

Use this progression:

1. Typed domain tools.
2. Approved analytical views.
3. Parameterized query templates.
4. Measure unanswered user questions.
5. Consider generated SQL only if a documented coverage gap remains.

Generated SQL, if ever approved, must run through an isolated read-only database role and must include AST/parser validation, a schema allowlist, function allowlist, one-statement enforcement, row limits, query-cost/time limits, redacted errors, and complete audit logs.

Generated SQL is not part of the initial implementation.

---

## 10. Simulation and Recommendation Policy

### 10.1 Simulation

The LLM may collect scenario inputs and explain results. It must not invent the calculation.

Before a simulation is production-ready:

- Remove placeholder or narrative-only outputs.
- Define input units and valid ranges.
- Validate zero, negative, missing, and extreme inputs.
- Make fixed-seed runs reproducible where randomness is used.
- Record assumptions and calculation version.
- Back-test against historical projects when data exists.
- Obtain domain/P6 SME review.
- Label results as estimates, not guaranteed forecasts.

### 10.2 Recommendations

Every recommendation must include:

- Recommended action.
- Reason.
- Supporting evidence.
- Expected benefit or impact.
- Risks/tradeoffs.
- Missing information.
- Recommendation strength.
- Whether approval would be required if the action were implemented.

Recommendations remain non-executing through Phase 2.

### 10.3 Executive summaries

Executive summaries should be scheduled/report workflows, not separate agents.

They must:

- Use the same typed tools and evidence contracts as chat.
- Display source freshness.
- Be reviewable before distribution.
- Record the model/prompt/tool/calculation versions used.
- Avoid claiming unsupported financial, DPR, or causal conclusions.

---

## 11. Authentication, Authorization, Security, and Privacy

These requirements are prerequisites, not optional future enhancements.

### 11.1 Identity and access

- Validate every bearer token/session server-side.
- Replace simple SHA-256 password storage if local credentials remain.
- Prefer the organization’s approved identity provider, such as Microsoft Entra ID, for production.
- Resolve user identity, role, and permitted projects from trusted server-side data.
- Apply role/project scopes to chat retrieval and every domain tool.
- Protect existing sync, mapping, notification, P6 update, and password-management endpoints.
- Never trust identity, role, account, or project authority supplied in the user message or request body.

### 11.2 Transport and configuration

- Remove global TLS verification bypasses before production.
- Restrict CORS to approved origins.
- Move secrets to environment/secret management.
- Do not return raw provider, database, or stack errors to clients.
- Configure request size limits, image limits, rate limits, timeouts, and model/tool budgets.

### 11.3 Prompt and data safety

- Treat user messages, browser history, tool results, uploaded images, and future documents as untrusted content.
- Separate system policy from retrieved content.
- Do not let tool/document text redefine tool permissions.
- Redact secrets and sensitive fields from prompts and traces.
- Establish provider/data-residency approval before sending project data to an external model.
- Disable production image analysis until retention, redaction, and provider policy are approved.

### 11.4 Action risk classes

Define the policy now even though writes are deferred:

| Class | Example | Initial behavior |
|---|---|---|
| Read | Get delayed activities | Allowed within user/project scope |
| Calculate | Run validated simulation | Allowed; label assumptions |
| Recommend | Suggest recovery action | Allowed; non-executing |
| Draft | Draft notification/escalation | Future; user review required |
| Reversible write | Acknowledge/assign notification | Future; authorization + explicit approval + idempotency |
| Consequential write | Update P6 date/resources | Future; preview + role authorization + approval + audit + read-back verification |
| Irreversible/high-risk | Delete/bulk overwrite | Do not expose to the agent |

---

## 12. Conversation Memory and Feedback

### 12.1 Conversation state

- Make the server the source of truth for conversation history.
- Bind conversations to authenticated user and tenant/project scope.
- The browser may cache UI state but must not define trusted history.
- Re-fetch volatile project values on each relevant turn instead of trusting prior answers.
- Keep only a bounded number of recent turns in prompts; summarize long conversations when needed.

### 12.2 Feedback

Do not describe unreviewed correction injection as model learning.

Store feedback with:

- User/author.
- Conversation and message IDs.
- Project/domain scope.
- Feedback type.
- Proposed correction.
- Review status.
- Reviewer.
- Valid-from/expiry fields where relevant.
- Source/evidence supporting an accepted correction.

Only reviewed corrections may become reusable prompt guidance or evaluation cases. User feedback is useful for prioritization but does not prove factual correctness.

### 12.3 Long-term memory

Do not add semantic long-term user memory initially. Akasha’s first requirement is correct operational data retrieval, not personalized consumer conversation. Reconsider only after a defined business case, retention policy, deletion workflow, and access-control model exist.

---

## 13. Observability and Audit Requirements

Every chatbot run must record:

- Run ID, conversation ID, message ID.
- Authenticated user ID, role, and project scope reference.
- Runtime mode and completion reason.
- Intent/entities and project-resolution result.
- Model provider, model, parameters, and prompt version.
- Tool name/version, redacted arguments, duration, result status, and evidence references.
- Calculation name/version.
- Per-source freshness.
- Token usage, latency, retries, and timeouts where available.
- Warnings, verifier outcome, final status, and feedback.

Do not log secrets, raw credentials, unredacted images, or unnecessary sensitive project content.

Initial implementation may use structured application logs plus PostgreSQL trace metadata. Do not require a new observability vendor. OpenTelemetry or another platform may be added later when operational ownership is established.

---

## 14. Phased Implementation Plan

Implement phases in order. Do not begin optional infrastructure while an earlier exit gate is unmet.

### Phase 0 — Baseline, protection, and contract stabilization

**Goal:** Make the existing chatbot internally consistent, secure enough for controlled development, and measurable before expanding agentic behavior.

#### Work items

1. Select `frontend/src/features/chatbot/AICopilot.tsx` as the canonical chatbot experience.
2. Create one shared frontend chat/SSE client and migrate every active chat caller to it or remove/deprecate unused callers.
3. Implement correct SSE buffering, cancellation, terminal events, and structured errors.
4. Add request/run IDs and structured logs.
5. Extract model-provider calls from `backend/routers/ai.py` into one model gateway with consistent streaming, timeouts, errors, and provider metadata.
6. Implement effective token/session validation and role/project authorization.
7. Protect existing write/sync/admin-style endpoints.
8. Remove production TLS bypass behavior and restrict CORS.
9. Fix notification model/tool schema drift.
10. Fix cache missing-timestamp and per-source freshness behavior.
11. Fix duplicate final generation in Deep Analysis streaming.
12. Define the typed chat, SSE, tool, evidence, and answer contracts from this document.
13. Build the initial golden evaluation dataset and automated test harness.
14. Record the current baseline for correctness, project resolution, latency, failure rate, and tool selection.

#### Primary code areas

- `backend/main.py`
- `backend/routers/auth.py`
- `backend/routers/ai.py`
- `backend/engine/orchestrator.py`
- `backend/engine/agent.py`
- `backend/engine/cache.py`
- `backend/engine/intent.py`
- `backend/engine/tools/portfolio_tools.py`
- `backend/models.py`
- `frontend/src/features/chatbot/AICopilot.tsx`
- Other active chatbot callers identified through repository search

#### Exit criteria

- One API/SSE contract is used by every active chatbot surface.
- Authentication and project scope are enforced in backend tests.
- No global TLS bypass remains in the production path.
- Tool/model/schema inconsistencies listed above are resolved.
- Golden cases run automatically and baseline metrics are recorded.
- No new agent, RAG, generated SQL, or write capability has been introduced.

### Phase 1 — Trusted hybrid AI chatbot

**Goal:** Deliver the minimum-complexity production candidate: reliable grounded answers plus bounded read-only agentic analysis for the two priority workflows.

#### Work items

1. Implement deterministic project resolution with ranked candidates and clarification.
2. Implement domain-aware context selection instead of full Project 360 prompt dumps.
3. Convert read tools to typed inputs and the common result envelope.
4. Enforce scopes inside every tool/service.
5. Add evidence IDs, calculation versions, and per-source freshness.
6. Add deterministic verification for important numbers, dates, counts, units, and totals.
7. Implement fast grounded mode for factual/single-domain questions.
8. Harden the existing Deep Analysis loop into bounded analysis mode:
   - explicit goal;
   - small plan;
   - step/time/token budgets;
   - typed tool results;
   - evidence ledger;
   - completion verifier;
   - no writes.
9. Implement the grounded project-status workflow.
10. Implement the cross-domain risk/root-cause workflow.
11. Make server conversation history authoritative.
12. Change feedback memory so only reviewed corrections can influence future answers.
13. Display concise source/freshness/warning metadata in the canonical UI.

#### Suggested minimal backend boundaries

The exact filenames may follow repository conventions, but responsibilities must be separated:

- Thin HTTP chat router.
- Model gateway.
- Orchestrator.
- Project resolver.
- Context selector.
- Typed tool registry/executor.
- Evidence verifier.
- Answer composer/prompt templates.
- Trace/persistence service.

Do not create a framework-heavy abstraction for a responsibility with only one implementation.

#### Exit criteria

- Both priority workflows meet agreed evaluation thresholds.
- Ambiguous projects produce clarification rather than an incorrect answer.
- No unauthorized or cross-project evidence reaches the model or response.
- Every material claim has evidence and source freshness.
- Numeric factual answers match deterministic source results.
- Agentic runs remain within configured budgets.
- Unsupported conclusions are removed or clearly labeled.
- Fast mode remains the default for simple questions.

### Phase 2 — Validated simulations, recommendations, and executive outputs

**Goal:** Add higher-value analysis only after the trusted hybrid chatbot is stable.

#### Work items

1. Inventory every simulation and classify it as validated, experimental, or placeholder.
2. Remove or disable placeholder simulations.
3. Validate supported models with P6/domain SMEs and historical data.
4. Add simulation input validation, reproducibility, assumptions, uncertainty, and calculation versions.
5. Implement structured recommendation output based on verified evidence.
6. Store recommendation review/outcome history.
7. Convert executive briefing generation to use the same tools, evidence, verifier, and freshness contracts.
8. Add scheduled execution only when ownership and review flow are defined.
9. Add verified DPR or finance tools only after completing the prerequisites in Section 9.3.

#### Exit criteria

- No placeholder or LLM-invented simulation result is exposed as factual.
- Validated simulations pass reproducibility, boundary, and back-testing requirements.
- Recommendations distinguish facts, assumptions, uncertainty, and expected impact.
- Executive outputs are reviewable and traceable.
- Domain SMEs approve calculation behavior for released simulations.

### Phase 3 — Optional expansion; separate approval required

Do not begin this phase automatically.

Possible capabilities:

1. Document RAG with ingestion, ACLs, versioning, retrieval evaluation, and page citations.
2. Durable/resumable workflows and LangGraph if tasks must survive restarts or wait for approvals.
3. A job queue and Redis if multiple workers or long-running jobs require shared state.
4. A low-risk approved action workflow.
5. Safe analytical SQL only if typed tools/templates leave a measured coverage gap.

Recommended first action workflow:

- Draft or acknowledge/assign a notification with explicit authorization, preview, approval, idempotency, audit, and read-back verification.

Do not begin with direct P6 schedule mutation.

---

## 15. Testing and Evaluation Strategy

Testing is a continuous workstream and a release gate for every phase. It is not a final cleanup task.

### 15.1 Current testing baseline

The current repository contains manual scripts that call endpoints or print database/model results, but it does not contain a sufficient automated chatbot test suite with assertions and release gates.

Before major implementation:

- Add a standard Python test runner and isolated test configuration.
- Add frontend unit/contract testing for the shared SSE client.
- Use a disposable test database or transaction rollback fixtures.
- Mock external model, P6, SharePoint, and transmission calls in deterministic CI tests.
- Keep a separate opt-in suite for live model/provider evaluations.

### 15.2 Golden evaluation dataset

Create an initial set of 50–100 real Akasha questions, reviewed by product/domain owners.

Each case must include:

```json
{
  "id": "AK-FACT-001",
  "question": "...",
  "user_role": "...",
  "allowed_projects": [],
  "expected_intent": "...",
  "expected_project_ids": [],
  "required_tools": [],
  "forbidden_tools": [],
  "expected_facts": [],
  "expected_evidence": [],
  "expected_freshness_behavior": "...",
  "expected_safety_behavior": "...",
  "severity": "critical | high | medium | low"
}
```

Required categories:

- Exact factual questions.
- Project status summaries.
- Ambiguous and misspelled project names.
- Portfolio versus project questions.
- P6 schedule and critical-path questions.
- Material, inventory, PO, transit, consumption, and vendor questions.
- Transmission readiness and delay questions.
- Cross-domain root-cause questions.
- Missing data.
- Stale data.
- Conflicting source values.
- Unsupported DPR/finance/document questions.
- Tool failures and timeouts.
- Prompt injection and instruction override attempts.
- Unauthorized project/data requests.
- Feedback poisoning attempts.
- Multi-turn follow-ups.
- Simulations and invalid scenario inputs.
- Action requests that must not execute.

### 15.3 Test layers

#### A. Unit tests

Test deterministic code without an LLM:

- Project normalization/resolution and candidate ranking.
- P6/SAP/transmission query filters.
- Calculation formulas and units.
- Freshness comparison and cache invalidation.
- Evidence creation.
- Tool input validation and result envelopes.
- Recommendation formatting rules.
- Simulation math and input boundaries.
- Feedback review policy.
- Authorization/scope decisions.

#### B. Tool contract tests

For every tool:

- Valid input.
- Missing/invalid input.
- Unknown project.
- Unauthorized project.
- No data.
- Partial/stale data.
- Row/result limits.
- Timeout and provider/database error.
- Evidence and freshness completeness.
- Stable output schema.

#### C. Integration tests

- Project mapping across P6, SAP/Module Tracker, and transmission.
- Chat router to orchestrator to tool to verifier to persistence.
- Database migrations from a clean schema.
- Cache invalidation after each source update.
- Conversation ownership and history retrieval.
- Feedback storage/review.
- Provider gateway behavior with mocked providers.

#### D. API and SSE tests

- Request validation.
- Authentication and authorization.
- SSE event ordering.
- Events split across network chunks.
- Multiple events in one network chunk.
- Unicode and large messages.
- Client cancellation/disconnect.
- Provider/tool failure after partial output.
- Exactly one terminal event.
- Persistence on success, partial failure, and abort according to policy.
- Compatibility of every active frontend chatbot surface.

#### E. AI behavior evaluations

Run with the configured model using fixed test data:

- Intent and entity accuracy.
- Required/forbidden tool selection.
- Project-resolution behavior.
- Factual exactness.
- Grounded claim rate.
- Correct abstention.
- Separation of fact/assumption/recommendation.
- Root-cause task completion.
- Stability across repeated runs.
- Prompt/model regression.

Do not evaluate correctness using string equality alone. Extract structured claims and compare them with deterministic expected facts.

#### F. Security and adversarial tests

- Invalid/expired/forged tokens.
- Role escalation.
- Cross-project access and indirect data leakage.
- Prompt injection in user text.
- Prompt injection in tool results and future documents.
- Requests to reveal prompts, credentials, endpoints, or internal errors.
- Oversized input and image payloads.
- Rate-limit and budget enforcement.
- Sensitive data redaction in prompts, logs, traces, and responses.
- Attempts to force writes through chat or tool names.

#### G. Simulation validation

- Fixed-seed reproducibility.
- Boundary and invalid inputs.
- Unit consistency.
- No-data and insufficient-history behavior.
- Comparison against hand-calculated cases.
- Historical back-testing.
- SME review and sign-off.
- Clear uncertainty/assumption display.

#### H. Performance and resilience tests

- Time to first answer token.
- Total completion latency.
- Prompt/context size.
- Concurrent requests.
- Database connection pressure.
- Tool timeout.
- Model timeout/rate limit.
- Retry only for safe operations.
- Provider outage behavior.
- Maximum step/token/runtime budget enforcement.
- Cost per successful evaluated task where provider usage is available.

#### I. Future HITL/action tests

Required before any write-capable release:

- Identity and scope enforcement.
- Preview accuracy.
- Explicit approval requirement.
- Approval bound to exact action, project, parameters, and user.
- Single-use/idempotency behavior.
- Duplicate request prevention.
- Expired/revoked approval.
- Failed execution and safe retry.
- Post-action read-back verification.
- Complete audit trail.
- Action kill-switch behavior.

### 15.4 Metrics

Track metrics by use case, release, model, prompt version, and tool version:

| Metric | Meaning |
|---|---|
| Project-resolution accuracy | Correct canonical project or correct clarification |
| Intent/domain accuracy | Correct classification and required domains |
| Factual exactness | Exact dates, counts, quantities, SPI/CPI, statuses, and units |
| Grounded claim rate | Material claims supported by evidence |
| Evidence completeness | Required source, record/aggregation, and freshness metadata present |
| Tool selection precision/recall | Required tools used and irrelevant tools avoided |
| Abstention/clarification correctness | System declines or asks instead of guessing |
| Task success | User goal completed, not merely answered fluently |
| Authorization safety | Unauthorized data/actions blocked |
| Stale-data disclosure | Correctly reports missing or stale sources |
| Simulation validity | Reproducible and within validated model behavior |
| First-token/completion latency | User experience |
| Cost per successful task | Runtime efficiency |
| Regression rate | Quality change between releases |

### 15.5 Initial hard release gates

- **100%** of unauthorized/cross-project test cases must be blocked without data leakage.
- **100%** of consequential action attempts must remain non-executing until the future approval framework exists.
- **100%** of critical material claims in released workflows must carry evidence and freshness metadata.
- Ambiguous project cases must clarify rather than silently select an incorrect project.
- Numeric answers in critical golden cases must exactly match deterministic expected results within explicitly defined rounding rules.
- Every released simulation must have automated deterministic tests and documented SME approval.
- Every model, prompt, tool, retrieval, or calculation change must run the regression suite before release.
- Critical safety/security failures block release; they cannot be averaged away by a high overall score.

Accuracy and latency targets beyond these hard gates must be agreed after Phase 0 baseline measurements. Record them in the evaluation configuration, not only in meeting notes.

### 15.6 CI and release execution

Recommended separation:

```text
Per commit:
  lint/type checks
  deterministic unit tests
  tool contract tests
  mocked API/SSE tests
  security scope tests

Per pull request/release candidate:
  integration tests
  golden dataset with mocked/fixed model outputs
  live-model regression suite where credentials are available
  performance smoke tests

Before production release:
  domain SME review
  security review
  adversarial/red-team sampling
  rollback verification
  release report containing evaluation deltas
```

Every production failure should become a permanent regression case after sensitive data is removed.

---

## 16. Rollout and Operational Strategy

### 16.1 Environments

- Development: mocked tools/providers available; synthetic or approved test data.
- Test/staging: representative sanitized database; production-like auth and networking.
- Production: approved model provider, explicit project scopes, monitoring, and rollback controls.

### 16.2 Feature flags

Use simple configuration flags for risky or incomplete capabilities:

- Analysis mode enabled.
- Image input enabled.
- Each simulation enabled.
- Each optional domain enabled.
- Executive scheduled generation enabled.
- Future document RAG enabled.
- Future action execution enabled.

Disabled capabilities must return a clear unsupported/disabled response and must not silently fall back to fabricated behavior.

### 16.3 Progressive rollout

1. Internal engineering/domain users.
2. Selected projects and roles.
3. Read-only broader rollout after evaluation review.
4. Optional capabilities only after independent acceptance gates.

### 16.4 Rollback

- Preserve fast grounded mode as a safe fallback if analysis mode is disabled.
- Model/provider changes must be independently reversible.
- Prompt/tool/calculation versions must be traceable.
- No database migration should depend on runtime `create_all` behavior alone; use reviewed migrations.

---

## 17. Patterns Adopted from the eSewa Reference

The eSewa reference archive describes a different, more complex wallet assistant. Akasha should adopt its discipline, not copy its topology.

### Adopt in simplified form

- One deterministic policy boundary around tools/actions.
- Clear separation of routing, policy, execution, and output contracts.
- Identity-scoped conversation state.
- Live retrieval for volatile values.
- Typed tool schemas and session-owned identity injection.
- Deterministic tests separated from live-model evaluations.
- Severity-based release gates.
- Evidence, trace, and audit metadata.
- Future action risk classes and kill-switch design if writes are introduced.

### Do not adopt initially

- Eight-agent routing architecture.
- Dynamic agent builder/registry.
- Multiple overlapping runtime generations.
- Keyword, semantic embedding, and LLM routers simultaneously.
- MCP/skill marketplace infrastructure.
- Long-term consumer user memory.
- Milvus/vector RAG without a document use case.
- Multi-database platform topology for chatbot state.
- Payment-grade action gate complexity before Akasha exposes any actions.

---

## 18. Implementation Rules for Codex and Developers

These rules are included to prevent implementation drift.

1. Read this document and the current relevant code before modifying files.
2. Inspect Git status and preserve all unrelated user changes.
3. Implement one phase or one bounded work item at a time.
4. Add or update tests with every behavior change.
5. Do not add new infrastructure or frameworks unless the current phase explicitly requires them.
6. Do not create new specialist agents to mirror business-domain names.
7. Do not replace deterministic calculations with LLM reasoning.
8. Do not enable writes from the chatbot.
9. Do not claim DPR, finance, simulation, RAG, confidence, or evidence capability beyond what tests verify.
10. Keep HTTP routers thin; do not place provider, orchestration, persistence, and prompt logic in one file.
11. Keep tool and answer contracts typed and versioned.
12. Enforce authorization at the API and tool/service levels.
13. Prefer the smallest refactor that establishes a clear boundary.
14. Run the relevant deterministic tests before using live providers.
15. Report changed files, migrations, configuration, tests run, results, known limitations, and rollback steps after each work item.

### Codex must stop and request approval before

- Adding LangGraph or another agent framework.
- Adding Redis, a vector database, or a job queue for chatbot runtime.
- Adding document RAG.
- Adding generated SQL.
- Adding a new external model/provider that changes data residency.
- Enabling long-term semantic memory.
- Enabling any write-capable tool.
- Performing a broad rewrite of the existing chatbot.
- Changing the locked architecture decisions in Section 4.

---

## 19. Definition of Done

The initial Akasha AI/Agentic AI implementation is complete when:

- One canonical chatbot UI uses one reliable SSE contract.
- Every request uses validated identity and project scope.
- Simple questions use the fast grounded path.
- Complex priority questions use one bounded read-only agentic path.
- Project resolution is deterministic or asks clarification.
- Only relevant domain evidence is retrieved.
- Important facts are deterministically verified.
- Every material claim exposes evidence and per-source freshness.
- Unsupported or missing data produces honest abstention.
- Simulations are not presented as valid until tested and approved.
- Recommendations are evidence-backed and non-executing.
- Automated unit, tool, integration, API/SSE, security, and AI evaluation suites exist.
- The two priority workflows meet the agreed release thresholds.
- Observability can reconstruct the model, prompt, tools, evidence, calculations, and outcome for a run.
- No unnecessary multi-agent, RAG, generated SQL, durable workflow, or write infrastructure has been introduced.

---

## 20. Final Positioning

Use the following statement consistently with engineering, product, and the client:

> **Akasha Governed Agentic Analytics Copilot** is a single AI copilot that answers routine questions through trusted project-data retrieval and performs bounded multi-step analysis for complex cross-platform questions using approved P6, SAP/material, transmission, notification, and validated simulation tools. AI explains and recommends, deterministic services calculate and verify, and humans remain responsible for consequential decisions and actions.

This is the final recommended direction because it brings meaningful AI and Agentic AI into the existing Akasha chatbot while preserving simplicity, testability, security, and implementation control.

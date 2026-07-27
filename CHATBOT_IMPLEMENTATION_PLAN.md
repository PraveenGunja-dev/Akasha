# Akasha Chatbot Implementation Plan

## 1. Purpose

This plan defines a production-quality upgrade of the Akasha chatbot focused on:

- Accurate, evidence-grounded answers from P6, SAP, Transmission Control (TC), and Pulse.
- Private, resumable conversations for CEO and PMAG users.
- Durable session context using LangGraph and PostgreSQL.
- Project progress, portfolio executive, and weekly PMAG report generation.
- Downloadable PDF, DOCX, and XLSX artifacts.
- A measurable evaluation program based initially on `Qns_AKASHA.xlsx`.
- Consolidation of the current duplicate chatbot implementations.
- Security, reliability, provenance, and operational readiness.

This is a phased replacement of the active manual ReAct loop. It is not an activation of the existing v2.2 implementation, which contains incompatible and unvalidated calculations.

## 2. Confirmed Product Decisions

| Area | Decision |
|---|---|
| Initial users | CEO and PMAG |
| Conversation memory | Session/thread memory with private, resumable past chats |
| Cross-chat long-term memory | Not required in the first release |
| Retention | Retain chats until the user deletes them |
| Chat access | User only; administrators see audit metadata, not content by default |
| Identity | Microsoft Entra ID |
| Answer behavior | Strict evidence-first; qualify or abstain when evidence is missing, stale, or conflicting |
| Answer evidence | Show source systems and freshness |
| Documents/RAG | Not in the first phase |
| Agent architecture | Phased migration to LangGraph |
| Model strategy | Provider-agnostic |
| Report types | Project Progress, Portfolio Executive, Weekly PMAG |
| Report sources | P6, SAP, TC, and Pulse |
| Report formats | PDF, DOCX, and XLSX |
| Report workflow | Preview scope and assumptions before generation |
| Report period | Latest data by default, with a reporting cutoff/date range |
| Artifact retention | Temporary download for 24 hours |
| Artifact repository | No permanent repository in the first release |
| Report scheduling | Later phase |
| Background infrastructure | Do not introduce Redis or Celery |
| Initial language | English |
| Evaluation seed | `Qns_AKASHA.xlsx` plus expected answers derived from database evidence |
| Business validation | Database-derived expected answers remain pending until user validation |

## 3. Current-State Problems to Resolve

### 3.1 Accuracy

- All requests are forced into deep-analysis mode in `backend/routers/ai.py`.
- The active agent has no executable accuracy benchmark.
- The existing v2.2 accuracy claims are unsupported and its calculations conflict with the active KPI engine.
- Deep-analysis responses omit meaningful data freshness and domain provenance.
- Sources identify tool names, not the source records and timestamps supporting individual claims.
- There is no deterministic check that numbers and dates in an answer came from tool evidence.
- Feedback is stored but does not improve the active agent.
- Pulse quality, P6 risk-register, resource, and some material-requirement signals are not exposed consistently to the agent.
- Cache invalidation is not connected to successful source synchronization.

### 3.2 Memory and Context

- The browser sends the conversation history and the backend trusts it.
- The agent retains only the last six client-provided messages.
- Server-side chat records are not used to restore conversations.
- Sessions are not owned by authenticated users.
- Browser storage is shared across users and retains attached images.
- There is no token-aware trimming, summarization, or context budget.
- Failed, interrupted, and cancelled turns are not represented reliably.

### 3.3 Reports

- The current CEO PDF is a browser DOM capture and contains field, unit, and currency mismatches.
- The AI briefing has no working export.
- PMAG report generation and downloads are mock controls.
- XLSX generation exists only in manual scripts.
- DOCX generation does not exist.
- Report narratives are not tied to a reproducible dataset or evidence ledger.
- There is no report job, preview, artifact, or authenticated download model.

### 3.4 Platform

- Authentication is not enforced.
- TLS certificate verification is disabled globally.
- Multiple frontend chatbot components implement incompatible API behavior.
- SSE lacks typed start, progress, error, and done events.
- Final model answers are generated fully before being split into apparent stream chunks.
- Provider integration is duplicated and inconsistent.
- Runtime startup performs database schema changes.
- There is no meaningful automated test suite or CI quality gate.

## 4. Target Architecture

```text
React Chat and Reports UI
        |
        | Entra access token
        v
FastAPI API and authorization layer
        |
        +---------------------------+
        |                           |
        v                           v
Conversation Service          Report Service
        |                           |
        v                           v
LangGraph Agent              Canonical Report Dataset
        |                           |
        +-- intent/scope            +-- P6 section
        +-- tool execution          +-- SAP section
        +-- evidence registry       +-- TC section
        +-- answer synthesis        +-- Pulse section
        +-- claim verification      +-- risks/actions
        +-- summarization           |
        |                           v
        v                     Format Renderers
Postgres Checkpointer         PDF / DOCX / XLSX
        |
        v
Application Chat, Report, Evidence, Evaluation, and Job Tables
        |
        v
P6 / SAP / TC / Pulse synchronized data
```

### 4.1 Ownership Boundaries

LangGraph will own:

- Execution state for one conversation thread.
- Model, assistant, and tool messages needed to continue execution.
- Conversation summaries used for context compression.
- Agent node state, retries, pending actions, and checkpoint ancestry.
- Resume state for report-preview confirmation.

The Akasha application database will own:

- User identity and session ownership.
- The canonical user-visible transcript.
- Session titles, deletion state, and retention.
- Answer provenance, evidence, freshness, and quality status.
- Feedback and corrections.
- Report definitions, previews, jobs, and temporary artifacts.
- Evaluation cases and results.
- Audit records.

P6, SAP, TC, and Pulse remain the source of truth for operational facts. Live business metrics must not be copied into chatbot memory.

## 5. Memory and Context Design

### 5.1 Required Memory

The first release needs durable short-term or thread-scoped memory, not cross-thread long-term memory.

Each conversation will have:

- An application `chat_session` record owned by one Entra user.
- A cryptographically random server-generated session ID.
- The same ID supplied to LangGraph as `thread_id`.
- Canonical `chat_message` records for display and audit.
- LangGraph checkpoints for execution continuity.

When a user reopens a past chat:

1. The API verifies that the authenticated user owns the session.
2. The UI retrieves canonical messages from the application tables.
3. The next user message invokes LangGraph with the existing `thread_id`.
4. The Postgres checkpointer restores the execution context.
5. The client submits only the new message, never an authoritative history array.

### 5.2 Context State

The graph state should contain only serializable execution data:

```python
class AkashaState(TypedDict):
    messages: Annotated[list, add_messages]
    conversation_summary: str | None
    user_id: str
    tenant_id: str
    session_id: str
    user_role: str
    active_project_ids: list[str]
    intent: str | None
    requested_domains: list[str]
    evidence_ids: list[str]
    quality_status: str | None
    report_request: dict | None
    report_preview: dict | None
```

Database sessions, ORM objects, credentials, complete report files, and large raw query results must not be persisted in graph state.

### 5.3 Context Budget

Replace message-count truncation with a token-aware policy:

- Preserve system instructions and the current request.
- Preserve recent user and assistant turns.
- Preserve complete assistant-tool-call and tool-result groups.
- Remove old, large tool payloads before conversational turns.
- Trigger summarization at a configurable percentage of the selected model's context window.
- Retain the canonical transcript even when graph context is summarized.
- Mark summaries as derived context, never as evidence.

Initial policy:

- Start summarization near 60 percent of the supported context window.
- Retain at least the most recent four complete conversational turns.
- Retain stable project selections and unresolved user instructions as structured state.
- Limit each tool result before it enters model context.
- Recalculate the budget for each provider/model combination.

### 5.4 Long-Term Memory

Do not add a LangGraph long-term store in the first release.

Potential later use is limited to explicit user preferences such as:

- Preferred report type.
- Preferred units and currency display.
- Preferred answer detail level.
- Frequently selected projects.

If introduced later, preferences must be user-visible, editable, deletable, and namespaced by authenticated tenant and user. They must not include volatile project metrics or unreviewed corrections.

### 5.5 LangGraph Persistence

Use:

- `langchain`
- `langgraph`
- `langgraph-checkpoint-postgres`
- Psycopg 3 for LangGraph persistence

The existing SQLAlchemy application can continue using its current driver during migration. Checkpointer resources must be initialized once through FastAPI lifespan or a deployment setup step, not during each request.

Checkpoint retention must follow the session deletion policy. Deleting a chat must remove or tombstone:

- Application messages.
- Feedback associated with those messages.
- LangGraph checkpoints for the thread.
- Temporary report previews associated only with that thread.

## 6. Agent and Answer-Quality Design

### 6.1 Graph Structure

Use a parent `StateGraph` with an agent subgraph rather than one unrestricted loop:

```text
authenticate and load thread
        |
normalize request and resolve scope
        |
classify route
        |
        +-- conversational response
        +-- evidence-backed analysis agent
        +-- report request parser and preview
        |
collect deterministic tool evidence
        |
synthesize structured answer
        |
verify claims and freshness
        |
        +-- pass -> stream final answer
        +-- repair once -> verify again
        +-- fail -> qualified response or abstention
        |
persist transcript, evidence, and quality result
```

Use `langchain.agents.create_agent` for the tool-calling subgraph where suitable. Keep deterministic routing, report preview, evidence validation, and persistence as explicit graph nodes.

### 6.2 Typed Tool Contract

Every operational tool must return a common envelope:

```json
{
  "status": "ok",
  "data": {},
  "evidence": [
    {
      "evidence_id": "...",
      "source_system": "P6",
      "source_entity": "p6_activity",
      "record_ids": ["..."],
      "project_id": "...",
      "data_as_of": "...",
      "last_synced_at": "..."
    }
  ],
  "warnings": [],
  "limitations": []
}
```

Required behavior:

- Validate all model-supplied arguments independently.
- Resolve and authorize project scope before executing a tool.
- Clamp row counts, date ranges, and ranking limits.
- Calculate business metrics deterministically in Python or SQL.
- Return stable units and explicit null semantics.
- Distinguish no matching row from a verified zero value.
- Include source freshness and known data-quality warnings.
- Never expose credentials or internal exception details.

### 6.3 Evidence-First Answer Contract

The synthesis model should produce structured output before rendering Markdown:

```json
{
  "answer_markdown": "...",
  "claims": [
    {
      "text": "Project X is 12 days late",
      "type": "numeric",
      "value": 12,
      "unit": "days",
      "evidence_ids": ["ev_123"]
    }
  ],
  "freshness_summary": {},
  "limitations": [],
  "follow_up_suggestions": []
}
```

The verification node must:

- Confirm every numeric and date claim against referenced evidence.
- Confirm that project names map to authorized canonical projects.
- Reject evidence IDs not produced during the current run.
- Check units, signs, and rounding tolerances.
- Detect source conflicts and require them to be disclosed.
- Verify that freshness is present for data-backed claims.
- Allow one repair attempt.
- Remove or qualify unsupported claims after a failed repair.

Do not ask the model to invent a percentage confidence score. Present a deterministic quality status instead:

- `verified`: all material claims are supported and sufficiently fresh.
- `verified_with_warnings`: claims are supported but data is stale, incomplete, or conflicting.
- `insufficient_evidence`: the requested conclusion cannot be supported.

### 6.4 Freshness Policy

Create source-specific, configurable thresholds rather than one global timeout.

The initial policy must define:

- Expected update frequency for P6, SAP, TC, and Pulse.
- Warning and stale thresholds.
- Which report sections may be generated with stale data.
- Which questions require abstention when stale.
- How conflicting synchronization timestamps are presented.

Each answer and report must show:

- Data sources used.
- Data current-through timestamp per source.
- Missing requested sources.
- Stale or conflicting data warnings.

### 6.5 Model Provider Abstraction

Create one provider interface used by:

- Agent tool selection.
- Final answer synthesis.
- Summarization.
- Report narrative generation.
- Evaluation judges where deterministic scoring is not possible.

The provider interface must normalize:

- Structured output.
- Tool calling.
- Streaming.
- Timeouts and retries.
- Token usage and model identity.
- Provider error categories.
- Vision capability.

Azure OpenAI, OpenRouter, and Ollama can be adapters. Unsupported provider/model capabilities must fail at startup or route to an explicitly configured fallback, never silently fall through.

### 6.6 Feedback

Keep feedback application-owned.

Add:

- Thumbs up/down.
- Optional correction text.
- Issue category: wrong number, wrong project, stale data, incomplete, unsupported claim, poor recommendation, or formatting.
- Link to answer, run, evidence, provider/model, and prompt version.

Feedback must not automatically rewrite prompts or become global memory. Reviewed corrections can be promoted into evaluation cases or curated few-shot examples.

## 7. Evaluation and Accuracy Program

### 7.1 Evaluation Dataset

Use `Qns_AKASHA.xlsx` as the initial question backlog, not as an immediately trusted golden dataset.

Current constraint:

- 132 questions exist.
- Only 5 currently have populated answers.
- Several questions depend on missing or `TBD` data sources.

Create an import process that produces versioned evaluation cases with:

- Question and category.
- User role.
- Required project scope.
- Expected tools and domains.
- Expected structured facts.
- Numeric tolerances and units.
- Required freshness and evidence.
- Permitted limitations or abstention.
- Source snapshot/hash.
- Validation status.

Validation statuses:

- `generated_from_database`
- `pending_business_validation`
- `business_validated`
- `rejected`
- `blocked_missing_source`

### 7.2 Generating Initial Expected Answers

For each feasible workbook question:

1. Resolve its source domain and project scope.
2. Query the current database through deterministic service functions.
3. Store expected facts, not only free-form prose.
4. Record source tables, record identifiers, timestamps, query/tool version, and database snapshot hash.
5. Generate a readable expected answer from those facts.
6. Mark the result `pending_business_validation`.
7. Present the evidence and answer for later user validation.

Questions that cannot be answered from the current database must be marked `blocked_missing_source`; the chatbot should not be trained or tested to fabricate those answers.

Database-derived expected answers may be used as provisional regression checks, but only `business_validated` cases may be used to claim business accuracy.

### 7.3 Metrics

Release-blocking metrics:

- Project-resolution correctness.
- Numeric and date exactness within defined tolerances.
- Unsupported numeric claim rate.
- Evidence coverage for numeric/date claims.
- Unit and schedule-variance sign correctness.
- Correct abstention when required data is missing.

Tracked secondary metrics:

- Tool-selection correctness.
- Answer completeness.
- Freshness disclosure.
- Source conflict disclosure.
- Recommendation usefulness.
- Time to first response event.
- End-to-end latency.
- Model and tool cost where available.
- User feedback rate.

Initial quality gates for the curated suite:

- 100 percent project-resolution correctness.
- 100 percent evidence coverage for material numeric/date claims.
- 0 unsupported material numeric claims.
- 100 percent correct units and variance signs.
- 100 percent correct abstention on explicitly missing-source cases.

These are engineering gates for the curated cases, not a claim that all possible chatbot answers are 100 percent accurate.

### 7.4 Evaluation Execution

Run evaluations:

- Locally during agent and tool development.
- In CI against deterministic fixtures.
- Against a frozen, sanitized database snapshot before release.
- Before changing prompts, tools, KPI formulas, providers, or models.
- Periodically against sampled production interactions after privacy review.

Store:

- Evaluation dataset version.
- Prompt and tool versions.
- Provider and model.
- Source fixture version.
- Per-case result and evidence.
- Aggregate metrics and regression comparison.

## 8. Report Generation Design

### 8.1 Supported Reports

#### Project Progress Report

Default sections:

- Project identity and reporting period.
- Executive summary.
- P6 progress and schedule performance.
- Critical and delayed activities.
- SAP procurement, material gaps, inventory, and vendor issues.
- TC line and network dependencies.
- Pulse quality non-conformances and RFIs.
- Cross-domain risks and data conflicts.
- Required decisions, owners, and recommended actions.
- Source freshness and methodology.

#### Portfolio Executive Report

Default sections:

- Portfolio summary and capacity context.
- Project health and risk ranking.
- Schedule and progress exceptions.
- Procurement and material exposure.
- Transmission dependencies.
- Quality hotspots.
- Cross-project trends and concentration risks.
- Executive decisions and actions.
- Source freshness and methodology.

#### Weekly PMAG Report

Default sections:

- Weekly status summary.
- Progress versus plan.
- New and carried-forward slippages.
- Two-to-six-week look-ahead, subject to available schedule data.
- Critical activities and constraints.
- Materials and procurement blockers.
- TC and quality blockers.
- Action register with owner and target date where supported.
- Exceptions requiring escalation.
- Source freshness and methodology.

### 8.2 Report Conversation Flow

Example:

1. User: "Generate the weekly PMAG report for Project X for the week ending 31 July."
2. Agent resolves the project and report intent.
3. Agent validates authorization and source availability.
4. Agent presents a preview containing:
   - report type
   - project/portfolio scope
   - reporting cutoff/date range
   - included sections and sources
   - source freshness
   - missing or stale data
   - output formats
5. User confirms or modifies the preview.
6. The application creates one report job and returns progress events.
7. The backend builds one canonical report dataset.
8. Narrative sections are generated and verified against the dataset.
9. PDF, DOCX, and XLSX renderers create artifacts.
10. The UI displays authenticated download links valid for 24 hours.

Preview confirmation can use a LangGraph interrupt or an explicit application confirmation endpoint. The application must persist the preview so it survives a page refresh.

### 8.3 Canonical Report Dataset

All formats must be rendered from the same typed dataset:

```text
ReportDataset
  metadata
    report_id
    report_type
    requested_by
    project_ids
    period_start
    period_end
    generated_at
    source_freshness
    prompt_version
    dataset_hash
  executive_summary
  project_kpis
  schedule
  procurement
  transmission
  quality
  risks
  actions
  evidence
  warnings
  methodology
```

Rules:

- Deterministic services compute all numbers, dates, rankings, and status fields.
- The LLM may summarize and explain but must not create new metrics.
- Every report claim references canonical evidence.
- All formats display the same metric values and units.
- Missing data remains missing; it must not default to zero or a healthy value.
- Currency and unit metadata are explicit.
- Schedule variance has one documented sign convention.

The reporting cutoff limits included activity, quality, and transaction events where historical fields permit it. The first release does not promise full historical reconstruction of tables that currently overwrite prior state. The preview must disclose this limitation.

### 8.4 Format Renderers

Use backend renderers:

- PDF: ReportLab for a predictable server-side implementation without Office automation.
- DOCX: `python-docx`, optionally `docxtpl` after the initial templates stabilize.
- XLSX: `openpyxl`, reusing verified logic from the current export scripts.
- Shared charts: generate server-side static images from canonical values for PDF and DOCX; use native XLSX charts where appropriate.

Do not:

- Capture the browser DOM as the canonical PDF.
- Use `pywin32` or Office COM as the primary production renderer.
- Ask the model to generate binary documents directly.
- Implement separate business calculations in each renderer.

### 8.5 Branding

No approved templates currently exist. Create an Akasha report design system covering:

- Cover page.
- Header/footer.
- Typography and colors.
- Project and period identity.
- KPI cards and status colors.
- Tables and charts.
- Warning and missing-data treatments.
- Source/freshness appendix.
- Confidentiality label.

Review the first sample of each report type before treating the templates as stable.

### 8.6 Jobs Without Redis or Celery

Do not use FastAPI `BackgroundTasks` for durable report generation.

Use a PostgreSQL-backed job table and a separate worker command in the same backend codebase:

- Worker polls pending jobs using `FOR UPDATE SKIP LOCKED`.
- Job rows include status, progress, attempts, heartbeat, cancellation, and error code.
- The worker owns one job at a time per report ID.
- Stale running jobs can be recovered after a heartbeat timeout.
- Generation steps are idempotent.
- API instances do not perform report work after returning the request.

This adds a worker process but no Redis, Celery, or additional persistence service.

For a strictly single-process development deployment, the same worker loop can run as a separate command on the same machine. Production must supervise the API and worker processes independently.

### 8.7 Temporary Artifact Storage

First-release behavior:

- Store generated files in a configured temporary artifact directory.
- Store metadata, checksum, MIME type, size, and expiry in PostgreSQL.
- Authorize every download against the requesting user.
- Use opaque artifact IDs, never user-provided filesystem paths.
- Set `Content-Disposition` and correct content type.
- Delete files and expire download records after 24 hours.
- Run cleanup through the worker process and at worker startup.

If the application later runs on multiple machines, the temporary directory must become a shared volume or object storage. Local files are acceptable only while API download routing and worker placement guarantee access to the same filesystem.

## 9. API and Data Model Changes

### 9.1 Conversation APIs

```text
POST   /api/chat/sessions
GET    /api/chat/sessions
GET    /api/chat/sessions/{session_id}
PATCH  /api/chat/sessions/{session_id}
DELETE /api/chat/sessions/{session_id}
POST   /api/chat/sessions/{session_id}/messages
POST   /api/chat/messages/{message_id}/feedback
```

The message endpoint returns a typed SSE stream with:

- `start`
- `status`
- `token`
- `visualization`
- `sources`
- `report_preview`
- `report_job`
- `error`
- `done`

Every event includes a stream version, request ID, session ID, and sequence number.

### 9.2 Report APIs

```text
POST   /api/reports/previews
PATCH  /api/reports/previews/{preview_id}
POST   /api/reports/previews/{preview_id}/confirm
GET    /api/reports/jobs/{job_id}
POST   /api/reports/jobs/{job_id}/cancel
GET    /api/reports/jobs/{job_id}/artifacts
GET    /api/reports/artifacts/{artifact_id}/download
```

### 9.3 Models

Extend or add:

- `ChatSession`: user ID, tenant ID, role, title, status, latest message time, deletion time.
- `ChatMessage`: request ID, run ID, status, model, prompt version, quality status.
- `ChatEvidence`: source, entity, record references, freshness, tool name/version, evidence payload hash.
- `ChatClaim`: answer claim, type, normalized value/unit, verification status, evidence links.
- `ChatFeedback`: user ID, issue category, correction, review status.
- `ReportPreview`: normalized request, scope, sections, source state, expiry, confirmation status.
- `ReportJob`: status, progress, attempts, heartbeat, cancellation, dataset hash, error code.
- `ReportArtifact`: format, path, MIME type, checksum, size, expiry.
- `EvaluationCase`: source workbook reference, expected facts, validation status, fixture/snapshot.
- `EvaluationRun`: model, prompt/tool versions, source fixture, aggregate results.
- `EvaluationResult`: per-case scores, output, evidence, and failure reasons.

Use reviewed Alembic migrations. Remove application-import schema mutation before these models are deployed.

## 10. Frontend Plan

### 10.1 Consolidate Chat

- Keep `AICopilot` as the full chat experience.
- Convert `ScenarioSimulationPanel` into a compact view over the same chat store.
- Remove or archive `FloatingCopilot`, `AkashaChat`, and `RightCopilot` after confirming no consumer remains.
- Use one typed chat transport and SSE parser.
- Use one message renderer for Markdown, charts, sources, warnings, and feedback.
- Remove raw HTML support or add strict sanitization.

### 10.2 Session Experience

- List authenticated user's sessions from the backend.
- Open and resume any session.
- Rename and delete a session.
- Search titles initially; add message-content search only if required.
- Show last updated time and report artifacts still available.
- Clear local browser chat storage after migration.
- Do not expose another user's sessions through predictable identifiers.

### 10.3 Evidence Experience

Each answer should display:

- Verified/verified-with-warnings/insufficient-evidence status.
- Source systems used.
- Data current-through timestamps.
- Missing/stale/conflicting source warnings.
- Expandable evidence details for important metrics.

### 10.4 Report Experience

- Detect report intent in chat.
- Render an editable preview card for scope, date range, sections, and formats.
- Require confirmation before generation.
- Display queued/running/rendering/completed/failed progress.
- Provide PDF, DOCX, and XLSX download actions.
- Display the 24-hour expiration time.
- Allow retry for a failed format without recomputing a valid canonical dataset.

## 11. Security and Privacy Prerequisites

These are release prerequisites, not optional follow-up work:

- Integrate Microsoft Entra ID access-token validation.
- Require authentication on every API route.
- Authorize projects, sessions, evidence, reports, and artifacts by user and role.
- Add CEO/PMAG role mapping and project-scope policy.
- Remove hardcoded frontend credentials and rotate exposed secrets.
- Restore TLS certificate verification and configure the corporate CA correctly.
- Restrict CORS to approved origins.
- Disable public user seeding, credential update, sync, and mutation routes until authorized.
- Add request, image, history, output, rate, and concurrency limits.
- Reject arbitrary history roles and client-selected ownership fields.
- Sanitize rendered model output.
- Encrypt transport and protect sensitive checkpoint/application data at rest according to organization policy.
- Log security-relevant actions without logging secrets or unnecessary conversation content.

## 12. Observability

Add correlation across:

- HTTP request ID.
- User and tenant ID.
- Chat session and message ID.
- LangGraph run and checkpoint ID.
- Tool call and evidence IDs.
- Report preview, job, dataset, and artifact IDs.
- Evaluation run ID.

Metrics:

- Time to first event and final answer.
- Agent iterations and tool calls.
- Tool errors and empty results.
- Provider latency, errors, tokens, and cost where available.
- Claim verification and repair rates.
- Stale-data and abstention rates.
- Active streams and disconnects.
- Report queue time and render duration by format.
- Evaluation regression counts.

Use structured logs and distributed traces where the deployment platform permits. Detailed errors remain server-side; clients receive stable codes and request IDs.

## 13. Testing Strategy

### 13.1 Unit Tests

- Project resolution and authorization.
- KPI, variance, date, unit, and rounding calculations.
- Source freshness rules.
- Tool argument validation and limits.
- Evidence-envelope generation.
- Claim verification.
- Context trimming and summarization boundaries.
- Report dataset builders.
- PDF, DOCX, and XLSX renderers.
- Artifact expiration and safe paths.

### 13.2 Integration Tests

- Entra-authenticated session ownership.
- Start, list, reopen, continue, rename, and delete conversations.
- LangGraph checkpoint persistence and resume.
- Provider adapters with mocked responses.
- Typed SSE success, error, cancellation, and disconnect.
- P6/SAP/TC/Pulse tool queries against fixtures.
- Report preview, confirmation, job execution, downloads, and cleanup.
- Database worker job locking and crash recovery.

### 13.3 Contract Tests

- Pydantic and TypeScript API/SSE schemas.
- Tool result envelope.
- Canonical report dataset.
- Source freshness and evidence display.
- All formats contain matching canonical metrics.

### 13.4 Security Tests

- Cross-user session and artifact access.
- Unauthorized project access.
- Prompt injection through user text and database fields.
- Fabricated client history and roles.
- Oversized messages and images.
- Malicious Markdown/HTML and links.
- Tool argument abuse.
- Path traversal and expired artifact downloads.

### 13.5 Evaluation Tests

- Provisional database-derived workbook cases.
- Business-validated workbook cases.
- Missing-source abstention cases.
- Stale and conflicting source cases.
- Adversarial project-name resolution.
- Numeric hallucination and unit/sign cases.
- Report narrative-to-dataset consistency.

## 14. Delivery Phases

### Phase 0: Baseline and Safety

Deliverables:

- Freeze and document the single active chatbot path.
- Remove unsupported accuracy claims from product-facing documentation.
- Add request IDs and baseline latency/tool telemetry.
- Fix source metadata mismatch and compact chat SSE incompatibility.
- Fix or disable inaccurate existing report exports.
- Correct simulation UI claims about external task execution.
- Add initial automated test scaffolding.

Exit criteria:

- Current behavior is measurable.
- Known misleading UI and report outputs are removed or corrected.
- A baseline evaluation run can execute, even with a small provisional dataset.

#### Phase 0 Progress Ledger

Overall status: `complete`

| Workstream | Status | Verification | Blockers |
|---|---|---|---|
| P0-A Active-path documentation | `complete` | Code-path review, accuracy/readiness/final contradiction claim searches, P0-G documentation remediation, and scoped `git diff --check` | None |
| P0-B Backend observability | `complete` | 25 full backend unittests, including 11 P0-B observability/privacy tests; scoped `py_compile`; scoped `git diff --check` | Mocked route execution unavailable because SQLAlchemy is not installed in the current interpreter |
| P0-C Chat SSE integration | `complete` | TypeScript and Vite build passed; shared helper lint and 3 focused request-ID tests passed; active-surface lint retains 30 pre-existing errors | None |
| P0-D Report correctness | `complete` | Targeted ESLint; TypeScript compile; Vite production build; report unit-label searches; scoped `git diff --check` | Planned CAPEX, explicit CPI availability, reliable procurement UOM, uncapped procurement detail, and verified PDF export are not available from current contracts |
| P0-E Simulation truthfulness | `complete` | 32 backend unittests including closed-vocabulary directive validation; scoped `py_compile`; frontend/backend claim and prose searches; frontend build/lint; `git diff --check` | None |
| P0-F Test/evaluation scaffold | `complete` | 24 isolated `unittest` tests passed; provisional baseline passed 11/11 rubric items; score-failure probe exited 1; empty/unknown-gate probes exited 2; scoped `py_compile` and `git diff --check` passed | No implementation blockers; validated benchmark data remains Phase 4 work |
| P0-G Independent review | `complete` | Final closed-vocabulary review; 32 backend and 3 frontend SSE tests passed; exact bypass and malformed-code probes rejected; production frontend build, scoped `py_compile`, ESLint, evaluator, and `git diff --check` passed | None |

##### P0-A: Active-Path Documentation

- Owner: P0-A subagent
- Status: `complete`
- Scope: Document the single active chatbot path and qualify unsupported accuracy claims.
- Changes: Added a code-as-built trace from `AICopilot` through path rewrite, forced deep analysis, tools, SSE, and database persistence; marked the standard pipeline, enhanced orchestrator, and v2.2 as inactive; labeled historical percentage claims as unvalidated estimates or targets.
- Files changed: `backend/ACTIVE_CHATBOT_PATH.md`; `backend/CHATBOT_V2_2_EXECUTIVE_SUMMARY.md`; `backend/CHATBOT_V2_2_DELIVERY.md`; `backend/CHATBOT_V2_2_INTEGRATION.md`; `backend/CHATBOT_V2_2_QUICK_REF.md`; `backend/README_V2_2.txt`; `backend/engine/ACCURACY_IMPROVEMENTS.md`; `backend/engine/ENHANCEMENT_SUMMARY.md`; `CHATBOT_IMPLEMENTATION_PLAN.md` (P0-A locations only).
- Verification: Confirmed `CEODashboard` mounts `AICopilot`; confirmed `/akasha/api/chat` rewrite and `ai.router` registration in `backend/main.py`; confirmed forced `is_deep_analysis=True`, `run_deep_analysis_agent_stream`, tool dispatch, SSE serialization, and `ChatSession`/`ChatMessage` commits in current code; searched Markdown again for 95/99 accuracy claims and confirmed remaining matches are labeled unvalidated; ran scoped `git diff --check`.
- Issues discovered: Text is emitted only after the model completes the final answer; persistence occurs only at final metadata handling; persisted history is not used to resume context; sources contain tool names rather than record evidence/freshness; active tools have no direct Pulse quality access.
- Blockers: None.
- Follow-up work: P0-C should address SSE behavior/contract; Phases 1-3 should add owned resumable sessions, explicit interrupted-turn persistence, direct Pulse evidence, freshness, and claim-level provenance; Phase 4 must establish an executable benchmark before any measured accuracy claim.
- P0-G remediation: Replaced contradictory production-ready, deployed, ready-to-integrate, rollout, and go-live wording with explicit inactive-prototype status; retained setup and migration procedures only as archival, conditional examples requiring renewed validation and approval.
- P0-G remediation files: `backend/CHATBOT_V2_2_DELIVERY.md`; `backend/CHATBOT_V2_2_EXECUTIVE_SUMMARY.md`; `backend/CHATBOT_V2_2_INTEGRATION.md`; `backend/CHATBOT_V2_2_QUICK_REF.md`; `backend/README_V2_2.txt`; `backend/engine/ENHANCEMENT_SUMMARY.md`; `backend/engine/CHATBOT_ENHANCEMENT_GUIDE.md`; `CHATBOT_IMPLEMENTATION_PLAN.md` (P0-A locations only).
- P0-G remediation verification: Searched the reviewed documentation for production-ready, deployment-complete, deployed, fully-operational, ready-to-deploy/integrate, immediate-deployment, and go-live wording; remaining matches are explicit negations or archival labels. Re-ran the 95/99 claim search and scoped `git diff --check`.
- P0-G final README remediation: Recast the historical “all code tested” statement as an unverified claim rather than current test evidence; made `deploy_v2_2.py` an approval-gated archival instruction for isolated evaluation only and explicitly not recommended for production activation.
- P0-G final README verification: Re-searched `backend/README_V2_2.txt` and related v2.2 documents for unqualified tested-code claims paired with direct deployment instructions; confirmed no contradictory pair remains and ran scoped `git diff --check`.

##### P0-B: Backend Observability

- Owner: P0-B subagent
- Status: `complete`
- Scope: Add request IDs and baseline chat latency/tool telemetry without replacing the active agent.
- Changes: Added a server-generated UUID operational request ID for every chat request and returned that same ID in the response header and all token, visualization, metadata, and sanitized error SSE events; added payload-safe JSON logs for chat start/completion/failure and per-tool duration/status; threaded correlation context through the existing orchestrator/agent; caught post-200 stream failures with rollback; made chat persistence atomic with flushes followed by one commit. P0-G remediation pseudonymizes every logged session ID with a bounded SHA-256 value and replaces vision-provider exception logging/return text with correlated operation/status telemetry and a fixed safe fallback. Final P0-G remediation removes `X-Request-ID` binding from the endpoint, ignores all caller-provided request IDs, and permits only canonical operational UUIDs to appear verbatim in logs.
- Files changed: `backend/routers/ai.py`; `backend/engine/orchestrator.py`; `backend/engine/agent.py`; `backend/engine/observability.py`; `backend/tests/test_observability.py`; `CHATBOT_IMPLEMENTATION_PLAN.md` (P0-B locations only).
- Verification: Ran `python -m py_compile backend/engine/observability.py backend/engine/agent.py backend/engine/orchestrator.py backend/routers/ai.py backend/tests/test_observability.py` without importing `backend/main.py`; `python -m unittest discover -s backend/tests -v` passed all 25 backend tests, including 11 observability tests proving conservative and secret-like incoming request IDs are replaced, the endpoint does not bind the incoming header, and the server UUID remains identical across logs and SSE; ran scoped `git diff --check` for tracked and untracked P0-B files.
- Issues discovered: The previous generator let post-HTTP-200 exceptions terminate without a typed SSE error, tool calls had no duration/status telemetry, and a newly created session was committed separately from its messages, preventing full rollback if message persistence failed. P0-G found that arbitrary caller session text and vision-provider exception text could reach observability paths; those paths are payload-safe. P0-G re-review then found that pattern-valid caller request IDs remained verbatim; the endpoint now ignores the header and always generates the operational UUID server-side.
- Blockers: A fuller mocked router-stream check could not run because SQLAlchemy is not installed in the available Python interpreter; no implementation blocker.
- Follow-up work: Run route-level SSE success/failure tests in the provisioned backend environment; P0-C should decide how clients visibly render the new sanitized `error` event while retaining existing token/visualization/metadata handling.

##### P0-C: Chat SSE Integration

- Owner: P0-C subagent
- Status: `complete`
- Scope: Fix source metadata and compact-chat SSE compatibility.
- Changes: Added a small typed SSE reader shared by the two active chat surfaces; it preserves frames split across network chunks, flushes the decoder and final unterminated frame, validates known events, and surfaces HTTP, malformed-frame, empty-stream, and typed backend errors. Updated AICopilot to accept active `metadata.sources: string[]` and legacy `{ tables: string[] }` metadata. Updated ScenarioSimulationPanel to stream POST responses without duplicating the current user message in history, send the local thread ID as `sessionId`, prevent overlapping sends, retain partial responses and explicit errors, store/render source metadata and suggestions, and deliberately defer visualization rendering to the full copilot.
- Files changed: `frontend/src/features/chatbot/chatStream.ts`; `frontend/src/features/chatbot/AICopilot.tsx`; `frontend/src/components/layout/ScenarioSimulationPanel.tsx`; `CHATBOT_IMPLEMENTATION_PLAN.md` (P0-C entries only).
- Verification: `npx tsc -b` passed. `npx vite build --emptyOutDir=false` passed with the existing large-chunk warning. `npx eslint src/features/chatbot/chatStream.ts` passed. Targeted lint across both active surfaces and the helper ran but remains red on 30 pre-existing violations in the two legacy components. `git diff --check` passed.
- Issues discovered: The standard `npm run build` completed TypeScript compilation but initially failed when Vite could not delete a concurrently locked `frontend/dist/adani.ttf` (`EPERM`); the non-emptying Vite build completed successfully. Both active components have existing ESLint debt involving unused imports, explicit `any`, synchronous state updates in effects, and React hook purity checks around `Date.now()`.
- Blockers: None for P0-C.
- Follow-up work: Keep compact-chat visualization rendering deferred to the full copilot until the planned Phase 1 frontend consolidation; address legacy component lint debt separately.
- P0-G remediation: Retained `request_id` on every parsed known and unknown SSE event, exposed `X-Request-ID` through the shared helper, persisted the correlation ID in assistant metadata on both active surfaces, and added concise `(Request ID: ...)` context to typed backend, HTTP, malformed-stream, empty-stream, and interrupted-stream errors when available. Error rendering uses sanitized event/HTTP messages only and does not expose stack traces.
- P0-G remediation files: `frontend/src/features/chatbot/chatStream.ts`; `frontend/src/features/chatbot/AICopilot.tsx`; `frontend/src/components/layout/ScenarioSimulationPanel.tsx`; `frontend/tests/chatStream.test.mjs`; `CHATBOT_IMPLEMENTATION_PLAN.md` (P0-C entries only).
- P0-G remediation verification: `node --experimental-strip-types --test tests/chatStream.test.mjs` passed 3/3 focused tests covering split and final frames, known and unknown event IDs, typed nested errors, response-header correlation, and HTTP errors. `npx tsc -b`, `npx eslint src/features/chatbot/chatStream.ts`, `npx vite build --emptyOutDir=false`, and `git diff --check` passed; Vite retained the existing large-chunk warning.
- Residual test gap: The frontend has no browser/component test harness, so support-ID rendering in AICopilot and ScenarioSimulationPanel is type/build verified but not covered by automated DOM interaction tests.

##### P0-D: Report Correctness

- Owner: P0-D subagent
- Status: `complete`
- Scope: Correct or disable inaccurate existing report output and export behavior.
- Changes: Traced CEO report props to `/api/summary`, `/api/financials`, `/api/financials/details`, and `/api/dashboard/summary`; mapped duration progress and CPI to the fields actually returned; removed invalid client-side SAP plant filtering; excluded defaultable CPI 1.00 values unless actual-cost computation is evidenced; rendered missing metrics as N/A with coverage warnings; formatted backend financial aggregates and PO values as INR crores; removed cross-material procurement quantity aggregation; replaced ambiguous raw schedule variance with forecast-finish minus baseline-finish calendar days; removed unsupported healthy/risk conclusions; and disabled runtime-CDN PDF capture and the unimplemented Share action.
- Files changed: `frontend/src/features/analytics/ReportsInsights.tsx`; `CHATBOT_IMPLEMENTATION_PLAN.md` (P0-D ledger and subsection only).
- Verification: `npx eslint src/features/analytics/ReportsInsights.tsx` passed. The TypeScript stage of `npm run build` passed; the normal Vite output step was blocked by an external `EPERM` lock on `frontend/dist/adani.ttf`, then `npx vite build --outDir %TEMP%/opencode-p0d-build` passed. Final repository `git diff --check` and the untracked plan-file whitespace check passed.
- Issues discovered: `/api/summary` exposes progress as `duration_percent_complete` and CPI as `cpi`/`cost_performance_index`, not the report's former camelCase fields. Its dynamic CPI calculation returns 1.00 when actual cost is unavailable. `/api/financials` returns one already-scoped aggregate in INR crores without `plant_code`; despite the response key `actualCapex`, the implementation computes aggregate PO net order value. `/api/financials/details` is already query-scoped and capped at 100 rows. Dashboard SAP objects also do not expose the plant key used by the former report join. Backend raw finish-variance sign/unit usage is inconsistent across code and documentation.
- Blockers: The current contracts do not provide planned CAPEX, an explicit CPI availability/provenance flag, a reliable procurement UOM, uncapped procurement detail, or a controlled PDF renderer. The Phase 0 UI reports these as unavailable or sample-limited and keeps export disabled.
- Follow-up work: Add explicit metric availability/source metadata, expose complete report-scoped procurement data and supported planned CAPEX, standardize raw schedule-variance semantics, and implement a verified export path in the later canonical reporting phase. If procurement quantities are restored, expose and group them by a reliable explicit UOM rather than aggregating across materials.
- P0-G remediation: Removed `order_quantity`/`po_quantities` from the report contract and eliminated vendor quantity sums and generic-unit labels. Vendor comparison now uses only loaded net order value in INR crores plus the vendor's count of records with an available order value. The report explicitly states that material quantities are not aggregated without a reliable common UOM and retains its capped-sample warning, N/A states, and disabled export/share controls.
- P0-G remediation verification: Targeted ESLint and `npx tsc -b` passed; `npx vite build --emptyOutDir=false` passed with the existing large-chunk warning; report searches found no quantity field access, MW label, generic quantity total, or cross-material unit comparison. Scoped report and untracked plan-file whitespace checks passed. Repository-wide `git diff --check` was also run and is red only on trailing whitespace in unrelated concurrently edited backend documentation.

##### P0-E: Simulation Truthfulness

- Owner: P0-E subagent
- Status: `complete`
- Scope: Remove misleading external-execution claims and disclose actual simulation behavior.
- Changes: Reframed detection as analysis of stored/available records; labeled generated strategies as modeled decision support with simplified schedule-network, weather, crew, and cost assumptions; replaced unsupported iteration-volume wording with neutral backend-managed wording; relabeled strategy execution as local action-directive generation and review; made external-system labels explicitly advisory; changed local checkmarks and completion from execution success to session-local review state; reset review state when directives are regenerated. Kept the detailed simulation unreachable, aligned its dormant iteration animation to the existing 1,000-iteration `/simulate` configuration, and kept the report UI disabled.
- Files changed: `frontend/src/features/analytics/SimulationLab.tsx`; `CHATBOT_IMPLEMENTATION_PLAN.md` (P0-E locations only).
- Verification: Searched `SimulationLab.tsx` for push, success, processed, 10,000, external-platform, iteration, completion, and report claims; no active push/success/processed/10,000 claims remain, external-platform names remain only in the explicit no-write disclosure, and report rendering remains guarded by `false`. `npm run build` passed. Targeted `npx eslint src/features/analytics/SimulationLab.tsx` ran and reported the file's existing lint debt (71 errors, 5 warnings, including `any`, hook/effect, unused disabled-path code, and the constant-false report guard); no new truthfulness lines were flagged. `git diff --check` passed with line-ending warnings only.
- Issues discovered: The active strategy endpoint performs 500 Monte Carlo iterations for the baseline and each option but does not return that count; the separate 1,000-iteration detailed simulation is unreachable from the UI. `/simulation-lab/execute` generates directives only, task review is local React state, and the report screen is disabled.
- Blockers: None.
- Follow-up work: If the detailed simulation is re-enabled later, render `iterations_run` from the API instead of animating a client-side count. Rename or revise the backend `/execute` contract and remove disabled simulation/report lint debt in a separately scoped change.
- P0-G remediation: Replaced the active `/simulation-lab/execute` model prompt that said tasks would be pushed with an advisory directive-planning contract. The prompt now states that the endpoint performs no external writes, defines system names only as suggested destination/owner labels, requires proposal-style `action` and `description` fields for human review, prohibits past/current/future automatic execution and push/sync/success claims in every generated field, and changes generated status from `Pending` to `For Review`. No frontend text normalization was added because the active UI already presents the verbatim fields inside an explicit local-review/no-external-write boundary, avoiding fragile replacement of useful advisory content.
- P0-G remediation files: `backend/routers/ai.py`; `CHATBOT_IMPLEMENTATION_PLAN.md` (P0-E ledger and subsection only). The existing P0-B request-ID, SSE, provider-routing, and telemetry changes in `backend/routers/ai.py` were preserved.
- P0-G remediation verification: `python -m py_compile backend/routers/ai.py` passed without importing `backend/main.py`. Backend searches found none of the former `will be pushed`, automated-directive, execution-task, external-system-list, or `Pending` contract wording and confirmed all new advisory/prohibition clauses. Active `SimulationLab.tsx` searches found none of the former pushing, pushed, processed, execution-success, or issue-resolved UI claims; model `action` and `description` remain verbatim but are enclosed by the existing suggested-destination and no-external-action disclosures. No frontend source changed in this remediation, so the previously passing frontend build was not rerun. Repository-wide and scoped `git diff --check` plus the untracked plan-file whitespace check passed with line-ending warnings only.
- P0-G deterministic remediation: Added the dependency-free `engine.simulation_directives` contract and routed parsed `/simulation-lab/execute` JSON through it before return. It accepts only a top-level `tasks` list of one to five exact directive objects, enforces non-empty bounded strings, canonicalizes an allowlist of advisory destinations, requires and emits only `For Review`, and rejects grammatical past/current/future/automatic execution, push, sync, completion, processing, write, update, send, create, apply, and success claims. Conditional/manual recommendations remain valid. Invalid or malformed model output now fails closed with HTTP 502 and the fixed message `AI directive output did not satisfy the advisory review contract.`; neither unsafe model text nor a partially validated list is returned.
- P0-G deterministic remediation files: `backend/engine/simulation_directives.py`; `backend/tests/test_simulation_directives.py`; `backend/routers/ai.py`; `CHATBOT_IMPLEMENTATION_PLAN.md` (P0-E ledger and subsection only). P0-B request-ID, SSE, provider-routing, and telemetry changes were retained.
- P0-G deterministic remediation verification: Six focused pure tests cover allowlisted valid directives, manual/conditional recommendations, ten adversarial execution claims, unsafe system/status/action fields, malformed shapes, list bounds, string bounds, canonicalization, and non-echoing errors. `python -m unittest discover -s backend/tests -v` passed all 31 tests. `python -m py_compile backend/engine/simulation_directives.py backend/tests/test_simulation_directives.py backend/routers/ai.py` passed without importing `backend/main.py`. Searches confirmed the execute route returns `normalize_simulation_directives(...)`, has no former raw/empty-task fallback, and uses the sanitized 502; former backend prompt and active frontend push/success claims remain absent. The frontend remains unchanged in this remediation and retains its local-review/no-external-write labels, so its previously passing build was not rerun. Repository-wide `git diff --check` and no-index whitespace checks for all new/untracked P0-E files passed with line-ending warnings only.
- P0-G closed-vocabulary remediation: Replaced the bypassable prose denylist with an exact code-only contract. The model may select only unique values from `P6_SCHEDULE_REVIEW`, `CREW_PLAN_REVIEW`, `PROCUREMENT_REVIEW`, `TC_RECOVERY_REVIEW`, and `PMAG_ACTION_REVIEW`; it cannot supply user-visible fields. The pure builder rejects unknown top-level keys, non-list/empty/excess selections, non-string or unknown codes, duplicates, case/whitespace variants, objects, old task payloads, and arbitrary prose. Accepted codes map to fixed backend-owned `system`, `action`, `description`, and `status: For Review` templates, preserving the frontend `{tasks: [...]}` response while ensuring request/model prose is never interpolated. The prior regex/denylist implementation was removed. Invalid output retains the fixed sanitized HTTP 502 without echoing model content.
- P0-G closed-vocabulary remediation files: `backend/engine/simulation_directives.py`; `backend/tests/test_simulation_directives.py`; `backend/routers/ai.py`; `CHATBOT_IMPLEMENTATION_PLAN.md` (P0-E ledger and subsection only). P0-B request-ID, SSE, provider-routing, and telemetry changes remain intact.
- P0-G closed-vocabulary remediation verification: Seven focused pure tests prove every accepted code maps to exact independently asserted backend text, returned templates are fresh copies, selected order is preserved, and old prose fields, unknown/duplicate/empty/excess codes, invalid shapes, and eleven P0-G bypass strings cannot reach output or error text. `python -m unittest discover -s backend/tests -v` passed all 32 tests. `python -m py_compile backend/engine/simulation_directives.py backend/tests/test_simulation_directives.py backend/routers/ai.py` passed without importing `backend/main.py`. Searches confirmed no obsolete simulation regex/denylist or model-authored task schema remains, the active route uses only `directive_codes` and `build_simulation_directives(...)`, the sanitized 502 remains, and the frontend still labels directives as local review with no external write. No frontend source changed, so its previously passing build was not rerun. Repository-wide `git diff --check` and no-index whitespace checks for all new/untracked P0-E files passed with line-ending warnings only.

##### P0-F: Test and Evaluation Scaffold

- Owner: P0-F subagent
- Status: `complete`
- Scope: Add safe test scaffolding and a small executable provisional evaluation baseline.
- Changes: Added standard-library `unittest` coverage that imports only the pure observability module, never `backend/main.py`, and exercises request-ID boundaries/fallback, correlated one-frame SSE serialization and event shapes, metadata-only JSON logging, evaluator validation, deterministic fact/evidence scoring, payload-free summaries, validation cohorts, and quality-gate failure. Added a standard-library evaluator with versioned JSON cases/responses, human stderr and machine-readable JSON stdout summaries, explicit provisional/generated/pending-validation statuses, separate validated and provisional aggregates, and exit codes 0/1/2 for pass/gate failure/input error. Seeded three `Execution`-sheet questions read safely from `Qns_AKASHA.xlsx`; all rubric values, evidence IDs, and responses are explicitly synthetic and not business-certified.
- Files changed: `backend/tests/__init__.py`; `backend/tests/test_observability.py`; `backend/tests/test_evaluation.py`; `backend/evaluation/__init__.py`; `backend/evaluation/evaluate.py`; `backend/evaluation/cases.v1.json`; `backend/evaluation/responses.v1.json`; `backend/evaluation/README.md`; `CHATBOT_IMPLEMENTATION_PLAN.md` (P0-F ledger and subsection only).
- Verification: `python -m unittest discover -s backend/tests -v` passed 16 tests; `python backend/evaluation/evaluate.py` exited 0 and passed 11/11 provisional rubric items across three cases while reporting `Validated: no cases`; `python -m py_compile backend/evaluation/evaluate.py backend/tests/test_observability.py backend/tests/test_evaluation.py` passed. A temporary `backend/evaluation/responses.intentional-fail.tmp.json` containing no responses was run with `python backend/evaluation/evaluate.py --responses backend/evaluation/responses.intentional-fail.tmp.json`; the evaluator reported all three gates failed and exited 1, and the temporary file was deleted. Scoped `git diff --check` passed for all P0-F files.
- Issues discovered: `openpyxl` is listed by the project but unavailable in the current interpreter, so workbook sheet names and question strings were inspected read-only through the XLSX ZIP/XML format using Python stdlib; no answer cells or business data were imported. The seeded 100% result proves only that the deterministic scorer recognizes its generated synthetic fixtures and is not a chatbot accuracy measurement. No Wave 1 runtime/UI files were modified.
- Blockers: None for the Phase 0 scaffold. There are no validated cases, representative production responses, or business-owned acceptance thresholds yet.
- Follow-up work: Phase 4 must import workbook/database benchmark candidates through an approved read-only process, remove sensitive data, establish business-certified expected answers and evidence, assign validated statuses, define representative slices and owned thresholds, and evaluate captured real chatbot responses before any accuracy claim.
- P0-G remediation: Closed the provisional evaluator's fail-open quality-gate path. Validation now runs before scoring, rejects missing/empty gate objects and unknown names, requires at least one recognized minimum score gate, accepts only finite numeric thresholds greater than 0 and at most 1, and requires `require_response_for_every_case` to be literal `true` when present. The final PASS calculation also requires a non-empty evaluated gate list as defense in depth. Synthetic fixtures, validation cohorts, and the explicit non-accuracy labeling are unchanged.
- P0-G remediation files: `backend/evaluation/evaluate.py`; `backend/evaluation/README.md`; `backend/tests/test_evaluation.py`; `CHATBOT_IMPLEMENTATION_PLAN.md` (P0-F ledger and subsection only).
- P0-G remediation verification: `python -m unittest discover -s backend/tests -v` passed 24 tests, including empty/missing, unknown/misspelled, completeness-only, invalid threshold/type, invalid completeness, nonzero CLI, and normal fixture coverage. `python backend/evaluation/evaluate.py` exited 0 with the unchanged provisional 11/11 synthetic result and `Validated: no cases`. A temporary empty response document produced `Quality gates: FAIL` and exit 1; temporary empty-gate and misspelled-gate case documents each produced `Evaluation input error` and exit 2; all temporary files were deleted. `python -m py_compile backend/evaluation/evaluate.py backend/tests/test_observability.py backend/tests/test_evaluation.py` and scoped `git diff --check` passed.

##### P0-G: Independent Review

- Owner: P0-G subagent
- Status: `complete`
- Scope: Final independent review of the closed-vocabulary simulation-directive design and regression confirmation for all previously resolved Phase 0 findings.
- Changes: Review only. No runtime/source fixes were made; this subsection and the P0-G ledger row are the only final-review edits.
- Files changed: `CHATBOT_IMPLEMENTATION_PLAN.md` (P0-G ledger row and subsection only).
- Verification: Reviewed the code-to-UI directive path without importing `backend/main.py` or accessing a database. `backend/routers/ai.py:874-905` requests and accepts only `directive_codes`; `backend/engine/simulation_directives.py:8-78` requires the exact top-level key, a bounded non-empty list of unique exact allowlisted strings, and maps selections to fresh copies of backend-owned templates. Unknown keys/codes, prose, wrong types/shapes, duplicates, empty lists, and excess entries fail before task construction. Invalid model JSON or contract output produces the sanitized non-echoing 502 at `backend/routers/ai.py:903-909`. The active UI receives only backend-generated `system`, `action`, `description`, and `status` values. `python -m unittest discover -s backend/tests -v` passed 32 tests; `backend/tests/test_simulation_directives.py:66-164` verifies every code/template, copy isolation, ordering, shape rejection, unknown/duplicate/empty/excess rejection, and P0-G prose bypass rejection. Independent probes rejected all four final bypass examples and five malformed/unknown/duplicate/excess payloads. `node --test tests/chatStream.test.mjs` passed 3 tests. `python backend/evaluation/evaluate.py` retained the explicitly provisional 11/11 result with no validated cases. Scoped `python -m py_compile`, targeted ESLint, and scoped `git diff --check` passed. `npm run build` completed TypeScript and the production Vite build with only the existing large-chunk warning.
- Findings: No unresolved findings.
- Resolved findings: The final simulation finding is resolved by the exact code vocabulary and backend-owned templates at `backend/engine/simulation_directives.py:8-78`; model/request prose cannot populate any user-visible task field. All prior remediations remain resolved: server-generated request UUID correlation and caller-header isolation; session-ID pseudonymization and sanitized vision failures; support-visible frontend request IDs; report quantity correctness and disabled export; fail-closed evaluation gates; simulation no-write UI wording; and consistently archival inactive-v2.2 documentation including `backend/README_V2_2.txt:538-550`.
- Blockers: None for P0-G. No validated production benchmark or business-owned acceptance threshold exists, but that is a documented later-phase dependency rather than a Phase 0 review defect.
- Residual risks: SQLAlchemy is unavailable in the current interpreter, so the live directive route and SSE transaction/disconnect behavior were not executed. Provider/LLM and database behavior were not exercised. Frontend SSE tests do not cover abort, early-consumer cancellation, or both React surfaces end-to-end. Report calculations have no dedicated unit tests. Stable unkeyed session-ID hashes remain pseudonyms rather than anonymization. The production build retains its existing large-chunk warning.
- Follow-up work: Preserve the closed-vocabulary boundary when adding future directive types; each new code should require a backend-owned template and corresponding rejection/mapping tests.

#### Phase 0 Closure

- Completion date: 2026-07-26.
- Coordinator status: `complete`.
- Exit criteria: Current behavior is measurable; known misleading chat, simulation, documentation, and report behavior is corrected or disabled; an executable provisional evaluation baseline exists.
- Final backend verification: `python -m unittest discover -s backend/tests -v` passed 32 tests; scoped `py_compile` passed without importing `backend/main.py`.
- Final frontend verification: `npm run build` passed; `node --test tests/chatStream.test.mjs` passed 3 tests; targeted chat-stream and report ESLint passed.
- Final evaluation verification: `python backend/evaluation/evaluate.py` passed 11/11 explicitly synthetic/provisional rubric items across three workbook-derived questions and reports no validated cases or production accuracy measurement.
- Final review: P0-G reports no unresolved findings after three remediation/re-review cycles.
- Final whitespace verification: `git diff --check` passed with line-ending conversion warnings only.
- Deferred environmental verification: Run live route-level SSE, transaction rollback, disconnect/cancellation, provider, database, and browser end-to-end tests in the provisioned application environment.
- Deferred product verification: Phase 4 must replace synthetic expected facts with database-derived evidence and later user-validated answers before any accuracy claim.

### Phase 1: Identity and Canonical Conversations

Deliverables:

- Entra ID integration.
- API authorization and CEO/PMAG roles.
- User-owned chat session/message APIs.
- Server-generated session IDs.
- Frontend history migrated from local storage.
- Session list, resume, rename, and delete.
- Typed SSE event contract.

Exit criteria:

- One user cannot access another user's chat.
- A user can reopen a chat in a new browser session and continue it.
- The client no longer submits authoritative conversation history.

#### Phase 1 Progress

Overall implementation status: `complete`

Deployment status: `pending_external_configuration`

##### Identity and Authorization

- Replaced the local random-token placeholder with signed Microsoft Entra access-token validation in `backend/security.py`.
- Validates RS256 signature, issuer, audience, tenant, expiration, user object ID, and supported app-role/group assignment.
- Maps `Akasha.CEO` to `executive` and `Akasha.PMAG` to `pmag`; configurable group IDs are supported as a fallback, while unresolved group-overage claims fail closed.
- Registered every business API router with a CEO/PMAG identity dependency. In production Entra mode it requires a bearer token; in explicit development mode it accepts a bounded browser-session identity and selected CEO/PMAG role. `/api/auth/me` returns the resolved identity. Local password login and public seed endpoints return HTTP 410.
- Added frontend development CEO/PMAG selection as the current default so local development does not require a Microsoft account. Added MSAL popup/restore/logout behavior for Entra mode, with tokens held in MSAL `sessionStorage`, never Akasha `localStorage`.
- Added a centralized same-origin fetch boundary that attaches bearer tokens only to Akasha API requests and clears the local identity after HTTP 401.
- Added frontend route guards: CEO routes require `executive`; PMAG routes require `pmag`.
- Replaced wildcard credentialed CORS with configured exact origins, bearer-compatible headers, and exposed request/session correlation headers.
- Removed process-wide and active runtime TLS-verification bypasses. Corporate trust now uses standard CA-bundle environment variables.

##### Canonical Conversations

- Added Entra tenant/user ownership fields and indexes to `ChatSession`; existing unowned sessions intentionally remain inaccessible.
- Added assistant chart and request-ID persistence to `ChatMessage`.
- Added owner-filtered create/list/get/rename/delete APIs under `/api/chat/sessions` with random server-generated session IDs.
- Added a constrained legacy-browser import endpoint. The frontend asks for explicit import consent; declining removes unscoped browser history. Successful imports are removed incrementally so retries do not duplicate completed threads.
- Imported assistant text remains visible as assistant history but is marked as legacy and supplied to future model context only as untrusted user-role transcript text.
- The active chat route requires an owned server session, rejects client `history`, loads canonical PostgreSQL messages, commits the user turn before streaming, and commits the assistant turn with charts and metadata on completion.
- Feedback submission verifies that the assistant message belongs to the authenticated tenant/user.
- Removed raw HTML processing from full-chat Markdown rendering.

##### Typed Streaming

- The active SSE contract now includes `start`, `status`, `token`, `visualization`, `metadata`, `error`, and `done` events.
- `start` exposes the canonical user message ID; `done` exposes the canonical assistant message ID.
- Both active chat surfaces use server session IDs and no longer submit conversation-history arrays.
- Full chat history supports server-backed list, resume, rename, and delete. The compact panel lists and resumes the same private server sessions.

##### Schema and Configuration

- Added `backend/migrations/phase1_chat_ownership.sql`; it must run before Phase 1 deployment.
- Added `AUTHENTICATION_SETUP.md` with Entra registration, app roles, scopes, environment variables, CORS, CA trust, and migration instructions.
- Added `PyJWT[crypto]` and `@azure/msal-browser`; added `backend/requirements-dev.txt` for API contract testing.
- Changed dotenv loading to preserve deployment environment variables rather than overriding them from local `.env` files.

##### Verification

- `python -m unittest discover -s backend/tests -v`: 58 tests passed.
- Backend tests cover claim mapping, token failure sanitization, role rejection, random session IDs, cross-user list/read/rename/delete/chat isolation, unowned-session isolation, legacy import, untrusted imported assistant context, request-schema rejection of client history, image-only prompts, canonical message persistence, and SSE lifecycle output.
- `npm run build`: TypeScript and production Vite build passed.
- `node --test tests/*.test.mjs`: 9 frontend contract tests passed for bearer scoping, development-header scoping, unauthorized handling, session API calls, retry-safe legacy migration, lifecycle SSE events, split frames, and correlated errors.
- Targeted ESLint for all new authentication, session-client, and stream-contract modules passed.
- The Phase 0 provisional evaluator remains green and explicitly reports no validated production cases.
- `git diff --check` passed with line-ending conversion warnings only.

##### Deployment Blockers and Residual Risks

- A real Entra tenant/app registration, API scope, app-role assignments, redirect URIs, and access token were not available in this workspace. Cryptographic validation is implemented and mocked at the library boundary, but live Entra login remains deployment verification.
- Development authentication is intentionally open and is now the default for local work. It is not production authentication. Production deployment is blocked until both `AKASHA_AUTH_MODE=entra` and `VITE_AUTH_MODE=entra` are set and the Entra flow is verified.
- The PostgreSQL migration was not applied to a production database. API ownership and persistence tests ran against isolated SQLite databases only.
- Existing scheduled scripts or external API consumers must be updated to acquire Entra tokens because all business APIs now fail closed without bearer authentication.
- CEO and PMAG are distinguished at the frontend route level, while shared backend business routers currently allow either supported role. A finer endpoint/project authorization matrix requires business ownership rules.
- `npm audit` reports two high-severity React Router advisories against the latest available `7.18.1`, centered on React Server Components/action handling that this BrowserRouter SPA does not use. No non-vulnerable stable package release is currently available; production requires upstream remediation or formal risk acceptance.
- Existing hardcoded Transmission Portal credentials and several diagnostic scripts with TLS bypasses were not part of the chatbot session implementation and remain security remediation work. Runtime P6, TC, Pulse, provider, and global request paths no longer disable TLS verification.
- Explicit failed/cancelled assistant-message states and checkpoint deletion belong to Phase 2.

##### Exit-Criteria Result

- Cross-user session access: passed through API and route tests returning non-disclosing HTTP 404 responses.
- Reopen/resume: passed through canonical session retrieval and a second chat turn using database-loaded context.
- No authoritative client history: passed; the request schema forbids `history`, and both active clients submit only the new message and owned session ID.

### Phase 2: LangGraph and Context

Deliverables:

- Parent StateGraph and tool-calling agent subgraph.
- Postgres checkpointer.
- Token-aware context policy and summarization.
- Typed tool runtime with authenticated user/project context.
- Cancellation, errors, and done events.
- Phased traffic switch with rollback to the existing path.

Exit criteria:

- Graph sessions survive API restart.
- Long chats remain within provider context limits.
- Tool-call/result groups remain valid after context management.
- Failed and cancelled runs have explicit application status.

#### Phase 2 Progress

Overall implementation status: `complete`

Deployment status: `pending_external_configuration`

##### LangGraph Execution

- Added a checkpointable parent `StateGraph` with explicit context validation, context compaction, tool-agent subgraph, and finalization nodes under `backend/engine/graph/`.
- The tool-agent subgraph uses provider-native tool calling, executes every returned tool call, appends matching `ToolMessage` results, and loops until a final assistant response is produced.
- Graph state is serializable and contains only messages, derived summary text, identity/thread bindings, project scope, transcript cursor, run correlation, and small execution metadata. Database sessions, ORM records, credentials, images, and provider clients are not checkpointed.
- Persisted checkpoint ownership is bound to tenant and user and is validated again on every invocation, independently of the route's session-ownership check.
- Canonical application messages use deterministic LangChain message IDs. A checkpointed transcript cursor reconciles completed turns created while the legacy engine was active without rehydrating history already removed by summarization.

##### PostgreSQL Checkpoints

- Added pinned compatible LangChain/LangGraph, Psycopg 3, and PostgreSQL checkpointer dependencies.
- Added one process-owned Psycopg 3 connection pool and `PostgresSaver` lifecycle through FastAPI lifespan. The SQLAlchemy application remains on its existing driver during this migration.
- Uses the random application session ID as LangGraph `thread_id`, so checkpoints resume the same private conversation after process recreation.
- Added `backend/scripts/setup_langgraph_checkpoint.py` as an explicit deployment command. API processes perform a readiness query but do not run LangGraph DDL.
- Session deletion first tombstones the application session, deletes the complete checkpoint thread, and then removes application rows. A graph-backed session remains inaccessible and returns a retryable deletion failure if checkpoint cleanup cannot complete.
- Stale pending/running/cancel-requested application runs are marked `interrupted` after the configured recovery timeout at startup.

##### Context Management

- Replaced six-message truncation on the LangGraph path with an approximately token-counted, model-window-specific budget resolved from the active model profile or provider metadata.
- Summarization begins at 60 percent of usable context after reserving output, system-prompt, and tool-schema capacity; a separate hard threshold bounds recent payloads if summarization is unavailable.
- Context grouping preserves human-turn boundaries and treats assistant tool calls plus all matching tool results as indivisible protocol groups.
- At least the newest four complete turns remain in graph context. Older turns are summarized into explicitly derived, non-evidentiary context while the complete canonical transcript remains in application tables.
- Tool output is bounded before checkpointing, and oversized recent message/tool content is truncated without removing protocol messages or creating orphaned tool results.
- `AKASHA_MODEL_CONTEXT_WINDOW` is an optional explicit override only. Recognized OpenAI/Azure models use LangChain profiles, OpenRouter/Ollama/Groq use provider model metadata, and an unknown limit fails startup instead of assuming a global default.
- OpenRouter requests use ordered native model fallbacks for rate limits and provider/model failures. Startup verifies tool-calling support for every model, context budgeting uses the smallest configured window, and the model selected for the final answer is persisted with the run/message. The configured free defaults require explicit organizational privacy acceptance before use with sensitive project data.
- Provider rate-limit, authentication, unavailable-route, timeout, and connection failures map to stable sanitized application error codes; provider response bodies remain server-side.
- Failed or cancelled graph turns reset their checkpoint thread before the next invocation, preventing an assistant tool call without its matching result from poisoning resumed history; the next turn reconstructs completed canonical turns and creates a clean checkpoint.
- Graph turns have a configurable bounded model-call budget. The final permitted call has tools disabled and must synthesize from evidence already collected with explicit scope limitations, preventing unbounded model/tool cycling; the LangGraph recursion limit remains a hard safety backstop with a specific client error.

##### Authenticated Tool Runtime

- Added Pydantic argument contracts for every active graph tool, with strict unknown-field rejection and bounded ranking, row-count, threshold, multiplier, keyword, and chart arguments.
- Tool identity, tenant, role, session, request, run, and selected project scope are injected from authenticated server state and are not model-supplied arguments.
- Every project argument is independently checked against canonical project records and selected scope. Scoped conversations cannot invoke portfolio-wide tools.
- Each tool opens and closes its own SQLAlchemy session, checks durable cancellation before and after work, sanitizes internal failures, and returns a bounded typed status/data result.
- The existing deterministic business functions remain the calculation implementation. The legacy ReAct loop remains unchanged as the rollback path.

##### Run Lifecycle and Streaming

- Added `ChatRun` plus message status, run, engine, safe error-code, and completion fields. The user message, running assistant placeholder, and run are committed before streaming.
- Added explicit `running`, `completed`, `failed`, `cancelled`, and `interrupted` message states and `pending`, `running`, `cancel_requested`, `completed`, `failed`, `cancelled`, and `interrupted` run states.
- Added an owner-checked, idempotent `POST /api/chat/runs/{run_id}/cancel` endpoint. Both active frontend surfaces request cancellation before aborting the response stream.
- Version 2 SSE events carry request, session, run, version, and monotonic sequence correlation. Success, failure, and cancellation end in a typed `done` event with durable terminal status; failures also emit sanitized `error`, and connected cancellations emit `cancelled`.
- The shared frontend parser validates Phase 2 sequence/correlation, rejects events after completion, and treats a clean EOF without `done` as an interrupted stream rather than success.
- A final graph answer must contain visible text unless a visualization was produced. Empty or malformed model output receives one repair attempt; repeated invalid output fails the run instead of persisting a blank `completed` assistant message, and both frontend surfaces independently reject content-free completion.
- Full and compact chat surfaces render backend progress and restored terminal status, preserve partial output, and expose cancellation controls. Failed and cancelled turns remain visible after reopening a session but are excluded from future model context.

##### Rollout and Schema

- Added server-owned `AKASHA_CHAT_ENGINE=legacy|canary|langgraph` selection and `AKASHA_LANGGRAPH_ROLLOUT_PERCENT=0..100`.
- Canary assignment is a deterministic tenant/user/session cohort and is persisted on the session. The client cannot select an engine, and no automatic fallback occurs after graph execution begins.
- `legacy` is an immediate kill switch for new turns. Canonical transcript reconciliation permits graph re-enablement after legacy rollback without losing completed rollback-period turns.
- Added `backend/migrations/phase2_langgraph_context.sql` for application lifecycle/schema changes and active-run uniqueness. Runtime schema mutation is now disabled unless the explicit local-only `AKASHA_AUTO_MIGRATE=true` setting is used.
- Updated `LOCAL_SETUP.md` with the required migration, checkpoint setup, canary, rollback, and context-window configuration.
- Backend installation and verification must use `backend/.venv`; system/user-level Python package installation is not an accepted project setup. Automation should invoke `backend/.venv/Scripts/python.exe` explicitly when activation is unavailable.

##### Verification

- `backend/.venv/Scripts/python.exe -m unittest discover -s backend/tests -v`: 90 tests passed.
- Phase 2 backend tests cover complete turn/tool grouping, orphan detection, four-turn retention, bounded payload structure, parent/subgraph checkpoint resume with `InMemorySaver`, checkpoint owner isolation, tool-call/result execution, durable success/failure status, sanitized failure SSE, owner-checked idempotent cancellation, and stable canary/rollback behavior.
- `backend/.venv/Scripts/python.exe -m pip check`: passed with no broken requirements.
- Scoped backend `py_compile`: passed for models, routers, lifecycle service, all graph modules, main lifespan, and checkpoint setup command.
- `node --experimental-strip-types --test tests/*.test.mjs`: 11 frontend contract tests passed, including correlated Phase 2 cancellation and rejection of terminal-event-free EOF.
- `npm run build`: TypeScript and production Vite build passed with the existing large-chunk warning.
- `git diff --check`: passed with line-ending conversion warnings only.

##### Exit-Criteria Result

- Graph persistence across process recreation: implemented through `PostgresSaver` with application session ID as `thread_id`; in-memory recreation/resume tests passed. Live PostgreSQL restart verification remains a deployment check.
- Provider context limits: implemented through configurable token budgets, summary and hard thresholds, bounded tool payloads, and four-turn structural retention; focused boundary tests passed.
- Tool-call/result validity: passed focused complete-group, orphan-rejection, compaction, and graph tool-loop tests.
- Failed and cancelled application status: passed route, persistence, ownership, idempotency, frontend contract, and reopen-payload tests.

##### Deployment Blockers and Residual Risks

- The Phase 2 application migration and LangGraph checkpoint setup command were not applied to a production PostgreSQL database in this workspace.
- No provisioned live model credentials or production model endpoint were available, so provider-specific tool-calling smoke tests and live graph cancellation latency remain deployment verification.
- The workspace did not have the recommended Python 3.12 interpreter. Verification used the project-owned `backend/.venv` created with available Python 3.14; production should retain the documented Python 3.12 baseline until 3.14 is formally approved.
- Synchronous provider calls can observe cancellation only between graph nodes or after the provider call returns. The durable cancel request prevents later successful application finalization, but immediate upstream compute termination depends on provider support.
- A real PostgreSQL integration run must verify checkpoint setup/readiness, API restart resume, multi-process concurrency, thread deletion, and rollback/re-enable reconciliation before enabling non-zero canary traffic.

##### Post-Phase-2 Accuracy Remediation

- Corrected project progress semantics so P6 `SummaryDurationPercentComplete` is the authoritative overall progress metric; completed activities divided by total activities is retained only as a separately labelled activity-count ratio.
- Removed the activity-count-based SPI proxy. Null P6 SPI/CPI values remain unavailable, and schedule/health classifications remain `UNKNOWN` instead of being inferred from unsupported substitutes.
- Added project status, activity counts, scheduled finish, P6 data date, and synchronization timestamp to the deterministic project KPI result.
- Added a bounded `p6_get_activities` tool with canonical status filtering and pagination for completed, in-progress, not-started, or all activities.
- Added one narrow repair attempt when a provider emits literal `<tool_call>` or `<function=...>` markup as answer text. Ordinary non-empty analytical responses are not subjected to a broader formatting gate.
- Hardened intermittent provider-format recovery: one complete XML-style call is converted only when its tool is registered and its arguments pass the existing strict Pydantic contract; malformed/unknown markup, invalid native calls, and empty outputs receive one tool-enabled semantic retry. Final raw markup remains blocked, and diagnostics record categories rather than response content.
- Live read-only verification for `FY26-P18` returned 23.1 percent P6 duration progress, 486 completed, 84 in progress, 1,730 not started, null SPI/CPI, Active status, scheduled finish 1 October 2027, data date 18 July 2026, and last synchronization 22 July 2026.
- Verification: 106 backend unittests passed, including new metric-semantics, project-summary normalization, status-filtered activity listing, raw-tool-markup repair, and repeated-invalid-output tests; scoped `py_compile` and `git diff --check` passed with line-ending warnings only.



### Phase 5: Canonical Reports

#### MVP Scope Implemented Before Full Phase 5

- Chatbot-first Project Progress Report only; Portfolio Executive and Weekly PMAG remain deferred.
- The chatbot resolves the project, creates a deterministic latest-data preview, and waits for explicit confirmation.
- Confirmed reports are generated synchronously in the chat request without report jobs, workers, Redis, Celery, polling, retries, or scheduling.
- One canonical in-memory dataset supplies P6 schedule, SAP procurement, TC transmission, Pulse quality, source freshness, missing-source warnings, and a bounded in-progress activity list.
- Deterministic services own all metrics. An optional AI executive narrative is constrained to the canonical facts and falls back to deterministic prose if unavailable.
- PDF and DOCX use the same dataset and a simple Akasha-branded server-side template.
- Generated files use opaque IDs, owner/tenant-checked downloads, local temporary storage, checksums, and 24-hour expiry. Cleanup occurs opportunistically during generation/download in this MVP.
- Download buttons are rendered inside the full chatbot; no report page or session report drawer is included.
- Deployment requires `backend/migrations/phase5_mvp_reports.sql`, `reportlab`, and `python-docx`.
- Full Phase 5 job durability, canonical evidence ledger, renderer retry, and production cleanup worker remain deferred.

Deliverables:

- Report preview and confirmation flow.
- Canonical P6/SAP/TC/Pulse report datasets.
- Project Progress, Portfolio Executive, and Weekly PMAG templates.
- PostgreSQL report jobs and worker command.
- PDF, DOCX, and XLSX renderers.
- 24-hour authenticated downloads and cleanup.
- Chat report progress and download UI.

Exit criteria:

- All three formats show matching metrics and warnings.
- Every material report claim maps to canonical evidence.
- Failed format rendering can be retried safely.
- Expired files cannot be downloaded and are removed.

### Phase 6: Consolidation and Production Hardening

Deliverables:

- Remove inactive chatbot clients and obsolete orchestration code.
- Remove or archive inactive v2.2 implementation after useful concepts are ported.
- Remove startup schema mutation.
- Production migration, backup, rollback, and operations runbooks.
- Load, security, failure-recovery, and provider-fallback tests.
- Dashboards and alerts for chat/report health.

Exit criteria:

- One documented chatbot architecture remains.
- Production readiness and security checks pass.
- Rollback has been tested.

### Later Phases

- Explicit cross-chat user preferences if product evidence justifies them.
- Scheduled weekly/monthly reports.
- SharePoint report publication and approval workflow.
- Document ingestion and RAG with page/sheet/slide citations.
- Shared project conversations, if privacy requirements change.
- Additional export formats such as CSV, JSON, or PowerPoint.

## 15. Suggested Workstream Order

Work can proceed in parallel after Phase 0:

| Workstream | Dependencies |
|---|---|
| Entra ID and authorization | Starts immediately |
| Session APIs and frontend history | Identity contract |
| LangGraph prototype | Can start with test identity context |
| Tool evidence contracts | Can start immediately |
| Workbook classification and expected facts | Stable deterministic tools and database access |
| Report dataset design | Stable KPI/tool semantics |
| Format renderer prototypes | Canonical report schema draft |
| UI consolidation | Typed SSE and session API contracts |

Recommended sequence for risk reduction:

1. Security and canonical sessions.
2. Evidence contracts and evaluation baseline.
3. LangGraph migration and context persistence.
4. Claim verification and provider consolidation.
5. Report datasets and renderers.
6. Cleanup and production hardening.

## 16. Key Risks and Mitigations

| Risk | Mitigation |
|---|---|
| Workbook answers are mostly missing | Generate deterministic expected facts, preserve evidence, and mark pending validation |
| Database-derived expected answer is itself wrong | Version formulas and queries; require later business validation |
| Long conversations create expensive checkpoints | Token limits, tool-output compaction, summaries, and retention cleanup |
| Summary loses an important fact | Keep canonical transcript and structured unresolved context; never use summary as evidence |
| Model emits unsupported report numbers | Structured claims, deterministic report dataset, verifier, and abstention |
| Different formats disagree | Render all formats from one immutable dataset hash |
| Local artifact unavailable on another server | Use single-host/shared-volume constraint initially; move to object storage before horizontal scaling |
| Database-backed worker processes duplicate jobs | Row locking, idempotency keys, heartbeats, and artifact uniqueness constraints |
| Provider lacks tool/structured-output support | Capability validation and explicit adapter/fallback policy |
| Cutoff date implies unavailable historical state | Disclose source-history limits and avoid claiming full point-in-time reconstruction |
| User deletes a chat but checkpoints remain | Coordinated deletion workflow with reconciliation and audit status |
| Prompt injection requests unauthorized data | Tool-level authorization and immutable runtime identity context |

## 17. Definition of Done

The initial program is complete when:

- CEO and PMAG users authenticate with Entra ID.
- Every chat and report is private to its owner and authorized project scope.
- Users can list, reopen, resume, rename, and delete conversations.
- LangGraph restores thread state from PostgreSQL without client-supplied history.
- Long conversations are summarized safely within a measured context budget.
- Data-backed answers expose source and freshness.
- Material numbers and dates are verified against run evidence.
- Missing, stale, or conflicting evidence produces a warning or abstention.
- Grounding and numeric regression gates pass on the curated evaluation suite.
- Project Progress, Portfolio Executive, and Weekly PMAG reports are available.
- Report previews show scope, period, sources, freshness, and warnings.
- PDF, DOCX, and XLSX outputs share the same canonical metrics.
- Artifacts are downloadable only by the requesting user and expire after 24 hours.
- The current duplicate chat implementations and misleading report paths are removed.
- Security, integration, load, recovery, and renderer tests pass.
- Deployment and rollback procedures are documented and tested.

## 18. Immediate Next Actions

1. Approve this architecture and phase order.
2. Inventory Entra tenant/app-registration requirements and CEO/PMAG group mappings.
3. Define source-specific freshness thresholds with P6/SAP/TC/Pulse data owners.
4. Establish a sanitized database fixture or snapshot for repeatable evaluation.
5. Import and classify `Qns_AKASHA.xlsx` without changing its source copy.
6. Select the first 20 high-value questions across project resolution, schedule, procurement, TC, and quality.
7. Generate provisional expected facts and evidence from the database for user validation.
8. Draft the typed SSE, tool evidence, structured answer, and report dataset schemas.
9. Prototype LangGraph checkpoint/resume against PostgreSQL in an isolated endpoint.
10. Prototype one Project Progress dataset and render it to PDF, DOCX, and XLSX before building the full report UI.

## 19. Official LangChain and LangGraph References

- Memory concepts: https://docs.langchain.com/oss/python/concepts/memory
- LangGraph memory: https://docs.langchain.com/oss/python/langgraph/add-memory
- Checkpointers and threads: https://docs.langchain.com/oss/python/langgraph/checkpointers
- LangGraph persistence: https://docs.langchain.com/oss/python/langgraph/persistence
- LangGraph stores: https://docs.langchain.com/oss/python/langgraph/stores
- LangChain agents: https://docs.langchain.com/oss/python/langchain/agents
- Context overview: https://docs.langchain.com/oss/python/concepts/context
- Summarization middleware: https://docs.langchain.com/oss/python/langchain/middleware/built-in#summarization
- Tools and runtime context: https://docs.langchain.com/oss/python/langchain/tools
- Human-in-the-loop: https://docs.langchain.com/oss/python/langchain/human-in-the-loop
- LangSmith chatbot evaluation: https://docs.langchain.com/langsmith/evaluate-chatbot-tutorial

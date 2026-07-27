# Active Production Chatbot Path

This document describes the chatbot path currently registered by the application. It is a code-as-built baseline, not the target architecture in `CHATBOT_IMPLEMENTATION_PLAN.md`.

## Active Request Flow

```text
CEODashboard
  -> AICopilot
  -> configured auth identity (development selector or Microsoft Entra)
  -> user-owned chat_session API
  -> POST /akasha/api/chat
  -> AkashaPathRewriteMiddleware: /akasha/api/chat -> /api/chat
  -> routers.ai.chat_with_copilot
  -> ChatOrchestrator.process_message_stream(is_deep_analysis=True)
  -> run_deep_analysis_agent_stream
  -> P6/SAP/TC/portfolio/notification/simulation/KPI/chart tools
  -> SSE token and visualization events
  -> final metadata handling and chat_session/chat_message persistence
  -> SSE metadata event
  -> AICopilot SSE parser and renderer
```

1. `frontend/src/pages/CEODashboard.tsx` mounts `frontend/src/features/chatbot/AICopilot.tsx` for the `ai_copilot` tab.
2. In the current default development mode, the user selects CEO or PMAG and the browser sends a temporary session identity through development-only headers. With both auth modes set to `entra`, MSAL attaches a bearer token and the backend validates its signature, issuer, audience, tenant, and CEO/PMAG assignment. Development mode is not suitable for an untrusted network.
3. `AICopilot` lists and restores owner-filtered sessions through `backend/routers/chat_sessions.py`. New session IDs are random server-generated values. The client sends only the new message, owned session ID, deep-analysis toggle, and optional image to `POST /akasha/api/chat`; it does not submit authoritative conversation history.
4. `backend/main.py` registers the protected routers. Its pure-ASGI `AkashaPathRewriteMiddleware` rewrites `/akasha/api/chat` to `/api/chat` without buffering the response.
5. `backend/routers/ai.py` verifies session ownership, loads prior user/assistant messages from PostgreSQL, persists the current user turn, and calls `ChatOrchestrator.process_message_stream` with `is_deep_analysis=True`; the request's `isDeepAnalysis` value cannot select another branch.
6. `backend/engine/orchestrator.py` optionally prepends vision-model output, then enters its deep-analysis branch and calls `backend/engine/agent.py::run_deep_analysis_agent_stream`.
7. The agent gives the configured model the `TOOLS` schemas and runs a ReAct loop of at most 15 model turns. `execute_tool` dispatches database-backed P6, SAP, TC, portfolio, notification, simulation, and KPI functions. `render_chart` instead builds a database-backed ECharts specification for a visualization event.
8. When the model returns no tool calls, its final answer has already been generated. The agent splits that completed answer on line endings; these chunks are not provider-token streaming. It also emits the tool-name list and any visualization specifications.
9. The orchestrator accumulates answer text and emits final response metadata. `backend/routers/ai.py` emits typed `start`, `status`, `token`, `visualization`, `metadata`, `error`, and `done` SSE events.
10. On final metadata handling, the router inserts the assistant `ChatMessage`, including tool names, charts, latency, and request ID. The user message was already committed before model execution, so a failed generation does not erase the submitted turn.
11. `AICopilot` uses `frontend/src/features/chatbot/chatStream.ts` to parse SSE frames and updates the answer, charts, suggestions, and source labels. Reopening a session loads canonical messages from PostgreSQL; browser storage is used only for the one-time legacy import/removal decision.

## Persistence Boundary

The current user turn is committed before the stream begins. A completed assistant turn is committed when final metadata is produced. A failure, cancellation, or disconnect can therefore leave a persisted user turn without an assistant turn; explicit failed/cancelled assistant states are planned for Phase 2. Feedback is ownership-checked through `POST /akasha/api/chat/feedback`.

## Inactive and Legacy Alternatives

- **v2.2 is inactive.** `backend/routers/ai_v2_2.py` and `backend/engine/orchestrator_v2_2.py` exist, but `backend/main.py` neither imports nor includes `ai_v2_2.router`. Therefore `/api/chat-v2.2` and its companion v2.2 endpoints are not registered. The v2.2 deployment documents describe an unactivated historical design, and their accuracy percentages are unvalidated targets rather than measured results.
- **The standard fast pipeline is inactive for `POST /api/chat`.** The non-deep branch in `ChatOrchestrator.process_message_stream` remains in the source but cannot be reached through the registered chat route while `backend/routers/ai.py` forces `is_deep_analysis=True`.
- **The non-streaming orchestrator entry point is inactive for this route.** `ChatOrchestrator.process_message` is not called by `chat_with_copilot`.
- **Enhanced-orchestrator examples are not registered.** `backend/engine/enhanced_orchestrator.py` and its guides/examples are alternatives, not the active `AICopilot` path.
- Other chat UI components that post to the same URL are not the canonical full chat experience. The implementation plan identifies `AICopilot` as the component to retain and the others for later consolidation.

## Current Limitations Relevant to Later Phases

- The active tool registry has no direct Pulse quality tool despite Pulse being a planned answer source.
- Source metadata is a list of tool names, not claim-level evidence, source rows, or freshness timestamps.
- Conversation history is now loaded from an owner-filtered application transcript, but LangGraph checkpoints and token-aware summarization are not implemented until Phase 2.
- The final answer is generated before textual SSE chunks begin, so time to first displayed text includes full answer generation.
- Persistence has separate user-start and assistant-complete commits but no explicit interrupted or failed assistant state.
- No executable benchmark supports a measured chatbot accuracy percentage for either the active path or inactive v2.2 path.

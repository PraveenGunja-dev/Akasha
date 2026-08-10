# 🤖 Akasha AI Chatbot — Comprehensive Architecture, Data Flow & Developer Guide

Welcome to the **Akasha Chatbot Engine** codebase. This document serves as the complete technical blueprint and developer onboarding guide for understanding how the chatbot operates, how data is retrieved, how responses are generated, what technologies power it, and what data sources are currently connected versus pending.

---

## 📑 Table of Contents

1. [Executive Overview](#1-executive-overview)
2. [Complete Technical Stack](#2-complete-technical-stack)
3. [Chatbot Architectural Approach & Execution Flow](#3-chatbot-architectural-approach--execution-flow)
   - [A. ReAct (Reasoning & Acting) Agent Loop](#a-react-reasoning--acting-agent-loop)
   - [B. v2.1 6-Step Intelligent Pipeline](#b-v21-6-step-intelligent-pipeline)
   - [C. v2.2 8-Step Ultra-Accurate Pipeline & 5 Engines](#c-v22-8-step-ultra-accurate-pipeline--5-engines)
4. [Data Sources: Connected vs. Not Connected / Pending](#4-data-sources-connected-vs-not-connected--pending)
5. [How Data is Fetched (Tool Execution System)](#5-how-data-is-fetched-tool-execution-system)
6. [How Responses are Generated & Streamed](#6-how-responses-are-generated--streamed)
7. [Directory Structure & Key File Map](#7-directory-structure--key-file-map)
8. [Developer Guide: How to Work on & Extend the Chatbot](#8-developer-guide-how-to-work-on--extend-the-chatbot)

---

## 1. Executive Overview

The **Akasha AI Copilot** is a deep-analysis project intelligence assistant for large-scale EPC (Engineering, Procurement, and Construction) renewable energy projects (Solar, Wind, Transmission). 

It allows project managers, engineers, and executives to ask complex natural language questions such as:
- *"Which projects have delayed transmission lines?"*
- *"Show me critical path activities for Khavda Solar Phase 2"*
- *"What are the SAP material gaps for project P-102?"*
- *"Run a what-if simulation if monsoon delays activity X by 30 days"*

---

## 2. Complete Technical Stack

| Layer | Technology | Usage / Purpose |
| :--- | :--- | :--- |
| **LLM Provider / Brain** | **OpenRouter API** (`meta-llama/llama-3.3-70b-instruct`) | Multi-provider LLM backend (supports OpenRouter, Groq, Azure OpenAI, Ollama). |
| **Backend Framework** | **Python 3.12 + FastAPI + Uvicorn** | High-performance asynchronous web server and REST/SSE endpoints. |
| **ORMM & Database** | **SQLAlchemy + PostgreSQL 18** | Relational database holding projects, activities, inventory, substations, chat sessions, and messages. |
| **Agent Framework** | **Custom ReAct Agent + LangChain** | Dynamic tool calling, step-by-step reasoning, and response synthesis. |
| **Frontend UI** | **React 19 + TypeScript + Vite + TailwindCSS** | Dynamic dashboard UI with interactive streaming chat interface. |
| **Data Visualization** | **ECharts + ReCharts + Deck.gl + Leaflet** | Interactive charts, maps, and network topology visualizations returned by chatbot tools. |
| **Background Tasks** | **Celery + Redis** | Asynchronous data synchronization tasks for P6 and SharePoint. |
| **Integrations** | **Microsoft Graph API + Primavera P6 REST API** | SharePoint SAP report downloads & Primavera schedule sync. |

---

## 3. Chatbot Architectural Approach & Execution Flow

The chatbot operates using a hybrid agent architecture combining **ReAct (Reasoning and Acting) Tool-Calling** with an **8-Step Validation Pipeline**.

```
                           +------------------------+
                           | User Prompt / Question |
                           +-----------+------------+
                                       |
                                       v
                        +--------------+---------------+
                        |   FastAPI /api/chat Endpoint |
                        +--------------+---------------+
                                       |
                                       v
                        +--------------+---------------+
                        |   ReAct Deep Analysis Agent  |
                        +--------------+---------------+
                                       |
         +-----------------------------+-----------------------------+
         |                             |                             |
         v                             v                             v
+------------------+         +-------------------+         +-------------------+
|  P6 Tools (SQL)  |         |  SAP Tools (SQL)  |         |  TC Tools (SQL)   |
+--------+---------+         +---------+---------+         +---------+---------+
         |                             |                             |
         +-----------------------------+-----------------------------+
                                       |
                                       v
                        +--------------+---------------+
                        | LLM Tool Response & Synthesis |
                        +--------------+---------------+
                                       |
                                       v
                        +--------------+---------------+
                        | Server-Sent Events (SSE)     |
                        | Streaming Chunk Output       |
                        +--------------+---------------+
                                       |
                                       v
                        +--------------+---------------+
                        | Final Metadata & Session Save |
                        +-------------------------------+
```

### A. ReAct (Reasoning & Acting) Agent Loop
Located in [`backend/engine/agent.py`](file:///c:/Users/Sree%20Charan/Desktop/Akasha1/Akasha/backend/engine/agent.py):
1. **Fuzzy Project Name Resolution**: If a project name (e.g. *"Khavda 2"*) is mentioned, the agent calls `portfolio_resolve_project_id` to get the canonical `project_id` (e.g. `P-102`).
2. **Dynamic Tool Calling**: The LLM analyzes the request and invokes specific tools (e.g., `p6_get_critical_activities`, `sap_get_material_gaps`).
3. **Observation & Synthesis**: Tool results are fed back to the LLM. It repeats tool calls if further data is needed, then generates a comprehensive, Markdown-formatted final answer.

### B. v2.1 6-Step Intelligent Pipeline
Located in [`backend/engine/orchestrator.py`](file:///c:/Users/Sree%20Charan/Desktop/Akasha1/Akasha/backend/engine/orchestrator.py):
1. Intent Classification & Project Extraction.
2. Context Retrieval (Database SQL & KPIs).
3. Risk Assessment & Trend Computation.
4. Intelligent Prompt Construction.
5. LLM Synthesis & Chart Recommendation.
6. Session Persistence & SSE Streaming Output.

### C. v2.2 8-Step Ultra-Accurate Pipeline & 5 Engines
Located in [`backend/engine/orchestrator_v2_2.py`](file:///c:/Users/Sree%20Charan/Desktop/Akasha1/Akasha/backend/engine/orchestrator_v2_2.py) and [`backend/engine/accuracy_engines.py`](file:///c:/Users/Sree%20Charan/Desktop/Akasha1/Akasha/backend/engine/accuracy_engines.py):
- **Semantic Understanding Engine**: Extracts domain concepts and canonical terms.
- **Cross-Source Validator**: Verifies consistency between P6 schedules and SAP material delivery dates.
- **Clarifying Questions Engine**: Detects ambiguity and prompts the user for missing project identifiers.
- **Confidence Scoring Engine**: Computes a 4-factor confidence score (Data completeness, Source freshness, Alignment, Model certainty).
- **Composite Metrics Engine**: Generates multi-dimensional health scores.

---

## 4. Data Sources: Connected vs. Not Connected / Pending

| Data Domain | Data Source | Connection Status | Details / Storage Location |
| :--- | :--- | :--- | :--- |
| **PostgreSQL DB** | Local / Azure PostgreSQL | ✅ **CONNECTED & LIVE** | Primary database (`DATABASE_URL=postgresql://postgres:Cherry%40123@localhost:5432/postgres`). Stores `projects`, `p6_activities`, `sap_inventory`, `tc_substations`, `tc_lines`, `chat_sessions`, `chat_messages`, etc. |
| **LLM Provider** | OpenRouter API | ✅ **CONNECTED & LIVE** | Key: `sk-or-v1-...`, Model: `meta-llama/llama-3.3-70b-instruct` on `https://openrouter.ai/api/v1`. |
| **Primavera P6** | Oracle P6 REST API | ✅ **CONNECTED & LIVE** | Authenticated via REST API token (`ORACLE_P6_BASE_URL`). Sync scripts store activities in `p6_activities` table. |
| **SAP Logistics** | Microsoft SharePoint API | ✅ **CONNECTED (via File Sync)** | SAP raw reports (`MB51`, `MB52`, `ME2M`, `ZIBDSESREP`) are downloaded from SharePoint via Graph API (`SHAREPOINT_CLIENT_ID`) and parsed into PostgreSQL `sap_inventory`. |
| **Pulse Quality** | Pulse REST API | ✅ **CONNECTED & LIVE** | Connected via REST endpoints (`/pulse-api/Ncs`, `/pulse-api/Rfis`). |
| **Direct Real-time SAP RFC** | Direct SAP ERP Connection | ⏳ **PENDING / INDIRECT** | Currently synced via SharePoint Excel exports rather than direct SAP RFC calls. |
| **Live GIS Server** | ESRI ArcGIS API | ⏳ **CACHED / LOCAL** | Transmission lines & substation coordinates are stored in Postgres (`tc_lines`, `tc_substations`) and rendered on the frontend using Leaflet/Deck.gl. |

---

## 5. How Data is Fetched (Tool Execution System)

When a user asks a question, the ReAct agent in [`backend/engine/agent.py`](file:///c:/Users/Sree%20Charan/Desktop/Akasha1/Akasha/backend/engine/agent.py) calls specific Python functions registered in `TOOLS`:

### 1. Portfolio Resolver Tool
- `portfolio_resolve_project_id(name)`: Searches the `projects` table using ILIKE matching on project name, SPV name, or P6 name to return the exact `project_id`.

### 2. P6 Schedule Tools ([`engine/tools/p6_tools.py`](file:///c:/Users/Sree%20Charan/Desktop/Akasha1/Akasha/backend/engine/tools/p6_tools.py))
- `p6_get_project_summary(project_id)`: Queries SPI, CPI, variance days, baseline vs actual dates.
- `p6_get_critical_activities(project_id)`: Queries `p6_activities` where `total_float <= 0`.
- `p6_get_delayed_activities(project_id)`: Queries activities where actual/forecast finish is past baseline finish.
- `p6_get_wbs_tree(project_id)`: Returns the hierarchical WBS tree structure.

### 3. SAP Procurement Tools ([`engine/tools/sap_tools.py`](file:///c:/Users/Sree%20Charan/Desktop/Akasha1/Akasha/backend/engine/tools/sap_tools.py))
- `sap_get_po_summary(project_id)`: Queries purchase orders, total ordered, fulfilled, and pending quantities.
- `sap_get_material_gaps(project_id)`: Identifies required vs delivered material discrepancies.
- `sap_get_inventory(project_id)`: Queries current stock levels from `sap_inventory`.

### 4. Transmission Connectivity Tools ([`engine/tools/tc_tools.py`](file:///c:/Users/Sree%20Charan/Desktop/Akasha1/Akasha/backend/engine/tools/tc_tools.py))
- `tc_get_project_lines(project_id)`: Queries transmission lines, substation readiness, line length, and bay status from `tc_lines` and `tc_substations`.
- `tc_get_at_risk_lines(days_threshold)`: Finds all delayed transmission interconnects across the portfolio.

### 5. What-If Simulation Tools ([`engine/tools/simulation_tools.py`](file:///c:/Users/Sree%20Charan/Desktop/Akasha1/Akasha/backend/engine/tools/simulation_tools.py))
- `sim_project_duration_what_if(...)`: Simulates project schedule shifts when key activity durations change.
- `sim_monsoon_impact(...)`: Calculates monsoon weather delay impacts on outdoor civil work.

---

## 6. How Responses are Generated & Streamed

1. **Endpoint Trigger**: The frontend sends a `POST` request to `/api/chat` (in [`routers/ai.py`](file:///c:/Users/Sree%20Charan/Desktop/Akasha1/Akasha/backend/routers/ai.py)).
2. **Streaming Response (`StreamingResponse`)**: FastAPI returns a `text/event-stream` (Server-Sent Events).
3. **Chunk Emission**: As the LLM generates tokens, they are streamed chunk-by-chunk to the UI.
4. **Metadata Event**: At the end of the stream, a JSON metadata chunk is emitted containing:
   ```json
   {
     "type": "metadata",
     "response": {
       "content": "...",
       "intent_type": "factual",
       "project_ids": ["P-102"],
       "domains": ["P6", "SAP"],
       "data_as_of": "2026-07-24",
       "sources_used": ["p6_activities", "sap_inventory"],
       "latency_ms": 1420
     }
   }
   ```
5. **Database Persistence**: The message is saved in PostgreSQL under `chat_messages` linked to `chat_sessions`.

---

## 7. Directory Structure & Key File Map

```
backend/
├── .env                              # Environment variables (OpenRouter key, DB URL, etc.)
├── main.py                           # FastAPI application entry point & router includes
├── run.py                            # Startup script with auto-migration and uvicorn runner
├── database.py                       # SQLAlchemy engine & session factory
├── models.py                         # Database ORM models (Projects, Activities, Messages)
│
├── routers/
│   ├── ai.py                         # Main /api/chat streaming endpoint & LLM dispatchers
│   └── ai_v2_2.py                    # Chatbot v2.2 enhanced API endpoints
│
├── engine/
│   ├── agent.py                      # ReAct agent loop, tool definitions, vision model
│   ├── orchestrator.py               # Fast vs Deep Analysis chat orchestrator
│   ├── orchestrator_v2_2.py          # v2.2 8-step pipeline orchestrator
│   ├── accuracy_engines.py           # 5 accuracy & validation engines
│   ├── intent_v2.py                  # Intent classification module
│   │
│   └── tools/                        # Agent Tool Implementations
│       ├── p6_tools.py               # Primavera schedule tools
│       ├── sap_tools.py              # SAP procurement tools
│       ├── tc_tools.py               # Transmission tools
│       ├── portfolio_tools.py        # Project resolver & notifications
│       └── simulation_tools.py       # What-if schedule simulations
│
└── services/
    ├── ai_service.py                 # LangChain OpenRouter/LLM interface
    ├── p6_service.py                 # Oracle P6 REST API client
    ├── sharepoint_service.py         # SharePoint Graph API SAP file downloader
    └── pulse_service.py              # Pulse Quality API client
```

---

## 8. Developer Guide: How to Work on & Extend the Chatbot

### How to Add a New Tool to the Chatbot
1. **Define the Tool Function**: Add your python query function in `backend/engine/tools/<domain>_tools.py`.
2. **Register the Schema**: In [`backend/engine/agent.py`](file:///c:/Users/Sree%20Charan/Desktop/Akasha1/Akasha/backend/engine/agent.py), add your tool's JSON schema into the `TOOLS` list.
3. **Bind Execution**: In [`backend/engine/agent.py`](file:///c:/Users/Sree%20Charan/Desktop/Akasha1/Akasha/backend/engine/agent.py), add your tool function into the `tool_map` dictionary in `run_deep_analysis_agent` and `run_deep_analysis_agent_stream`.

### How to Change the LLM Model or Provider
To change models, update [`backend/.env`](file:///c:/Users/Sree%20Charan/Desktop/Akasha1/Akasha/backend/.env):
```env
AI_PROVIDER=openrouter
OPENROUTER_API_KEY=sk-or-v1-your-key-here
OPENROUTER_MODEL=meta-llama/llama-3.3-70b-instruct
```
*Supported providers in `AI_PROVIDER`: `openrouter`, `groq`, `azure`, `ollama`.*

---
*Created for the Akasha Engineering Team.*

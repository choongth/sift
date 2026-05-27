# Sift — Personal Research Agent

## Project overview

Sift is an AI-powered research agent that autonomously searches the web, reads PDFs,
and synthesizes findings into structured Markdown reports. The user gives a research
question; Sift plans and executes a multi-step investigation, asking for human
confirmation before any irreversible action.

Built as a portfolio project to demonstrate MCP protocol, agentic AI systems, and
cloud deployment on AWS.

---

## Current status (as of 2026-05-27)

**Feature-complete locally. Next step: deploy to AWS.**

What works end-to-end:
- MCP server (FastAPI + SSE) with web_search, read_pdf, write_report tools
- Two-phase agent: planning → ReAct research loop
- Structured report output (executive_summary, key_findings, detailed_analysis, sources, confidence)
- CLI entrypoint (`python -m agent.main "question"`)
- Chainlit UI (`chainlit run chainlit_app.py --port 8082`) — fully working
- Human-in-the-loop gate with feedback loop (decline → provide feedback → Claude revises)
- S3 report upload after write (presigned download URL shown in UI, forced download)
- All config externalised to `.env` — no hardcoded values anywhere
- Docker + docker-compose ready (not yet deployed)

---

## Architecture

```
User prompt
    │
    ▼
chainlit_app.py  (Chainlit UI — web server on :8082)
    │
    ├── starts agent thread → agent/runner.py
    │        │  typed event queue (agent → UI)
    │        │  confirm queue    (UI → agent, blocking)
    │        │
    │        ├── Phase 1: agent/planner.py
    │        │        Forces plan via tool_choice=submit_plan
    │        │        Returns: {approach, research_questions, search_queries}
    │        │
    │        └── Phase 2: ReAct loop
    │                 │  AnthropicBedrock (BEDROCK_MODEL_ID env var)
    │                 │  parses tool_use blocks, calls MCP tools
    │                 │
    │                 └──► MCP Server (FastAPI + SSE on :8000)
    │                          ├── web_search   (Tavily API)
    │                          ├── read_pdf     (PyMuPDF)
    │                          └── write_report (Markdown + S3 upload)
    │
    └── on EvReportWritten → agent/s3_uploader.py → S3 presigned URL shown in UI
```

---

## Tech stack

| Layer | Technology |
|---|---|
| Language | Python 3.10+ |
| MCP Server | FastAPI + SSE (`mcp==1.9.0` Python SDK) |
| LLM | Claude Sonnet 4.6 via `anthropic[bedrock]` (`BEDROCK_MODEL_ID` env var) |
| Web search | Tavily API (`tavily-python`) |
| PDF parsing | PyMuPDF (`fitz`) |
| HTTP client | `httpx` (agent → MCP server) |
| Streaming | Server-Sent Events (SSE) |
| UI | Chainlit 2.11.1 (`chainlit_app.py`) |
| Report storage | AWS S3 (`agent/s3_uploader.py`) — presigned URLs, forced download |
| Containerisation | Docker + docker-compose (`Dockerfile`, `docker-compose.yml`) |
| Deployment | AWS (not yet deployed) |
| Auth | AWS IAM roles (no hardcoded keys) |

---

## Project structure

```
sift/
├── CLAUDE.md
├── README.md
├── requirements.txt
├── Dockerfile                 # single image; CMD overridden by docker-compose
├── docker-compose.yml         # mcp (:8000) + chainlit (:8082); MCP_SERVER_URL auto-wired
├── .dockerignore
├── chainlit_app.py            # Chainlit UI — chainlit run chainlit_app.py --port 8082
├── .env                       # real secrets — NEVER commit
├── .env.example               # template with all variables documented
├── .gitignore
│
├── server/                    # MCP Server — uvicorn server.main:app --port 8000
│   ├── main.py                # FastAPI app; /sse GET + /messages/ mounted as ASGI (NOT @app.post)
│   ├── schemas.py             # MCP Tool definitions
│   └── tools/
│       ├── web_search.py      # Tavily async wrapper
│       ├── read_pdf.py        # PyMuPDF; PDF_MAX_PAGES + PDF_FETCH_TIMEOUT from env
│       └── write_report.py    # structured Markdown renderer; REPORTS_DIR from env
│
├── agent/
│   ├── main.py                # CLI entrypoint: python -m agent.main "question"
│   ├── loop.py                # CLI ReAct loop (stdout); reads MCP_SERVER_URL/MAX_ITERATIONS lazily
│   ├── runner.py              # UI ReAct loop (typed event queue); reads env lazily inside _run()
│   ├── planner.py             # Phase 1: submit_plan via tool_choice
│   ├── bedrock_client.py      # AnthropicBedrock; BEDROCK_MODEL_ID read lazily in chat()
│   ├── human_gate.py          # CLI confirmation prompt
│   └── s3_uploader.py         # upload_report() → presigned URL; all config lazy from env
│
└── reports/                   # generated Markdown reports
```

---

## Key design decisions

### MCP over direct function calling
Tools are exposed as a proper MCP server so the project demonstrates real MCP protocol
knowledge. The agent connects over HTTP the same way any MCP host (e.g. Claude Desktop) would.

### IMPORTANT: /messages/ must be mounted as ASGI, not a FastAPI route
`SseServerTransport.handle_post_message` is a full ASGI app — it sends its own
`202 Accepted` response. Wrapping it in `@app.post()` causes FastAPI to try sending
a second response → `RuntimeError: Unexpected ASGI message 'http.response.start'`.
Fix: `app.mount("/messages/", app=sse_transport.handle_post_message)`

### AWS Bedrock instead of Anthropic API
Uses `AnthropicBedrock` client. Model ID controlled by `BEDROCK_MODEL_ID` env var
(default: `global.anthropic.claude-sonnet-4-6`). Credentials from environment, never hardcoded.

### Two-phase loop: plan then execute
Phase 1 forces a structured plan via `tool_choice={"type": "tool", "name": "submit_plan"}`.
The plan is injected into the system prompt for Phase 2, giving Claude direction.

### Structured report schema
`write_report` requires 7 fields: filename, title, executive_summary, key_findings,
detailed_analysis, sources, confidence. This guarantees consistent output format.
`max_tokens=8192` is required — 4096 causes truncated tool_use JSON → KeyError.

### on_text callback for dual-mode streaming
`bedrock_client.chat()` accepts `on_text: Callable[[str], None] | None`.
- CLI: `on_text=None` → prints to stdout
- UI: `on_text=lambda t: event_queue.put(EvThinkChunk(t))` → sends to Chainlit

### UI event queue pattern (runner.py)
Two queues bridge the agent thread and Chainlit:
- `event_queue`: agent → UI (plan, iterations, tool calls, results, confirm request)
- `confirm_queue`: UI → agent (bool confirmed, str feedback) — agent blocks on `.get()`
Chainlit drains the queue via `loop.run_in_executor(None, eq.get(timeout=0.5))`.

### Chainlit UI layout
Each ReAct iteration is a `cl.Step(type="run", default_open=True)`.
Tool calls are child `cl.Step(type="tool", parent_id=iter_step.id)` — nested inside the
iteration. This gives the Claude/ChatGPT-style sequential layout.

### S3 report upload (agent/s3_uploader.py)
After write_report succeeds, `upload_report(local_path)` uploads to `S3_BUCKET_NAME/reports/`.
Presigned URL uses `ResponseContentDisposition: attachment` to force download (not display).
`boto3` calls run in `loop.run_in_executor` to avoid blocking the Chainlit event loop.
All config (bucket, expiry) read lazily inside the function — never at module import time.

### All config read lazily — never at module level
`os.environ.get()` calls must be inside functions, not at module top-level. Reason: Chainlit
imports modules before `load_dotenv()` runs. Module-level reads always return the default.

### No LangChain / LangGraph / CrewAI
Deliberate. The ReAct loop, MCP integration, and planning are built from scratch.

---

## Running locally

**Option A — Two terminals:**
```bash
# Terminal 1
uvicorn server.main:app --port 8000

# Terminal 2
chainlit run chainlit_app.py --port 8082
```

**Option B — Docker Compose:**
```bash
docker compose up --build
```
`MCP_SERVER_URL` is automatically set to `http://mcp:8000/sse` inside Docker.

**CLI only:**
```bash
python -m agent.main "Your research question here"
```

---

## Port layout

| Service | Port | Note |
|---|---|---|
| MCP server | 8000 | Chainlit default is also 8000 — must run separately |
| Chainlit UI | 8082 | 8080 is taken by Apache on this machine |

---

## Environment variables (see .env.example for full list)

```bash
# AWS
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=ap-southeast-1

# LLM
BEDROCK_MODEL_ID=global.anthropic.claude-sonnet-4-6

# Tools
TAVILY_API_KEY=...
PDF_MAX_PAGES=20
PDF_FETCH_TIMEOUT=30

# Agent
MAX_ITERATIONS=10
REPORTS_DIR=./reports
MCP_SERVER_URL=http://localhost:8000/sse   # Docker overrides to http://mcp:8000/sse

# S3
S3_BUCKET_NAME=sift-s3-tihuai-2026
S3_PRESIGNED_EXPIRY=3600
```

---

## Known issues / gotchas

- `max_tokens` must be 8192+. At 4096, long write_report calls get truncated mid-JSON → KeyError.
- Chainlit and MCP server both default to port 8000 — always pass `--port 8082` for Chainlit.
- Chainlit 2.x `cl.Action` requires `payload: dict` (required field) — `value` param is gone.
  Use `name` field to identify which action was clicked: `res.get("name") == "write_report"`.
- `write_report` MCP tool returns `"Report written to /abs/path/file.md"` as result text.
  `runner.py` parses the actual path: `result_text.split("Report written to ", 1)[-1].strip()`.
- The CLI loop has no interactive feedback flow after user declines — Chainlit UI handles this.

---

## Resume description (reference)

```
Sift — Personal Research Agent                              2026.05
• Designed and built an AI research agent using Model Context Protocol (MCP),
  exposing web search, PDF parsing, and report generation as MCP-compliant Tools
• Implemented a two-phase ReAct loop: structured planning phase (forced via
  tool_choice) followed by autonomous multi-step research with Claude Sonnet 4.6
  via AWS Bedrock, with streaming output and human-in-the-loop confirmation
• Built MCP server with FastAPI + SSE; structured report output enforced via
  JSON schema (executive summary, key findings, sources, confidence rating)
• Event-driven Chainlit UI: agent runs in background thread, communicates via typed
  event queue; tool calls nested inside iteration steps for Claude-style layout
• Integrated AWS S3 for report persistence: presigned URLs with forced-download
  Content-Disposition header; all credentials from environment, never hardcoded
• Containerised with Docker + docker-compose; fully config-driven via .env
```

---

## Coding conventions

- All async: use `async def` and `await` throughout, no blocking I/O
- Type hints everywhere
- Errors surface as structured messages, never raw tracebacks
- No secrets in code — all config via environment variables, read lazily inside functions
- Each tool file is self-contained and independently testable

# 🔍 Sift — Personal Research Agent

> An AI-powered research agent that autonomously searches the web, reads PDFs, and synthesises findings into structured Markdown reports. Built as a portfolio project demonstrating MCP protocol, agentic AI systems, and cloud deployment on AWS.

<p align="center">
  <!-- Language & Runtime -->
  <img src="https://img.shields.io/badge/Python-3.11-3776AB?style=flat&logo=python&logoColor=white" />
  <!-- AI / LLM -->
  <img src="https://img.shields.io/badge/Claude_Sonnet_4.6-D97706?style=flat&logo=anthropic&logoColor=white" />
  <img src="https://img.shields.io/badge/AWS_Bedrock-FF9900?style=flat&logo=amazonaws&logoColor=white" />
  <!-- MCP / Backend -->
  <img src="https://img.shields.io/badge/MCP_Protocol-6366F1?style=flat&logoColor=white" />
  <img src="https://img.shields.io/badge/FastAPI-009688?style=flat&logo=fastapi&logoColor=white" />
  <!-- UI -->
  <img src="https://img.shields.io/badge/Chainlit-2.11-F472B6?style=flat&logoColor=white" />
  <!-- Tools -->
  <img src="https://img.shields.io/badge/Tavily_Search-0EA5E9?style=flat&logoColor=white" />
  <img src="https://img.shields.io/badge/PyMuPDF-PDF_Parsing-E11D48?style=flat&logoColor=white" />
  <!-- AWS -->
  <img src="https://img.shields.io/badge/AWS_S3-569A31?style=flat&logo=amazons3&logoColor=white" />
  <img src="https://img.shields.io/badge/AWS_EC2-FF9900?style=flat&logo=amazonec2&logoColor=white" />
  <img src="https://img.shields.io/badge/AWS_IAM-DD344C?style=flat&logo=amazonaws&logoColor=white" />
  <!-- Infra -->
  <img src="https://img.shields.io/badge/Docker-2496ED?style=flat&logo=docker&logoColor=white" />
  <img src="https://img.shields.io/badge/Nginx-009639?style=flat&logo=nginx&logoColor=white" />
  <img src="https://img.shields.io/badge/Let's_Encrypt-003A70?style=flat&logo=letsencrypt&logoColor=white" />
</p>

---

## ✨ How it works

1. 💬 **You ask a research question** in the chat UI.
2. 🗺️ **Sift plans** a structured approach — research questions and search queries.
3. ✅ **You approve the plan** before research begins.
4. 🔄 **Sift executes** a multi-step ReAct loop: searches the web, reads PDFs, synthesises findings.
5. 📋 **You approve the final report** before it is saved.
6. ☁️ **Report is saved** locally as Markdown and uploaded to S3 with a presigned download link.

---

## 🏗️ Architecture

```
User prompt
    │
    ▼
chainlit_app.py       (Chainlit UI — :8082)
    │
    ├── agent/runner.py       Phase 1: planner.py  →  structured plan
    │                         Phase 2: ReAct loop  →  MCP tool calls
    │
    └──► server/main.py       (MCP Server — FastAPI + SSE — :8000)
              ├── web_search      Tavily API
              ├── read_pdf        PyMuPDF
              └── write_report    Markdown + S3 upload
```

The agent and UI communicate via two thread-safe queues: an **event queue** (agent → UI) and a **confirm queue** (UI → agent). This keeps the agent logic completely decoupled from the UI framework.

---

## 🛠️ Tech stack

| Layer | Technology |
|---|---|
| 🤖 LLM | Claude Sonnet 4.6 via AWS Bedrock |
| 🔌 MCP Server | FastAPI + SSE (`mcp` Python SDK) |
| 🔄 Agent loop | Custom ReAct — no LangChain/LangGraph |
| 🔍 Web search | Tavily API |
| 📄 PDF parsing | PyMuPDF (fitz) |
| 💬 UI | Chainlit 2.11 |
| ☁️ Report storage | AWS S3 — presigned download URLs |
| 🐳 Containerisation | Docker + Docker Compose |
| 🌐 Reverse proxy | Nginx + Let's Encrypt (HTTPS) |
| 🖥️ Hosting | AWS EC2 (t3.small) with IAM role |
| ✅ Validation | Pydantic + python-dotenv |

---

## 📋 Prerequisites

- Python 3.11+
- AWS account with Bedrock model access (`claude-sonnet-4-6` in your region)
- Tavily API key — [tavily.com](https://tavily.com)
- AWS credentials with S3 write access (optional — reports save locally if unset)

---

## 🚀 Quick start

### Option A — Docker Compose (recommended)

```bash
cp .env.example .env
# Fill in your credentials in .env

docker compose up --build
```

Open [http://localhost:8082](http://localhost:8082).

### Option B — Two terminals

```bash
cp .env.example .env
# Fill in your credentials in .env
pip install -r requirements.txt

# Terminal 1 — MCP server
uvicorn server.main:app --port 8000

# Terminal 2 — Chainlit UI
chainlit run chainlit_app.py --port 8082
```

### Option C — CLI only

```bash
python -m agent.main "What are the key differences between Kafka and RabbitMQ?"
```

---

## ⚙️ Environment variables

Copy `.env.example` to `.env` and fill in your values:

```bash
# AWS (use IAM role in production)
AWS_ACCESS_KEY_ID=...
AWS_SECRET_ACCESS_KEY=...
AWS_DEFAULT_REGION=ap-southeast-1

# LLM
BEDROCK_MODEL_ID=global.anthropic.claude-sonnet-4-6

# Tools
TAVILY_API_KEY=...

# Agent
MAX_ITERATIONS=10
REPORTS_DIR=./reports
MCP_SERVER_URL=http://localhost:8000/sse   # overridden automatically in Docker

# PDF limits
PDF_MAX_PAGES=20
PDF_FETCH_TIMEOUT=30

# S3 (optional — skip to save reports locally only)
S3_BUCKET_NAME=your-bucket-name
S3_PRESIGNED_EXPIRY=3600
```

---

## 📁 Project structure

```
sift/
├── chainlit_app.py       Chainlit UI
├── chainlit.md           UI welcome screen
├── server/               MCP server (FastAPI + SSE, port 8000)
│   ├── main.py
│   ├── schemas.py
│   └── tools/
│       ├── web_search.py
│       ├── read_pdf.py
│       └── write_report.py
├── agent/                Agent logic
│   ├── main.py           CLI entrypoint
│   ├── runner.py         UI ReAct loop (event queue)
│   ├── loop.py           CLI ReAct loop
│   ├── planner.py        Phase 1: structured plan
│   ├── bedrock_client.py AnthropicBedrock wrapper
│   ├── human_gate.py     CLI confirmation prompt
│   └── s3_uploader.py    S3 upload + presigned URL
├── reports/              Generated Markdown reports (git-ignored)
├── Dockerfile
└── docker-compose.yml
```

---

## 💡 Key design decisions

**🔌 MCP over direct function calling** — Tools are exposed as a proper MCP server so the project demonstrates real protocol knowledge. The agent connects over HTTP the same way any MCP host (e.g. Claude Desktop) would.

**🗺️ Two-phase loop** — Phase 1 forces a structured plan via `tool_choice`. The plan is injected into the system prompt for Phase 2, giving Claude direction before it starts searching.

**🔧 No LangChain / LangGraph / CrewAI** — The ReAct loop, MCP integration, and planning are all built from scratch. The goal is to understand and demonstrate the underlying mechanics.

**🙋 Human-in-the-loop** — The agent pauses for approval before starting research (plan review) and again before saving the report. Feedback from a declined plan is fed back into the next attempt.

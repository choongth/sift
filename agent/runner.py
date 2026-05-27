"""
Event-based agent runner for the Chainlit UI.

Every meaningful action is sent as a typed event to `event_queue`.
The human gate is handled via `confirm_queue`:
  - agent puts EvConfirmReport, then blocks on confirm_queue.get()
  - UI puts (confirmed: bool, feedback: str) into confirm_queue
"""

import asyncio
import os
from dataclasses import dataclass, field
from queue import Queue

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.types import Tool as MCPTool

from agent.bedrock_client import chat
from agent.planner import PLAN_SYSTEM, SUBMIT_PLAN_TOOL, plan_to_context

SYSTEM_PROMPT = """\
You are Sift, an AI research agent. Your job is to answer the user's research \
question thoroughly and accurately.

You have access to three tools:
- web_search: search the web for current information
- read_pdf: extract text from a PDF (local file path or public URL)
- write_report: write your final findings as a structured Markdown report

Research process:
1. Follow your research plan — answer every sub-question
2. Follow up on promising sources; read PDFs when relevant
3. Synthesise findings across all sources with inline URL citations
4. Write the final report only when all sub-questions are answered

Be thorough. Use multiple searches before concluding."""


# ── Events ─────────────────────────────────────────────────────────────────

@dataclass
class EvPlan:
    plan: dict

@dataclass
class EvIterStart:
    n: int
    total: int

@dataclass
class EvThinkChunk:
    text: str

@dataclass
class EvToolCall:
    name: str
    summary: str

@dataclass
class EvToolResult:
    name: str
    text: str
    is_error: bool = False

@dataclass
class EvConfirmReport:
    title: str
    filename: str
    executive_summary: str
    key_findings: list[str]
    confidence: str
    full_input: dict = field(default_factory=dict)

@dataclass
class EvReportWritten:
    path: str

@dataclass
class EvDone:
    pass

@dataclass
class EvError:
    message: str


# ── Thread entry point ──────────────────────────────────────────────────────

def run_agent(question: str, event_queue: Queue, confirm_queue: Queue) -> None:
    asyncio.run(_run(question, event_queue, confirm_queue))


# ── Helpers ─────────────────────────────────────────────────────────────────

def _to_anthropic_tools(mcp_tools: list[MCPTool]) -> list[dict]:
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.inputSchema,
        }
        for t in mcp_tools
    ]


def _tool_summary(block) -> str:
    if block.name == "web_search":
        return f'query="{block.input.get("query", "")}"'
    if block.name == "read_pdf":
        return f'source="{block.input.get("source", "")}"'
    return f'title="{block.input.get("title", "")}"'


# ── Async runner ─────────────────────────────────────────────────────────────

async def _run(question: str, eq: Queue, cq: Queue) -> None:
    mcp_server_url = os.environ.get("MCP_SERVER_URL", "http://localhost:8000/sse")
    max_iterations = int(os.environ.get("MAX_ITERATIONS", "10"))

    def emit(event):
        eq.put(event)

    def on_text(chunk: str):
        emit(EvThinkChunk(text=chunk))

    # ── Phase 1: Planning ────────────────────────────────────────────────
    try:
        message = await chat(
            messages=[{"role": "user", "content": question}],
            tools=[SUBMIT_PLAN_TOOL],
            system=PLAN_SYSTEM,
            tool_choice={"type": "tool", "name": "submit_plan"},
            on_text=on_text,
        )
        plan = next(
            (b.input for b in message.content
             if b.type == "tool_use" and b.name == "submit_plan"),
            {"approach": "", "research_questions": [], "search_queries": []},
        )
        emit(EvPlan(plan=plan))
    except Exception as e:
        emit(EvError(message=f"Planning failed: {type(e).__name__}: {e}"))
        return

    system_with_plan = SYSTEM_PROMPT + "\n\n" + plan_to_context(plan)

    # ── Phase 2: ReAct loop ──────────────────────────────────────────────
    try:
        async with sse_client(mcp_server_url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                tools = _to_anthropic_tools((await session.list_tools()).tools)
                messages: list[dict] = [{"role": "user", "content": question}]

                for iteration in range(1, max_iterations + 1):
                    emit(EvIterStart(n=iteration, total=max_iterations))

                    message = await chat(
                        messages=messages,
                        tools=tools,
                        system=system_with_plan,
                        on_text=on_text,
                    )
                    messages.append({"role": "assistant", "content": message.content})

                    if message.stop_reason == "max_tokens":
                        messages.append({
                            "role": "user",
                            "content": "Response truncated. Retry with a more concise detailed_analysis.",
                        })
                        continue

                    tool_blocks = [b for b in message.content if b.type == "tool_use"]
                    if not tool_blocks:
                        emit(EvDone())
                        return

                    tool_results = []
                    for block in tool_blocks:
                        emit(EvToolCall(name=block.name, summary=_tool_summary(block)))

                        if block.name == "write_report":
                            emit(EvConfirmReport(
                                title=block.input.get("title", ""),
                                filename=block.input.get("filename", ""),
                                executive_summary=block.input.get("executive_summary", ""),
                                key_findings=block.input.get("key_findings", []),
                                confidence=block.input.get("confidence", "medium"),
                                full_input=block.input,
                            ))
                            confirmed, feedback = cq.get()  # blocks until UI responds

                            if not confirmed:
                                tool_results.append({
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": (
                                        f"User declined the report and requested changes: {feedback}. "
                                        "Please revise and call write_report again."
                                    ),
                                })
                                continue

                        mcp_result = await session.call_tool(block.name, block.input)
                        result_text = "\n".join(
                            c.text for c in mcp_result.content if hasattr(c, "text")
                        )

                        if block.name == "write_report" and not mcp_result.isError:
                            # result_text is "Report written to /abs/path/file.md"
                            actual_path = result_text.split("Report written to ", 1)[-1].strip()
                            emit(EvReportWritten(path=actual_path))

                        emit(EvToolResult(
                            name=block.name,
                            text=result_text,
                            is_error=bool(mcp_result.isError),
                        ))

                        tool_results.append({
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "is_error": mcp_result.isError,
                            "content": result_text,
                        })

                    messages.append({"role": "user", "content": tool_results})

                emit(EvDone())

    except Exception as e:
        emit(EvError(message=f"{type(e).__name__}: {e}"))

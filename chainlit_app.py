import asyncio
import os
import threading
from pathlib import Path
from queue import Empty, Queue

import chainlit as cl
from dotenv import load_dotenv

from agent.s3_uploader import upload_report
from agent.runner import (
    EvConfirmReport,
    EvDone,
    EvError,
    EvIterStart,
    EvPlan,
    EvReportWritten,
    EvThinkChunk,
    EvToolCall,
    EvToolResult,
    run_agent,
)

load_dotenv()

TOOL_ICONS = {"web_search": "🔍", "read_pdf": "📄", "write_report": "📝"}


@cl.on_chat_start
async def on_chat_start():
    await cl.Message(
        content="Welcome to **Sift**! Enter a research question and I'll search the web, read sources, and write a structured report."
    ).send()


@cl.on_message
async def on_message(message: cl.Message):
    question = message.content.strip()
    if not question:
        return

    eq: Queue = Queue()
    cq: Queue = Queue()
    agent_thread = threading.Thread(target=run_agent, args=(question, eq, cq), daemon=True)
    agent_thread.start()

    await _run_ui(eq, cq, agent_thread)


# ── Event loop ────────────────────────────────────────────────────────────────

async def _run_ui(eq: Queue, cq: Queue, agent_thread: threading.Thread) -> None:
    loop = asyncio.get_event_loop()
    iter_step: cl.Step | None = None   # one per ReAct iteration, tool steps nest inside
    active_step: cl.Step | None = None  # the currently-running tool step

    while True:
        try:
            event = await loop.run_in_executor(None, lambda: eq.get(timeout=0.5))
        except Empty:
            if not agent_thread.is_alive():
                await cl.Message(
                    content="Agent stopped unexpectedly. Make sure the MCP server is running (`uvicorn server.main:app --port 8000`)."
                ).send()
                return
            continue

        if isinstance(event, EvPlan):
            await _send_plan(event.plan)

        elif isinstance(event, EvIterStart):
            # Finalise previous iteration before opening a new one
            if iter_step:
                await iter_step.update()
            iter_step = cl.Step(
                name=f"Iteration {event.n} / {event.total}",
                type="run",
                default_open=True,
            )
            await iter_step.send()

        elif isinstance(event, EvThinkChunk):
            if iter_step:
                await iter_step.stream_token(event.text)

        elif isinstance(event, EvToolCall):
            icon = TOOL_ICONS.get(event.name, "🔧")
            active_step = cl.Step(
                name=f"{icon} {event.name}",
                type="tool",
                parent_id=iter_step.id if iter_step else None,
            )
            active_step.input = event.summary
            await active_step.send()

        elif isinstance(event, EvToolResult):
            if active_step:
                preview = event.text[:2000] + ("…" if len(event.text) > 2000 else "")
                active_step.output = preview
                if event.is_error:
                    active_step.is_error = True
                await active_step.update()
                active_step = None

        elif isinstance(event, EvConfirmReport):
            # Close current iteration before the human gate so the UI is clean
            if iter_step:
                await iter_step.update()
                iter_step = None
            await _handle_confirm(event, cq)

        elif isinstance(event, EvReportWritten):
            await _show_report(event.path)

        elif isinstance(event, EvDone):
            if iter_step:
                await iter_step.update()
            await cl.Message(
                content="Research complete! Start a new message to research another topic."
            ).send()
            return

        elif isinstance(event, EvError):
            if iter_step:
                await iter_step.update()
            await cl.Message(content=f"Error: {event.message}").send()
            return


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _send_plan(plan: dict) -> None:
    lines: list[str] = [f"**Approach:** {plan.get('approach', '')}"]
    rqs = plan.get("research_questions", [])
    sqs = plan.get("search_queries", [])
    if rqs:
        lines.append("\n**Sub-questions:**")
        for i, q in enumerate(rqs, 1):
            lines.append(f"{i}. {q}")
    if sqs:
        lines.append("\n**Search queries:**")
        for q in sqs:
            lines.append(f"- `{q}`")
    await cl.Message(content="\n".join(lines), author="Research Plan").send()


async def _handle_confirm(event: EvConfirmReport, cq: Queue) -> None:
    content = (
        f"## {event.title}\n\n"
        f"**File:** `{event.filename}` · **Confidence:** {event.confidence}\n\n"
        f"### Executive Summary\n\n{event.executive_summary}\n\n"
        f"### Key Findings\n\n"
        + "\n".join(f"- {f}" for f in event.key_findings)
    )

    res = await cl.AskActionMessage(
        content=content,
        actions=[
            cl.Action(name="write_report", payload={}, label="Write Report"),
            cl.Action(name="request_changes", payload={}, label="Request Changes"),
        ],
        timeout=300,
    ).send()

    if res is None or res.get("name") == "write_report":
        cq.put((True, ""))
        await cl.Message(content="Writing report…").send()
        return

    feedback_res = await cl.AskUserMessage(
        content="What changes would you like? (e.g. Add more detail on X, shorten section Y, include sources about Z…)",
        timeout=300,
    ).send()
    feedback = (feedback_res.get("output", "") if feedback_res else "").strip()
    cq.put((False, feedback or "Please revise the report."))


async def _show_report(local_path: str) -> None:
    filename = Path(local_path).name
    report_md = Path(local_path).read_text(encoding="utf-8")

    s3_bucket = os.environ.get("S3_BUCKET_NAME", "")
    if s3_bucket:
        try:
            presigned_url = await upload_report(local_path)
            await cl.Message(
                content=f"[Download `{filename}` from S3]({presigned_url}) *(link valid 1 hour)*"
            ).send()
        except Exception as e:
            await cl.Message(
                content=f"Report saved to `{local_path}` (S3 upload failed: {e})"
            ).send()
    else:
        await cl.Message(content=f"Report saved to `{local_path}`").send()

    await cl.Message(content=report_md).send()

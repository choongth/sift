import os

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.types import Tool as MCPTool

from agent.bedrock_client import chat
from agent.human_gate import confirm_write_report
from agent.planner import display_plan, plan_research, plan_to_context

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


def _to_anthropic_tools(mcp_tools: list[MCPTool]) -> list[dict]:
    return [
        {
            "name": t.name,
            "description": t.description,
            "input_schema": t.inputSchema,
        }
        for t in mcp_tools
    ]


async def run(research_question: str) -> None:
    mcp_server_url = os.environ.get("MCP_SERVER_URL", "http://localhost:8000/sse")
    max_iterations = int(os.environ.get("MAX_ITERATIONS", "10"))

    # ── Phase 1: Planning ────────────────────────────────────────
    plan = await plan_research(research_question)
    display_plan(plan)

    plan_context = plan_to_context(plan)
    system_with_plan = SYSTEM_PROMPT + "\n\n" + plan_context

    # ── Phase 2: Execute ReAct loop ──────────────────────────────
    try:
        async with sse_client(mcp_server_url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()

                tools_list = await session.list_tools()
                tools = _to_anthropic_tools(tools_list.tools)

                messages: list[dict] = [{"role": "user", "content": research_question}]

                for iteration in range(1, max_iterations + 1):
                    print(f"\n{'─' * 60}")
                    print(f"  Iteration {iteration} / {max_iterations}")
                    print(f"{'─' * 60}\n")

                    message = await chat(
                        messages=messages,
                        tools=tools,
                        system=system_with_plan,
                    )

                    messages.append({"role": "assistant", "content": message.content})

                    # Truncated response — ask Claude to be more concise and retry
                    if message.stop_reason == "max_tokens":
                        print("\n[Sift] Response truncated. Asking Claude to be more concise.")
                        messages.append({
                            "role": "user",
                            "content": (
                                "Your response was truncated because it was too long. "
                                "Please retry with a more concise detailed_analysis — "
                                "aim for quality over length."
                            ),
                        })
                        continue

                    tool_blocks = [b for b in message.content if b.type == "tool_use"]

                    if not tool_blocks:
                        print("\n[Sift] Research complete.")
                        return

                    tool_results = []
                    for block in tool_blocks:
                        _print_tool_call(block)

                        if block.name == "write_report":
                            confirmed = await confirm_write_report(
                                title=block.input.get("title", ""),
                                filename=block.input.get("filename", ""),
                                executive_summary=block.input.get("executive_summary", ""),
                                key_findings=block.input.get("key_findings", []),
                                confidence=block.input.get("confidence", "medium"),
                            )
                            if not confirmed:
                                tool_results.append({
                                    "type": "tool_result",
                                    "tool_use_id": block.id,
                                    "content": (
                                        "User declined the report. Ask what changes "
                                        "they would like before trying again."
                                    ),
                                })
                                continue

                        mcp_result = await session.call_tool(block.name, block.input)

                        result_text = "\n".join(
                            c.text for c in mcp_result.content if hasattr(c, "text")
                        )

                        if mcp_result.isError:
                            print(f"  ↳ [ERROR] {result_text}")
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "is_error": True,
                                "content": f"Tool error: {result_text}. Check that all required fields are present and valid.",
                            })
                        else:
                            print(f"  ↳ {result_text[:250]}{'...' if len(result_text) > 250 else ''}")
                            tool_results.append({
                                "type": "tool_result",
                                "tool_use_id": block.id,
                                "content": result_text,
                            })

                    messages.append({"role": "user", "content": tool_results})

                print(f"\n[Sift] Reached max iterations ({max_iterations}).")

    except Exception as e:
        print(f"\n[Sift] Failed to connect to MCP server at {mcp_server_url}")
        print(f"  Make sure it is running: uvicorn server.main:app --port 8000")
        print(f"  Error: {type(e).__name__}: {e}")


def _print_tool_call(block) -> None:
    if block.name == "web_search":
        print(f"\n[Tool → web_search] query=\"{block.input.get('query', '')}\"")
    elif block.name == "read_pdf":
        print(f"\n[Tool → read_pdf] source=\"{block.input.get('source', '')}\"")
    elif block.name == "write_report":
        print(f"\n[Tool → write_report] title=\"{block.input.get('title', '')}\"")
    else:
        print(f"\n[Tool → {block.name}] {block.input}")

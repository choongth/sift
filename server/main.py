import json

from dotenv import load_dotenv
from fastapi import FastAPI
from starlette.requests import Request
from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import TextContent

from server.schemas import ALL_TOOLS
from server.tools.read_pdf import read_pdf
from server.tools.web_search import web_search
from server.tools.write_report import write_report

load_dotenv()

app = FastAPI(title="Sift MCP Server")
mcp_server = Server("sift")
sse_transport = SseServerTransport("/messages/")


@mcp_server.list_tools()
async def list_tools():
    return ALL_TOOLS


@mcp_server.call_tool()
async def call_tool(name: str, arguments: dict):
    if name == "web_search":
        results = await web_search(
            query=arguments["query"],
            max_results=arguments.get("max_results", 5),
        )
        return [TextContent(type="text", text=json.dumps(results, indent=2))]

    if name == "read_pdf":
        text = await read_pdf(
            source=arguments["source"],
            max_pages=arguments.get("max_pages", 20),
        )
        return [TextContent(type="text", text=text)]

    if name == "write_report":
        message = await write_report(
            filename=arguments["filename"],
            title=arguments["title"],
            executive_summary=arguments["executive_summary"],
            key_findings=arguments["key_findings"],
            detailed_analysis=arguments["detailed_analysis"],
            sources=arguments["sources"],
            confidence=arguments["confidence"],
        )
        return [TextContent(type="text", text=message)]

    raise ValueError(f"Unknown tool: {name}")


@app.get("/sse")
async def sse_endpoint(request: Request):
    async with sse_transport.connect_sse(
        request.scope, request.receive, request._send
    ) as streams:
        await mcp_server.run(
            streams[0],
            streams[1],
            mcp_server.create_initialization_options(),
        )


# Mounted as a raw ASGI app — handle_post_message sends its own 202 response
# internally, so it must NOT be wrapped in a FastAPI route handler (which would
# try to send a second response and crash with "response already completed").
app.mount("/messages/", app=sse_transport.handle_post_message)

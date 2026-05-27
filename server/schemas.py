from mcp.types import Tool

WEB_SEARCH = Tool(
    name="web_search",
    description=(
        "Search the web for up-to-date information on a topic. "
        "Returns a list of relevant results with titles, URLs, and snippets."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query string.",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results to return (default 5).",
                "default": 5,
            },
        },
        "required": ["query"],
    },
)

READ_PDF = Tool(
    name="read_pdf",
    description=(
        "Extract and return the text content of a PDF file. "
        "Provide either a local file path or a public URL."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "source": {
                "type": "string",
                "description": "Local file path or public URL of the PDF.",
            },
            "max_pages": {
                "type": "integer",
                "description": "Maximum number of pages to extract (default 20).",
                "default": 20,
            },
        },
        "required": ["source"],
    },
)

WRITE_REPORT = Tool(
    name="write_report",
    description=(
        "Write the final research report to a Markdown file. "
        "Call this only when you have finished all research. "
        "Requires human confirmation before writing."
    ),
    inputSchema={
        "type": "object",
        "properties": {
            "filename": {
                "type": "string",
                "description": "Output filename (e.g. 'quantum_computing.md'). No path prefix.",
            },
            "title": {
                "type": "string",
                "description": "Report title shown as the top-level heading.",
            },
            "executive_summary": {
                "type": "string",
                "description": "2-3 sentence summary of the most important findings.",
            },
            "key_findings": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Bullet-point findings, each a single complete sentence.",
            },
            "detailed_analysis": {
                "type": "string",
                "description": (
                    "Full Markdown body with ## section headers and inline URL citations. "
                    "This is the main body of the report."
                ),
            },
            "sources": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of all source URLs cited in the report.",
            },
            "confidence": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "description": "Confidence level in the findings based on source quality and agreement.",
            },
        },
        "required": [
            "filename", "title", "executive_summary",
            "key_findings", "detailed_analysis", "sources", "confidence",
        ],
    },
)

ALL_TOOLS: list[Tool] = [WEB_SEARCH, READ_PDF, WRITE_REPORT]

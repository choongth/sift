from typing import Callable

from agent.bedrock_client import chat

SUBMIT_PLAN_TOOL = {
    "name": "submit_plan",
    "description": "Submit your structured research plan before beginning research.",
    "input_schema": {
        "type": "object",
        "properties": {
            "approach": {
                "type": "string",
                "description": "One sentence describing your overall research strategy.",
            },
            "research_questions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Specific sub-questions that must be answered to address the topic.",
            },
            "search_queries": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Initial web search queries to execute, one per sub-question.",
            },
        },
        "required": ["approach", "research_questions", "search_queries"],
    },
}

PLAN_SYSTEM = """\
You are a research planning assistant. Given a research question, produce a structured
plan: identify the key sub-questions that must be answered, and write one focused web
search query per sub-question. Be specific — vague queries return vague results.
Do not begin researching yet. Only submit the plan."""


async def plan_research(
    question: str,
    on_text: Callable[[str], None] | None = None,
) -> dict:
    """
    Phase 1: ask Claude to produce a research plan.
    Forces the model to call submit_plan via tool_choice.
    Returns the plan dict: {approach, research_questions, search_queries}.
    """
    if not on_text:
        print("\n[Sift] Planning research...\n")

    message = await chat(
        messages=[{"role": "user", "content": question}],
        tools=[SUBMIT_PLAN_TOOL],
        system=PLAN_SYSTEM,
        tool_choice={"type": "tool", "name": "submit_plan"},
        on_text=on_text,
    )

    for block in message.content:
        if block.type == "tool_use" and block.name == "submit_plan":
            return block.input

    return {"approach": "", "research_questions": [], "search_queries": []}


def display_plan(plan: dict) -> None:
    print("\n" + "━" * 60)
    print("  RESEARCH PLAN")
    print("━" * 60)
    print(f"  Approach: {plan.get('approach', '')}")
    print("\n  Sub-questions:")
    for i, q in enumerate(plan.get("research_questions", []), 1):
        print(f"    {i}. {q}")
    print("\n  Initial search queries:")
    for q in plan.get("search_queries", []):
        print(f"    → \"{q}\"")
    print("━" * 60 + "\n")


def plan_to_context(plan: dict) -> str:
    questions = "\n".join(
        f"{i}. {q}" for i, q in enumerate(plan.get("research_questions", []), 1)
    )
    queries = "\n".join(f'- "{q}"' for q in plan.get("search_queries", []))
    return (
        f"You have already created a research plan:\n\n"
        f"Approach: {plan.get('approach', '')}\n\n"
        f"Sub-questions to answer:\n{questions}\n\n"
        f"Start with these search queries:\n{queries}\n\n"
        f"Execute this plan thoroughly. Cover every sub-question."
    )

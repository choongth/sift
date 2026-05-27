import os
from typing import Any, Callable

import anthropic
from anthropic import AnthropicBedrock

_client: AnthropicBedrock | None = None


def get_client() -> AnthropicBedrock:
    global _client
    if _client is None:
        _client = AnthropicBedrock(
            aws_region=os.environ.get("AWS_DEFAULT_REGION", "ap-southeast-1"),
        )
    return _client


async def chat(
    messages: list[dict],
    tools: list[dict],
    system: str = "",
    max_tokens: int = 8192,
    tool_choice: dict[str, Any] | None = None,
    on_text: Callable[[str], None] | None = None,
) -> anthropic.types.Message:
    client = get_client()
    model_id = os.environ.get("BEDROCK_MODEL_ID", "global.anthropic.claude-sonnet-4-6")

    kwargs: dict[str, Any] = dict(
        model=model_id,
        max_tokens=max_tokens,
        system=system,
        messages=messages,
        tools=tools,
    )
    if tool_choice is not None:
        kwargs["tool_choice"] = tool_choice

    with client.messages.stream(**kwargs) as stream:
        for text in stream.text_stream:
            if on_text:
                on_text(text)
            else:
                print(text, end="", flush=True)

        message = stream.get_final_message()

    if not on_text and any(block.type == "tool_use" for block in message.content):
        print()

    return message

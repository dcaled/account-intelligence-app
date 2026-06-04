import os
from collections.abc import Generator

import anthropic
from dotenv import load_dotenv

load_dotenv()

MODEL = "claude-haiku-4-5"
MAX_TOKENS = 1024


def stream_brief(system_prompt: str, user_message: str) -> Generator[str, None, None]:
    """Stream a meeting brief from Claude, yielding text chunks as they arrive."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    with client.messages.stream(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    ) as stream:
        for text in stream.text_stream:
            yield text

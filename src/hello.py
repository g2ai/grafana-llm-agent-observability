"""Steps 2.1-2.2: one Anthropic call, recorded as a generation in Grafana Agent
Observability, plus OTel traces and metrics sent to the Grafana Cloud OTLP gateway.

Run from the repo root with the venv active:
    python src/hello.py
"""

import logging
import os
import uuid

from dotenv import load_dotenv

# Load .env before importing the SDKs, because both read their settings from env vars.
load_dotenv()

import anthropic  # noqa: E402
from agento11y import Client  # noqa: E402
from agento11y_anthropic import AnthropicOptions, messages  # noqa: E402
from telemetry import setup_otel  # noqa: E402

# Show SDK warnings. Export failures are logged, not raised, so without this they are silent.
logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")


def main() -> None:
    otel_shutdown = setup_otel()  # must run before Client(), or spans and metrics are dropped
    o11y = Client()  # reads AGENTO11Y_* env vars
    llm = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY

    conversation_id = f"hello-{uuid.uuid4().hex[:8]}"
    request = {
        "model": MODEL,
        "max_tokens": 100,  # hard cap on output tokens, keeps cost tiny
        "messages": [{"role": "user", "content": "In one sentence, what does an SRE do?"}],
    }

    try:
        # The wrapper starts a generation record, calls our function, then records
        # the request, response, tokens and latency for export.
        response = messages.create(
            o11y,
            request,
            lambda req: llm.messages.create(**req),
            AnthropicOptions(
                conversation_id=conversation_id,
                agent_name="sre-triage-agent",
                agent_version="0.1.0",
            ),
        )
        print("Reply:          ", response.content[0].text)
        print("Tokens in/out:  ", response.usage.input_tokens, "/", response.usage.output_tokens)
        print("Conversation ID:", conversation_id)
    finally:
        # Exports are async and batched. shutdown() flushes the queue;
        # skip it and a short script can exit before anything is sent.
        o11y.shutdown()
        otel_shutdown()  # then flush traces and metrics
        print("Done. Any export problem shows above as a WARNING line.")


if __name__ == "__main__":
    main()

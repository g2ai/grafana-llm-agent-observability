"""SRE triage agent: Claude + mock tools, observed with Grafana Agent Observability.

Run from the repo root with the venv active:
    python src/agent.py "What is firing right now and what should I do first?"

Each LLM call is one generation. Each tool call is one execute_tool span.
One parent span (invoke_agent) groups the whole run in the trace view.
"""

import json
import logging
import os
import sys
import uuid

from dotenv import load_dotenv

load_dotenv()

import anthropic  # noqa: E402
from agento11y import (  # noqa: E402
    Client,
    ClientConfig,
    ContentCaptureMode,
    ToolExecutionStart,
)
from agento11y_anthropic import AnthropicOptions, messages  # noqa: E402
from opentelemetry import trace  # noqa: E402

from telemetry import setup_otel  # noqa: E402
from tools import TOOL_SCHEMAS, ToolFailure, run_tool  # noqa: E402

logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")

MODEL = os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001")
AGENT_NAME = "sre-triage-agent"
AGENT_VERSION = "0.3.0"
MAX_STEPS = 5  # max LLM calls per run, stops runaway tool loops

SYSTEM_PROMPT = (
    "You are an SRE triage assistant. Use the tools to look up alerts, metrics and runbooks "
    "before answering. Before you name a likely cause, call query_metrics for the service with "
    "the most severe alert and check its recent deploys. Only state facts that appear in tool "
    "results, and cite alert IDs and runbook IDs. Do not link alerts to each other unless a tool "
    "result shows the link. If the tools do not give you enough information, say so. "
    "Answer in under 120 words with three parts: Summary, Likely cause, Next steps."
)


class TriageAgent:
    def __init__(self) -> None:
        self.otel_shutdown = setup_otel()  # before Client(), or spans and metrics are dropped
        # FULL capture: tool arguments and results also go on tool spans.
        # Safe here because all data is synthetic.
        self.o11y = Client(ClientConfig(content_capture=ContentCaptureMode.FULL))
        self.llm = anthropic.Anthropic()
        self.tracer = trace.get_tracer(AGENT_NAME)

    def run(
        self,
        question: str,
        *,
        conversation_id: str | None = None,
        system_prompt: str = SYSTEM_PROMPT,
        use_tools: bool = True,
        fail_tool: str | None = None,
        max_tokens: int = 400,
        tags: dict[str, str] | None = None,
    ) -> str:
        """Runs one agent turn. The keyword options exist so demo scenarios can force failures."""
        conversation_id = conversation_id or f"triage-{uuid.uuid4().hex[:8]}"
        options = AnthropicOptions(
            conversation_id=conversation_id,
            agent_name=AGENT_NAME,
            agent_version=AGENT_VERSION,
            tags=tags or {},
        )
        history: list[dict] = [{"role": "user", "content": question}]

        with self.tracer.start_as_current_span(f"invoke_agent {AGENT_NAME}") as span:
            span.set_attribute("gen_ai.operation.name", "invoke_agent")
            span.set_attribute("gen_ai.agent.name", AGENT_NAME)
            span.set_attribute("gen_ai.conversation.id", conversation_id)

            for _ in range(MAX_STEPS):
                request = {
                    "model": MODEL,
                    "max_tokens": max_tokens,
                    "system": system_prompt,
                    "messages": history,
                }
                if use_tools:
                    request["tools"] = TOOL_SCHEMAS

                response = messages.create(
                    self.o11y, request, lambda req: self.llm.messages.create(**req), options
                )
                history.append({"role": "assistant", "content": [b.model_dump() for b in response.content]})

                if response.stop_reason != "tool_use":
                    return "".join(b.text for b in response.content if b.type == "text")

                history.append({"role": "user", "content": self._run_tools(response, conversation_id, fail_tool)})

            return "Stopped: reached the step limit without a final answer."

    def _run_tools(self, response, conversation_id: str, fail_tool: str | None) -> list[dict]:
        results = []
        for block in response.content:
            if block.type != "tool_use":
                continue
            start = ToolExecutionStart(
                tool_name=block.name,
                tool_call_id=block.id,
                tool_type="function",
                include_content=True,
                conversation_id=conversation_id,
                agent_name=AGENT_NAME,
                agent_version=AGENT_VERSION,
                request_model=MODEL,
                request_provider="anthropic",
            )
            with self.o11y.start_tool_execution(start) as rec:
                try:
                    output = run_tool(block.name, block.input, fail_tool=fail_tool)
                    rec.set_result(arguments=block.input, result=output)
                    results.append({"type": "tool_result", "tool_use_id": block.id, "content": json.dumps(output)})
                except ToolFailure as exc:
                    # Record the error on the tool span, then tell the model the tool failed.
                    rec.set_exec_error(exc)
                    rec.set_result(arguments=block.input, result={"error": str(exc)})
                    results.append(
                        {"type": "tool_result", "tool_use_id": block.id, "content": str(exc), "is_error": True}
                    )
        return results

    def close(self) -> None:
        # Order matters: flush generations first, then traces and metrics.
        self.o11y.shutdown()
        self.otel_shutdown()


def main() -> None:
    question = " ".join(sys.argv[1:]) or "What is firing right now and what should I do first?"
    agent = TriageAgent()
    try:
        answer = agent.run(question)
        print(answer)
    finally:
        agent.close()


if __name__ == "__main__":
    main()

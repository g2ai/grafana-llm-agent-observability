"""Mock SRE tools backed by synthetic JSON in src/data. No real systems are called."""

import json
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"


def _load(name: str):
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


class ToolFailure(RuntimeError):
    """Raised when a tool is forced to fail (demo scenario 5)."""


# Tool definitions in the Anthropic Messages API format.
TOOL_SCHEMAS = [
    {
        "name": "list_active_alerts",
        "description": "List currently firing alerts. Optionally filter by service name.",
        "input_schema": {
            "type": "object",
            "properties": {"service": {"type": "string", "description": "Service name, e.g. checkout-api"}},
        },
    },
    {
        "name": "get_runbook",
        "description": "Get the runbook steps for a runbook ID such as RB-ERR-5XX.",
        "input_schema": {
            "type": "object",
            "properties": {"runbook_id": {"type": "string"}},
            "required": ["runbook_id"],
        },
    },
    {
        "name": "query_metrics",
        "description": "Get the last 30 minutes of metrics and recent deploys for a service.",
        "input_schema": {
            "type": "object",
            "properties": {"service": {"type": "string"}},
            "required": ["service"],
        },
    },
]


def list_active_alerts(service: str | None = None) -> list[dict]:
    alerts = _load("alerts.json")
    if service:
        alerts = [a for a in alerts if a["service"] == service]
    return alerts


def get_runbook(runbook_id: str) -> dict:
    runbooks = _load("runbooks.json")
    if runbook_id not in runbooks:
        return {"error": f"runbook {runbook_id} not found"}
    return {"id": runbook_id, **runbooks[runbook_id]}


def query_metrics(service: str) -> dict:
    metrics = _load("metrics.json")
    if service not in metrics:
        return {"error": f"no metrics for service {service}"}
    return {"service": service, **metrics[service]}


_TOOLS = {
    "list_active_alerts": list_active_alerts,
    "get_runbook": get_runbook,
    "query_metrics": query_metrics,
}


def run_tool(name: str, arguments: dict, fail_tool: str | None = None):
    """Runs a tool by name. If name == fail_tool, raises ToolFailure instead."""
    if name == fail_tool:
        raise ToolFailure(f"{name}: upstream timeout after 5s (simulated)")
    if name not in _TOOLS:
        raise ToolFailure(f"unknown tool {name}")
    return _TOOLS[name](**arguments)

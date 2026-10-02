"""OpenTelemetry setup: traces and metrics to the Grafana Cloud OTLP gateway.

The agento11y SDK does not create OTel providers itself. If you skip this,
spans and metrics go to no-op providers and the Agent Observability
analytics views stay empty, with no error anywhere.

The exporters read OTEL_EXPORTER_OTLP_ENDPOINT and OTEL_EXPORTER_OTLP_HEADERS
from the environment (.env). Call setup_otel() BEFORE creating agento11y.Client().
"""

from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

SERVICE_NAME = "sre-triage-agent"


def setup_otel():
    """Registers global tracer and meter providers. Returns a shutdown function."""
    resource = Resource.create({"service.name": SERVICE_NAME, "service.version": "0.1.0"})

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter(), export_interval_millis=10_000)],
    )
    metrics.set_meter_provider(meter_provider)

    def shutdown() -> None:
        # Flush anything still buffered. Short scripts exit before the batch timers fire.
        tracer_provider.shutdown()
        meter_provider.shutdown()

    return shutdown

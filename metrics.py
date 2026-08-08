"""Prometheus metrics for tracking router and LLM performance.

Tracks:
- Query complexity distribution
- Routing decisions by tier and model
- Cost per request and daily totals
- Model performance (latency, token usage)
- Cache hit rates
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from time import time
from typing import Generator

__all__ = [
    "MetricsCollector",
    "get_metrics_collector",
    "record_query_complexity",
    "record_router_decision",
    "record_model_request",
    "record_model_response",
    "get_prometheus_text",
]


@dataclass
class MetricCounter:
    """Simple counter metric."""

    name: str
    help_text: str
    value: int = 0
    labels: dict[str, str] | None = None

    def increment(self, amount: int = 1) -> None:
        self.value += amount

    def to_prometheus(self) -> str:
        """Render as Prometheus text format."""
        return f"# HELP {self.name} {self.help_text}\n# TYPE {self.name} counter\n{self.name} {self.value}"


@dataclass
class MetricGauge:
    """Simple gauge metric."""

    name: str
    help_text: str
    value: float = 0.0

    def set(self, value: float) -> None:
        self.value = value

    def to_prometheus(self) -> str:
        return f"# HELP {self.name} {self.help_text}\n# TYPE {self.name} gauge\n{self.name} {self.value}"


@dataclass
class MetricHistogram:
    """Simple histogram metric with buckets."""

    name: str
    help_text: str
    buckets: list[float] = None
    observations: list[float] = None
    labels: dict[str, str] | None = None

    def __post_init__(self):
        if self.buckets is None:
            self.buckets = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        if self.observations is None:
            self.observations = []

    def observe(self, value: float) -> None:
        self.observations.append(value)

    def to_prometheus(self) -> str:
        lines = [
            f"# HELP {self.name} {self.help_text}",
            f"# TYPE {self.name} histogram",
        ]

        # Count observations in each bucket
        for bucket in self.buckets:
            count = sum(1 for o in self.observations if o <= bucket)
            lines.append(f'{self.name}_bucket{{le="{bucket}"}} {count}')

        lines.append(f'{self.name}_bucket{{le="+Inf"}} {len(self.observations)}')
        lines.append(f"{self.name}_sum {sum(self.observations)}")
        lines.append(f"{self.name}_count {len(self.observations)}")

        return "\n".join(lines)


class MetricsCollector:
    """Collects and stores Prometheus metrics."""

    def __init__(self):
        # Complexity distribution
        self.query_complexity = MetricHistogram(
            "ragstack_query_complexity",
            "Query complexity score distribution (0-100)",
            buckets=[10, 20, 30, 40, 50, 60, 70, 80, 90, 100],
        )

        # Routing metrics
        self.router_decisions_total = MetricCounter(
            "ragstack_router_decisions_total",
            "Total routing decisions made",
        )

        self.router_tier_total = {
            "cheap": MetricCounter("ragstack_router_cheap_total", "Cheap tier routing decisions"),
            "medium": MetricCounter("ragstack_router_medium_total", "Medium tier routing decisions"),
            "expensive": MetricCounter("ragstack_router_expensive_total", "Expensive tier routing decisions"),
        }

        # Cost tracking
        self.estimated_cost_total = MetricGauge(
            "ragstack_estimated_cost_total_usd",
            "Total estimated cost in USD",
        )

        self.model_cost_total = {}  # Dict[model_name, float]
        self.model_request_count = {}  # Dict[model_name, int]

        # Performance metrics
        self.request_latency = MetricHistogram(
            "ragstack_request_latency_seconds",
            "Request latency in seconds",
            buckets=[0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0],
        )

        self.token_usage_input = MetricHistogram(
            "ragstack_tokens_input",
            "Input tokens used per request",
            buckets=[100, 500, 1000, 2000, 5000, 10000, 50000],
        )

        self.token_usage_output = MetricHistogram(
            "ragstack_tokens_output",
            "Output tokens used per request",
            buckets=[10, 50, 100, 200, 500, 1000, 2000],
        )

        # Per-model metrics
        self.model_latency = {}  # Dict[model_name, MetricHistogram]
        self.model_input_tokens = {}  # Dict[model_name, MetricHistogram]
        self.model_output_tokens = {}  # Dict[model_name, MetricHistogram]

    def record_complexity(self, score: int) -> None:
        """Record a query complexity score."""
        self.query_complexity.observe(float(score))

    def record_routing_decision(self, tier: str, model_name: str, complexity: int) -> None:
        """Record a routing decision."""
        self.router_decisions_total.increment()
        self.router_tier_total[tier].increment()

        if model_name not in self.model_request_count:
            self.model_request_count[model_name] = 0
            self.model_cost_total[model_name] = 0.0

        self.model_request_count[model_name] += 1

    def record_request_started(self, model_name: str) -> float:
        """Record request start time. Returns timestamp for later latency recording."""
        return time()

    def record_request_completed(
        self,
        model_name: str,
        start_time: float,
        input_tokens: int,
        output_tokens: int,
        cost: float = 0.0,
    ) -> None:
        """Record request completion with latency and token usage."""
        latency = time() - start_time
        self.request_latency.observe(latency)

        # Per-model metrics
        if model_name not in self.model_latency:
            self.model_latency[model_name] = MetricHistogram(
                f"ragstack_model_latency_{{model=\"{model_name}\"}}",
                f"Latency for {model_name}",
            )
            self.model_input_tokens[model_name] = MetricHistogram(
                f"ragstack_model_input_tokens_{{model=\"{model_name}\"}}",
                f"Input tokens for {model_name}",
            )
            self.model_output_tokens[model_name] = MetricHistogram(
                f"ragstack_model_output_tokens_{{model=\"{model_name}\"}}",
                f"Output tokens for {model_name}",
            )

        self.model_latency[model_name].observe(latency)
        self.model_input_tokens[model_name].observe(float(input_tokens))
        self.model_output_tokens[model_name].observe(float(output_tokens))

        # Aggregate token metrics
        self.token_usage_input.observe(float(input_tokens))
        self.token_usage_output.observe(float(output_tokens))

        # Cost tracking
        if model_name in self.model_cost_total:
            self.model_cost_total[model_name] += cost
            self.estimated_cost_total.set(sum(self.model_cost_total.values()))

    def get_metrics_text(self) -> str:
        """Render all metrics in Prometheus text format."""
        lines = []

        # Query complexity
        lines.append(self.query_complexity.to_prometheus())
        lines.append("")

        # Routing decisions
        lines.append(self.router_decisions_total.to_prometheus())
        lines.append("")
        for tier, counter in self.router_tier_total.items():
            lines.append(counter.to_prometheus())
        lines.append("")

        # Cost
        lines.append(self.estimated_cost_total.to_prometheus())
        lines.append("")

        # Performance
        lines.append(self.request_latency.to_prometheus())
        lines.append("")
        lines.append(self.token_usage_input.to_prometheus())
        lines.append("")
        lines.append(self.token_usage_output.to_prometheus())
        lines.append("")

        # Per-model metrics
        for model_name in sorted(self.model_latency.keys()):
            lines.append(f"# Model: {model_name}")
            lines.append(self.model_latency[model_name].to_prometheus())
            lines.append("")
            lines.append(self.model_input_tokens[model_name].to_prometheus())
            lines.append("")
            lines.append(self.model_output_tokens[model_name].to_prometheus())
            lines.append("")

        return "\n".join(lines)

    def reset(self) -> None:
        """Reset all metrics."""
        self.__init__()


# Global collector instance
_collector: MetricsCollector | None = None


def get_metrics_collector() -> MetricsCollector:
    """Get or create the global metrics collector."""
    global _collector
    if _collector is None:
        _collector = MetricsCollector()
    return _collector


def record_query_complexity(score: int) -> None:
    """Record a query complexity score."""
    get_metrics_collector().record_complexity(score)


def record_router_decision(tier: str, model_name: str, complexity: int) -> None:
    """Record a routing decision."""
    get_metrics_collector().record_routing_decision(tier, model_name, complexity)


def record_model_request(model_name: str) -> float:
    """Record start of model request. Returns timestamp."""
    return get_metrics_collector().record_request_started(model_name)


def record_model_response(
    model_name: str,
    start_time: float,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cost: float = 0.0,
) -> None:
    """Record completion of model request."""
    get_metrics_collector().record_request_completed(
        model_name,
        start_time,
        input_tokens,
        output_tokens,
        cost,
    )


def get_prometheus_text() -> str:
    """Get all metrics in Prometheus text format."""
    return get_metrics_collector().get_metrics_text()


@contextmanager
def track_request(model_name: str, cost_calculator: callable | None = None) -> Generator[None, None, None]:
    """Context manager to track a model request."""
    start_time = record_model_request(model_name)
    try:
        yield
    finally:
        cost = cost_calculator() if cost_calculator else 0.0
        record_model_response(model_name, start_time, cost=cost)

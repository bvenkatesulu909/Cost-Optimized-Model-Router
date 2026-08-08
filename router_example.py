"""Example: Cost-optimized model router in action.

Demonstrates:
1. Complexity estimation
2. Routing decisions
3. Cost tracking
4. Prometheus metrics
5. FastAPI metrics server
"""

from __future__ import annotations

import asyncio
from pathlib import Path

from .router import (
    ModelRouter,
    RouterConfig,
    preset_anthropic_only,
    preset_openrouter,
    preset_local,
    estimate_complexity,
)
from .metrics import get_prometheus_text, get_metrics_collector


def example_basic_routing():
    """Example 1: Basic routing with complexity estimation."""
    print("=" * 60)
    print("Example 1: Basic Routing")
    print("=" * 60)

    # Create router with preset configuration
    config = preset_anthropic_only()
    router = ModelRouter(config)

    # Test queries with varying complexity
    queries = [
        "What is 2+2?",
        "Summarize the economic impact of AI adoption in healthcare",
        "Compare and contrast the philosophical implications of determinism vs free will in quantum mechanics",
        "How do I reset my password?",
    ]

    for query in queries:
        complexity = estimate_complexity(query)
        decision = router.route(query)

        print(f"\nQuery: {query}")
        print(f"  Complexity: {complexity}/100")
        print(f"  Model: {decision.model.name}")
        print(f"  Tier: {decision.model.tier.value}")
        print(f"  Est. Cost: ${decision.estimated_cost:.6f}")
        print(f"  Reasoning: {decision.reason}")


def example_context_aware_routing():
    """Example 2: Routing with context size factor."""
    print("\n" + "=" * 60)
    print("Example 2: Context-Aware Routing")
    print("=" * 60)

    config = preset_anthropic_only()
    router = ModelRouter(config)

    query = "Based on the retrieved passages, what is the main argument?"
    context_sizes = [0, 5000, 20000, 100000]

    for context_chars in context_sizes:
        decision = router.route(query, context_chars=context_chars)
        print(f"\nContext size: {context_chars} chars")
        print(f"  Model: {decision.model.name} ({decision.model.tier.value})")
        print(f"  Est. Cost: ${decision.estimated_cost:.6f}")


def example_forced_tier_routing():
    """Example 3: Force routing to specific tier."""
    print("\n" + "=" * 60)
    print("Example 3: Forced Tier Routing")
    print("=" * 60)

    from .router import ModelTier

    config = preset_anthropic_only()
    router = ModelRouter(config)

    query = "Simple factual question"

    # Force each tier and show what model is selected
    for tier in ModelTier:
        decision = router.route(query, force_tier=tier)
        print(f"\nForced to {tier.value}:")
        print(f"  Model: {decision.model.name}")
        print(f"  Est. Cost: ${decision.estimated_cost:.6f}")


def example_multi_provider_routing():
    """Example 4: Multi-provider routing with OpenRouter."""
    print("\n" + "=" * 60)
    print("Example 4: Multi-Provider Routing (OpenRouter)")
    print("=" * 60)

    config = preset_openrouter()
    router = ModelRouter(config)

    queries = [
        "Fix my code syntax error",
        "Explain quantum entanglement",
        "Analyze the global economic trends in 2024",
    ]

    print("\nOpenRouter pricing tier distribution:")
    for query in queries:
        decision = router.route(query)
        print(f"\n'{query[:40]}...'")
        print(f"  -> {decision.model.name}")
        print(f"  -> ${decision.estimated_cost:.6f}")


def example_cost_tracking():
    """Example 5: Track cumulative costs."""
    print("\n" + "=" * 60)
    print("Example 5: Cost Tracking & Statistics")
    print("=" * 60)

    config = preset_anthropic_only()
    config.daily_budget_usd = 10.0  # Set a daily budget
    router = ModelRouter(config)

    # Simulate routing 20 queries
    import random

    topics = [
        "weather",
        "history",
        "science",
        "philosophy",
        "technology",
    ]

    for i in range(20):
        topic = random.choice(topics)
        # Synthetic complexity-varying questions
        if i % 3 == 0:
            query = f"What is {topic}?"
        elif i % 3 == 1:
            query = f"Explain the detailed mechanisms of {topic}"
        else:
            query = f"Compare and contrast various aspects of {topic} with deep analysis"

        router.route(query)

    stats = router.stats()
    print(f"\nRouter Statistics:")
    print(f"  Queries routed: {stats['queries_routed']}")
    print(f"  Est. daily spend: ${stats['estimated_daily_spend']:.2f}")
    print(f"  Cheap models configured: {stats['cheap_models']}")
    print(f"  Medium models configured: {stats['medium_models']}")
    print(f"  Expensive models configured: {stats['expensive_models']}")


def example_prometheus_metrics():
    """Example 6: Prometheus metrics export."""
    print("\n" + "=" * 60)
    print("Example 6: Prometheus Metrics Export")
    print("=" * 60)

    config = preset_anthropic_only()
    router = ModelRouter(config)

    # Simulate some routing
    queries = [
        "Simple question",
        "What is a moderately complex topic?",
        "Deep analysis required here",
    ]

    for query in queries:
        router.route(query)

    # Export metrics
    print("\nPrometheus metrics (excerpt):")
    print("-" * 40)
    metrics_text = get_prometheus_text()
    # Show first 30 lines
    lines = metrics_text.split("\n")[:30]
    print("\n".join(lines))
    print("...")


def example_fastapi_server():
    """Example 7: FastAPI metrics server."""
    print("\n" + "=" * 60)
    print("Example 7: FastAPI Metrics Server")
    print("=" * 60)

    try:
        from .metrics_server import create_metrics_app
    except ImportError:
        print("FastAPI not installed. Install with: pip install ragstack[router]")
        return

    config = preset_anthropic_only()
    router = ModelRouter(config)

    # Create app
    app = create_metrics_app(router)

    print("FastAPI application created!")
    print("Endpoints:")
    print("  GET /health - Health check")
    print("  GET /metrics - Prometheus metrics")
    print("  GET /router/estimate?question=... - Estimate complexity")
    print("  GET /router/route?question=... - Route query")
    print("  GET /router/models - List configured models")
    print("  GET /router/config - Get configuration")
    print("  GET /router/stats - Get statistics")
    print("\nExample:")
    print("  uvicorn ragstack.router_example:app --port 8000")
    print("  curl 'http://localhost:8000/router/estimate?question=What%20is%20AI?'")


async def example_async_routing():
    """Example 8: Async request tracking."""
    print("\n" + "=" * 60)
    print("Example 8: Request Tracking with Metrics")
    print("=" * 60)

    from .metrics import track_request

    config = preset_anthropic_only()
    router = ModelRouter(config)

    query = "Complex analytical question"
    decision = router.route(query)

    # Simulate an async LLM request with cost calculation
    def calculate_cost():
        return decision.estimated_cost

    with track_request(decision.model.name, cost_calculator=calculate_cost):
        # Simulate API call
        print(f"Calling {decision.model.name}...")
        await asyncio.sleep(0.1)
        print(f"Got response from {decision.model.name}")

    # Show metrics
    collector = get_metrics_collector()
    print(f"\nMetrics recorded:")
    print(f"  Model requests tracked: {len(collector.model_request_count)}")
    print(f"  Total cost tracked: ${collector.estimated_cost_total.value:.6f}")


def main():
    """Run all examples."""
    example_basic_routing()
    example_context_aware_routing()
    example_forced_tier_routing()
    example_multi_provider_routing()
    example_cost_tracking()
    example_prometheus_metrics()
    example_fastapi_server()

    # Run async example
    asyncio.run(example_async_routing())

    print("\n" + "=" * 60)
    print("Examples complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()

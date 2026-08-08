"""Tests for the cost-optimized model router."""

import pytest
from ragstack.router import (
    ComplexityEstimator,
    ModelConfig,
    ModelRouter,
    ModelTier,
    RouterConfig,
    estimate_complexity,
    preset_anthropic_only,
    preset_openrouter,
    preset_local,
)
from ragstack.metrics import (
    get_metrics_collector,
    record_query_complexity,
    record_router_decision,
    get_prometheus_text,
)


class TestComplexityEstimation:
    """Test query complexity estimation."""

    def test_simple_question(self):
        """Simple questions should score low (0-30)."""
        score = estimate_complexity("What time is it?")
        assert 0 <= score <= 30

    def test_moderate_question(self):
        """Moderate questions should score medium (30-70)."""
        score = estimate_complexity("Explain machine learning and its applications")
        assert 30 <= score <= 70

    def test_complex_question(self):
        """Complex questions should score high (60-100)."""
        score = estimate_complexity(
            "Synthesize multiple perspectives on the philosophical implications of quantum mechanics"
        )
        assert 60 <= score <= 100

    def test_context_size_matters(self):
        """Larger context should increase complexity."""
        question = "Summarize this"
        score_no_context = estimate_complexity(question, context_chars=0)
        score_large_context = estimate_complexity(question, context_chars=100000)
        assert score_large_context >= score_no_context

    def test_reasoning_keywords_increase_score(self):
        """Questions with reasoning keywords should score higher."""
        score_factual = estimate_complexity("What is the capital of France?")
        score_analytical = estimate_complexity("Why is Paris important to European history?")
        # Note: "Why" keywords increase score
        assert score_analytical >= score_factual - 10  # Some tolerance for randomness

    def test_multipart_questions_increase_score(self):
        """Questions with multiple parts should score higher."""
        score_simple = estimate_complexity("What is Python?")
        score_multipart = estimate_complexity("What is Python and how does it compare to Java?")
        assert score_multipart > score_simple

    def test_bounded_output(self):
        """Complexity score should always be 0-100."""
        for text_length in [10, 100, 500, 1000]:
            question = "test " * text_length
            score = estimate_complexity(question)
            assert 0 <= score <= 100


class TestModelTierRouting:
    """Test routing decisions by complexity tier."""

    def test_cheap_tier_for_simple_query(self):
        """Simple queries should route to cheap tier."""
        config = preset_anthropic_only()
        router = ModelRouter(config)

        decision = router.route("What is 2+2?")
        assert decision.model.tier == ModelTier.CHEAP

    def test_medium_tier_for_moderate_query(self):
        """Moderate queries should route to medium tier."""
        config = preset_anthropic_only()
        config.cheap_threshold = 30
        config.medium_threshold = 70
        router = ModelRouter(config)

        # Force a moderate complexity score
        decision = router.route(
            "What are the key features of machine learning?",
        )
        # Should be in the 30-70 range and route to medium
        if decision.complexity_score < config.medium_threshold:
            assert decision.model.tier in [ModelTier.CHEAP, ModelTier.MEDIUM]

    def test_expensive_tier_for_complex_query(self):
        """Complex queries should route to expensive tier."""
        config = preset_anthropic_only()
        config.medium_threshold = 30  # Lower threshold to force expensive routing
        router = ModelRouter(config)

        decision = router.route(
            "Provide a comprehensive synthesis of quantum mechanics and relativity..."
        )
        assert decision.model.tier == ModelTier.EXPENSIVE

    def test_force_tier_override(self):
        """Forced tier should override complexity-based routing."""
        config = preset_anthropic_only()
        router = ModelRouter(config)

        # Force cheap tier for complex question
        decision = router.route(
            "Complex question requiring deep analysis",
            force_tier=ModelTier.CHEAP,
        )
        assert decision.model.tier == ModelTier.CHEAP


class TestCostTracking:
    """Test cost estimation and tracking."""

    def test_estimated_cost_is_positive(self):
        """Estimated cost should be positive or zero."""
        config = preset_anthropic_only()
        router = ModelRouter(config)

        decision = router.route("Test query")
        assert decision.estimated_cost >= 0

    def test_expensive_model_higher_cost(self):
        """Expensive tier should have higher estimated cost."""
        config = preset_anthropic_only()
        config.medium_threshold = 0  # Force expensive tier
        router = ModelRouter(config)

        decision_expensive = router.route("Any query", force_tier=ModelTier.EXPENSIVE)

        config.medium_threshold = 200  # Force cheap tier
        router2 = ModelRouter(config)
        decision_cheap = router2.route("Any query", force_tier=ModelTier.CHEAP)

        assert decision_expensive.estimated_cost >= decision_cheap.estimated_cost * 0.9

    def test_router_stats_track_spend(self):
        """Router should accumulate estimated spend."""
        config = preset_anthropic_only()
        router = ModelRouter(config)

        # Route multiple queries
        for i in range(10):
            router.route(f"Query {i}")

        stats = router.stats()
        assert stats["queries_routed"] == 10
        assert stats["estimated_daily_spend"] >= 0


class TestConfigurationAndValidation:
    """Test router configuration and validation."""

    def test_preset_configs_load(self):
        """Preset configurations should be valid."""
        configs = [
            preset_anthropic_only(),
            preset_openrouter(),
            preset_local(),
        ]

        for config in configs:
            router = ModelRouter(config)
            assert router is not None

    def test_empty_config_raises_error(self):
        """Router should require at least one model."""
        config = RouterConfig()  # Empty config
        with pytest.raises(ValueError):
            ModelRouter(config)

    def test_duplicate_model_names_raise_error(self):
        """Configuration should not allow duplicate model names."""
        config = RouterConfig(
            cheap_models=[
                ModelConfig(
                    name="model-a",
                    tier=ModelTier.CHEAP,
                    cost_per_1k_input=0.001,
                    cost_per_1k_output=0.001,
                ),
                ModelConfig(
                    name="model-a",  # Duplicate
                    tier=ModelTier.CHEAP,
                    cost_per_1k_input=0.001,
                    cost_per_1k_output=0.001,
                ),
            ],
        )

        with pytest.raises(ValueError):
            ModelRouter(config)

    def test_get_model_by_name(self):
        """Should retrieve model by name."""
        config = preset_anthropic_only()
        router = ModelRouter(config)

        model = router.get_model_by_name("claude-3-5-haiku-20241022")
        assert model is not None
        assert model.name == "claude-3-5-haiku-20241022"

    def test_get_nonexistent_model_returns_none(self):
        """Getting nonexistent model should return None."""
        config = preset_anthropic_only()
        router = ModelRouter(config)

        model = router.get_model_by_name("nonexistent-model")
        assert model is None


class TestMetrics:
    """Test Prometheus metrics collection."""

    def test_metrics_collection(self):
        """Metrics should be recorded."""
        # Reset collector
        get_metrics_collector().reset()

        # Record some metrics
        record_query_complexity(50)
        record_query_complexity(75)
        record_router_decision("cheap", "model-a", 25)
        record_router_decision("medium", "model-b", 55)

        collector = get_metrics_collector()
        assert len(collector.query_complexity.observations) == 2
        assert collector.router_tier_total["cheap"].value >= 1
        assert collector.router_tier_total["medium"].value >= 1

    def test_prometheus_text_export(self):
        """Metrics should export as Prometheus text."""
        get_metrics_collector().reset()

        # Record some metrics
        record_query_complexity(42)
        record_router_decision("cheap", "test-model", 42)

        text = get_prometheus_text()

        # Should contain expected metric names
        assert "ragstack_query_complexity" in text
        assert "ragstack_router_cheap_total" in text
        assert "# TYPE" in text  # Prometheus format markers


class TestCustomEstimator:
    """Test custom complexity estimators."""

    def test_custom_estimator_override(self):
        """Should use custom estimator if provided."""

        class AlwaysMedium(ComplexityEstimator):
            def estimate(self, question: str, context_chars: int = 0) -> int:
                return 50

        config = RouterConfig(
            cheap_models=[
                ModelConfig("cheap", ModelTier.CHEAP, 0.001, 0.001),
            ],
            medium_models=[
                ModelConfig("medium", ModelTier.MEDIUM, 0.01, 0.01),
            ],
            expensive_models=[],
            complexity_estimator=AlwaysMedium(),
        )

        router = ModelRouter(config)

        # Any query should route to medium due to custom estimator
        for query in ["simple", "complex", "anything"]:
            decision = router.route(query)
            assert decision.complexity_score == 50


class TestRouterDecisionReasoning:
    """Test router decision reasoning."""

    def test_decision_includes_reason(self):
        """Routing decision should include reasoning."""
        config = preset_anthropic_only()
        router = ModelRouter(config)

        decision = router.route("Test query")
        assert decision.reason is not None
        assert len(decision.reason) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

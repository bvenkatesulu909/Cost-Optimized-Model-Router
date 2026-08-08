"""Cost-optimized model router.

Routes queries based on complexity to cheap or expensive models, minimizing spend
while maintaining quality. Supports multi-provider routing via LiteLLM.

Features:
- Automatic complexity scoring from 0-100
- Configurable model tiers with pricing
- Prometheus metrics for spend tracking
- Cost budget enforcement
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Literal

from .metrics import record_router_decision, record_query_complexity

__all__ = [
    "ModelTier",
    "RouterConfig",
    "ComplexityEstimator",
    "ModelRouter",
    "estimate_complexity",
]


class ModelTier(str, Enum):
    """Model tier classification."""

    CHEAP = "cheap"
    MEDIUM = "medium"
    EXPENSIVE = "expensive"


@dataclass
class ModelConfig:
    """Configuration for a model in the router."""

    name: str
    tier: ModelTier
    cost_per_1k_input: float
    cost_per_1k_output: float
    description: str = ""
    max_input_tokens: int = 200000


@dataclass
class RouterConfig:
    """Configuration for the cost-optimized router."""

    # Model definitions
    cheap_models: list[ModelConfig] = field(default_factory=list)
    medium_models: list[ModelConfig] = field(default_factory=list)
    expensive_models: list[ModelConfig] = field(default_factory=list)

    # Complexity thresholds (0-100 scale)
    # cheap -> medium threshold (default 40)
    cheap_threshold: int = 40
    # medium -> expensive threshold (default 70)
    medium_threshold: int = 70

    # Optional budget enforcement
    daily_budget_usd: float | None = None
    query_budget_usd: float | None = None

    # Complexity estimation
    complexity_estimator: ComplexityEstimator | None = None


class ComplexityEstimator:
    """Estimates query complexity based on various heuristics."""

    def estimate(self, question: str, context_chars: int = 0) -> int:
        """Estimate complexity (0-100) of a question.

        Factors:
        - Question length and structure
        - Token count and special characters
        - Context size
        - Presence of domain-specific terminology
        """
        score = 0

        # Length factor (0-30 points)
        # Short q's are simpler; longer ones need more reasoning
        q_words = len(question.split())
        if q_words < 5:
            score += 10
        elif q_words < 15:
            score += 20
        else:
            score += min(30, 20 + q_words // 5)

        # Complexity indicators (0-40 points)
        q_lower = question.lower()

        # Multi-part questions
        if any(conn in q_lower for conn in [" and ", " or ", " but "]):
            score += 15

        # Reasoning keywords
        reasoning_keywords = [
            "why", "how", "compare", "contrast", "analyze", "evaluate",
            "synthesis", "explain", "discuss", "interpret", "infer"
        ]
        for keyword in reasoning_keywords:
            if keyword in q_lower:
                score += 10
                break

        # Temporal or conditional complexity
        if any(word in q_lower for word in ["if", "when", "before", "after", "depends"]):
            score += 10

        # Negative questions
        if "not " in q_lower or "n't" in q_lower:
            score += 5

        # Context size factor (0-20 points)
        if context_chars > 0:
            # More context = potentially more complex integration
            context_complexity = min(20, context_chars // 1000)
            score += context_complexity

        # Special punctuation (0-10 points)
        special_chars = sum(1 for c in question if c in "?!:;")
        score += min(10, special_chars * 2)

        return min(100, score)


def estimate_complexity(question: str, context_chars: int = 0) -> int:
    """Convenience function to estimate query complexity."""
    estimator = ComplexityEstimator()
    return estimator.estimate(question, context_chars)


@dataclass
class RoutingDecision:
    """Result of routing a query to a model."""

    model: ModelConfig
    complexity_score: int
    estimated_cost: float | None = None
    reason: str = ""


class ModelRouter:
    """Routes queries to models based on complexity and cost."""

    def __init__(self, config: RouterConfig):
        self.config = config
        self.estimator = config.complexity_estimator or ComplexityEstimator()
        self._validate_config()
        self._daily_spend = 0.0
        self._query_count = 0

    def _validate_config(self) -> None:
        """Validate router configuration."""
        all_models = (
            self.config.cheap_models +
            self.config.medium_models +
            self.config.expensive_models
        )
        if not all_models:
            raise ValueError("Router must have at least one model configured")

        # Check for duplicate model names
        names = [m.name for m in all_models]
        if len(names) != len(set(names)):
            raise ValueError("Duplicate model names in configuration")

    def route(
        self,
        question: str,
        context_chars: int = 0,
        force_tier: ModelTier | None = None,
    ) -> RoutingDecision:
        """Route a question to an appropriate model.

        Args:
            question: The user's question
            context_chars: Size of retrieved context in characters
            force_tier: Override complexity and force a specific tier

        Returns:
            RoutingDecision with selected model and reasoning
        """
        complexity = self.estimator.estimate(question, context_chars)
        record_query_complexity(complexity)

        # Determine tier based on complexity
        if force_tier:
            tier = force_tier
            reason = f"Forced to {tier.value} tier"
        elif complexity < self.config.cheap_threshold:
            tier = ModelTier.CHEAP
            reason = f"Complexity {complexity} < {self.config.cheap_threshold}"
        elif complexity < self.config.medium_threshold:
            tier = ModelTier.MEDIUM
            reason = f"Complexity {complexity} < {self.config.medium_threshold}"
        else:
            tier = ModelTier.EXPENSIVE
            reason = f"Complexity {complexity} >= {self.config.medium_threshold}"

        # Select model from tier
        model = self._select_model_from_tier(tier)

        if not model:
            # Fall back to any available model
            for m in (
                self.config.cheap_models +
                self.config.medium_models +
                self.config.expensive_models
            ):
                model = m
                reason = f"Tier {tier.value} unavailable, using {model.name}"
                break

        # Estimate cost (rough approximation)
        estimated_tokens = min(
            complexity * 10,  # Heuristic: complexity -> output tokens
            model.max_input_tokens
        )
        estimated_cost = (
            (len(question) / 4 / 1000) * model.cost_per_1k_input +
            (estimated_tokens / 1000) * model.cost_per_1k_output
        )

        # Check budget if configured
        if self.config.query_budget_usd and estimated_cost > self.config.query_budget_usd:
            reason += f" (over query budget {estimated_cost:.4f} > {self.config.query_budget_usd})"

        decision = RoutingDecision(
            model=model,
            complexity_score=complexity,
            estimated_cost=estimated_cost,
            reason=reason,
        )

        record_router_decision(tier, model.name, complexity)
        self._query_count += 1
        self._daily_spend += estimated_cost

        return decision

    def _select_model_from_tier(self, tier: ModelTier) -> ModelConfig | None:
        """Select a model from the configured tier."""
        models_by_tier = {
            ModelTier.CHEAP: self.config.cheap_models,
            ModelTier.MEDIUM: self.config.medium_models,
            ModelTier.EXPENSIVE: self.config.expensive_models,
        }
        candidates = models_by_tier[tier]
        return candidates[0] if candidates else None

    def get_model_by_name(self, name: str) -> ModelConfig | None:
        """Look up a model by name."""
        for model in (
            self.config.cheap_models +
            self.config.medium_models +
            self.config.expensive_models
        ):
            if model.name == name:
                return model
        return None

    def stats(self) -> dict:
        """Return router statistics."""
        return {
            "queries_routed": self._query_count,
            "estimated_daily_spend": self._daily_spend,
            "cheap_models": len(self.config.cheap_models),
            "medium_models": len(self.config.medium_models),
            "expensive_models": len(self.config.expensive_models),
        }


# Preset configurations for common use cases

def preset_openrouter() -> RouterConfig:
    """OpenRouter-based configuration (cheap and expensive models)."""
    return RouterConfig(
        cheap_models=[
            ModelConfig(
                name="openrouter/openchat-3.5-0106",
                tier=ModelTier.CHEAP,
                cost_per_1k_input=0.000011,
                cost_per_1k_output=0.000011,
                description="Fast, cheap model for simple queries",
                max_input_tokens=8000,
            ),
        ],
        medium_models=[
            ModelConfig(
                name="openrouter/mixtral-8x7b-instruct-v0.1",
                tier=ModelTier.MEDIUM,
                cost_per_1k_input=0.00024,
                cost_per_1k_output=0.00024,
                description="Balanced model for general reasoning",
                max_input_tokens=32000,
            ),
        ],
        expensive_models=[
            ModelConfig(
                name="claude-3-5-sonnet-20241022",
                tier=ModelTier.EXPENSIVE,
                cost_per_1k_input=0.003,
                cost_per_1k_output=0.015,
                description="Premium model for complex reasoning",
                max_input_tokens=200000,
            ),
        ],
        cheap_threshold=35,
        medium_threshold=65,
    )


def preset_anthropic_only() -> RouterConfig:
    """Anthropic models only (uses speed/capability as cost proxy)."""
    return RouterConfig(
        cheap_models=[
            ModelConfig(
                name="claude-3-5-haiku-20241022",
                tier=ModelTier.CHEAP,
                cost_per_1k_input=0.00080,
                cost_per_1k_output=0.004,
                description="Fast model for simple queries",
                max_input_tokens=200000,
            ),
        ],
        medium_models=[
            ModelConfig(
                name="claude-3-5-sonnet-20241022",
                tier=ModelTier.MEDIUM,
                cost_per_1k_input=0.003,
                cost_per_1k_output=0.015,
                description="Balanced model for general reasoning",
                max_input_tokens=200000,
            ),
        ],
        expensive_models=[
            ModelConfig(
                name="claude-3-opus-20250219",
                tier=ModelTier.EXPENSIVE,
                cost_per_1k_input=0.015,
                cost_per_1k_output=0.075,
                description="Premium model for complex reasoning",
                max_input_tokens=200000,
            ),
        ],
        cheap_threshold=40,
        medium_threshold=70,
    )


def preset_local() -> RouterConfig:
    """Local models via Ollama (zero cost)."""
    return RouterConfig(
        cheap_models=[
            ModelConfig(
                name="mistral:latest",
                tier=ModelTier.CHEAP,
                cost_per_1k_input=0.0,
                cost_per_1k_output=0.0,
                description="Local Mistral model",
                max_input_tokens=32000,
            ),
        ],
        medium_models=[
            ModelConfig(
                name="neural-chat:latest",
                tier=ModelTier.MEDIUM,
                cost_per_1k_input=0.0,
                cost_per_1k_output=0.0,
                description="Local neural chat model",
                max_input_tokens=4096,
            ),
        ],
        expensive_models=[],
        cheap_threshold=50,
        medium_threshold=100,  # Never use expensive tier for local
    )

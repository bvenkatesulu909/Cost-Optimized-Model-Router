"""FastAPI server for exposing metrics and router endpoints.

Provides:
- /metrics - Prometheus metrics endpoint
- /health - Health check
- /router/estimate - Complexity estimation
- /router/route - Routing decision with explanations
"""

from __future__ import annotations

from typing import Optional

try:
    from fastapi import FastAPI, HTTPException
    from fastapi.responses import PlainTextResponse
except ImportError:
    raise ImportError(
        "FastAPI not installed. Install with: pip install ragstack[router]"
    )

from .metrics import get_prometheus_text
from .router import ModelRouter, RouterConfig, ModelTier

__all__ = ["create_metrics_app"]


def create_metrics_app(router: ModelRouter) -> FastAPI:
    """Create a FastAPI application with metrics and router endpoints.

    Args:
        router: Configured ModelRouter instance

    Returns:
        FastAPI application ready to run
    """
    app = FastAPI(
        title="RAGStack Model Router",
        description="Cost-optimized model routing with Prometheus metrics",
        version="0.1.0",
    )

    @app.get("/health")
    async def health():
        """Health check endpoint."""
        return {"status": "healthy", "version": "0.1.0"}

    @app.get("/metrics", response_class=PlainTextResponse)
    async def metrics():
        """Prometheus metrics endpoint."""
        return get_prometheus_text()

    @app.get("/router/estimate")
    async def estimate_complexity(question: str, context_chars: int = 0):
        """Estimate complexity of a query without routing."""
        try:
            complexity = router.estimator.estimate(question, context_chars)
            return {
                "question": question,
                "context_chars": context_chars,
                "complexity": complexity,
                "difficulty": "easy" if complexity < 40 else "medium" if complexity < 70 else "hard",
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/router/route")
    async def route_query(
        question: str,
        context_chars: int = 0,
        force_tier: Optional[str] = None,
    ):
        """Route a query to the best model.

        Args:
            question: The user's question
            context_chars: Size of retrieved context
            force_tier: Force routing to a specific tier (cheap/medium/expensive)

        Returns:
            Routing decision with model, complexity, estimated cost, and reasoning
        """
        try:
            tier = None
            if force_tier:
                try:
                    tier = ModelTier(force_tier.lower())
                except ValueError:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Invalid tier. Must be one of: {', '.join(t.value for t in ModelTier)}",
                    )

            decision = router.route(question, context_chars, force_tier=tier)

            return {
                "model": decision.model.name,
                "tier": decision.model.tier.value,
                "complexity": decision.complexity_score,
                "estimated_cost_usd": round(decision.estimated_cost, 6) if decision.estimated_cost else None,
                "reasoning": decision.reason,
                "description": decision.model.description,
                "max_input_tokens": decision.model.max_input_tokens,
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))

    @app.get("/router/models")
    async def list_models():
        """List all configured models by tier."""
        return {
            "cheap": [
                {
                    "name": m.name,
                    "cost_per_1k_input": m.cost_per_1k_input,
                    "cost_per_1k_output": m.cost_per_1k_output,
                    "description": m.description,
                }
                for m in router.config.cheap_models
            ],
            "medium": [
                {
                    "name": m.name,
                    "cost_per_1k_input": m.cost_per_1k_input,
                    "cost_per_1k_output": m.cost_per_1k_output,
                    "description": m.description,
                }
                for m in router.config.medium_models
            ],
            "expensive": [
                {
                    "name": m.name,
                    "cost_per_1k_input": m.cost_per_1k_input,
                    "cost_per_1k_output": m.cost_per_1k_output,
                    "description": m.description,
                }
                for m in router.config.expensive_models
            ],
        }

    @app.get("/router/config")
    async def get_config():
        """Get current router configuration."""
        return {
            "cheap_threshold": router.config.cheap_threshold,
            "medium_threshold": router.config.medium_threshold,
            "daily_budget_usd": router.config.daily_budget_usd,
            "query_budget_usd": router.config.query_budget_usd,
        }

    @app.get("/router/stats")
    async def get_stats():
        """Get router statistics."""
        return router.stats()

    return app

# Router Integration with RAGStack

Quick integration examples showing how to use the cost-optimized model router with your existing RAG pipeline.

## Example 1: Drop-in Router for `ragstack answer`

Replace the backend selection in your CLI with intelligent routing:

**File: `src/ragstack/llm.py` (modified `answer` function)**

```python
def answer(
    question: str,
    *,
    top_k: int | None = None,
    min_score: float | None = None,
    source_filter: str | None = None,
    index_dir: Path | None = None,
    backend: str | None = None,
    model: str | None = None,
    effort: str | None = None,
    max_tokens: int | None = None,
    on_text: Callable[[str], None] | None = None,
    use_router: bool = False,  # NEW: Enable cost-optimized routing
) -> AnswerResult:
    """Retrieve passages for `question`, then have the configured model answer.
    
    If `use_router=True`, automatically selects the best model tier based on
    query complexity.
    """
    if not question or not question.strip():
        raise ValueError("question must not be empty")

    # Retrieve first to know context size
    hits = retrieve.search(
        question,
        top_k=top_k,
        min_score=min_score,
        source_filter=source_filter,
        index_dir=index_dir,
    )

    # Early return for empty context
    if not hits:
        return AnswerResult(
            answer=(
                "No passages in the index cleared the relevance threshold for this "
                "question. Try rephrasing, lowering --min-score, or indexing more "
                "documents."
            ),
            hits=[],
            model=model or "none",
            stop_reason="no_context",
        )

    # Use router to select model if enabled
    if use_router:
        from .router import ModelRouter, preset_anthropic_only
        from .metrics import record_model_response, record_model_request

        router = ModelRouter(preset_anthropic_only())
        context_chars = sum(len(h.text) for h in hits)
        decision = router.route(question, context_chars=context_chars)
        model = decision.model.name

        # Track metrics
        start_time = record_model_request(model)
        
        try:
            backend = backend or config.LLM_BACKEND
            result = _BACKENDS[backend.lower()](
                question,
                hits,
                model=model,
                effort=effort,
                max_tokens=max_tokens,
                on_text=on_text,
            )
            
            # Record usage
            tokens_in = result.usage.get("input_tokens", 0)
            tokens_out = result.usage.get("output_tokens", 0)
            cost = decision.estimated_cost or 0.0
            record_model_response(model, start_time, tokens_in, tokens_out, cost)
            
            return result
        except Exception as e:
            record_model_response(model, start_time)
            raise
    else:
        # Original logic
        backend = (backend or config.LLM_BACKEND).strip().lower()
        if backend not in _BACKENDS:
            raise ValueError(...)
        
        model = model or config.model_for(backend)
        return _BACKENDS[backend](
            question,
            hits,
            model=model,
            effort=effort,
            max_tokens=max_tokens,
            on_text=on_text,
        )
```

**CLI Usage:**

```bash
# Without router (original behavior)
ragstack answer "What is AI?" --backend anthropic

# With router (automatic model selection)
ragstack answer "What is AI?" --use-router

# With router on OpenRouter (supports many models)
ragstack answer "Complex question" --use-router --router-preset openrouter
```

## Example 2: Integrate with PDF QA Module

**File: `src/ragstack/pdf_qa/llm_chain.py` (new router-aware chain)**

```python
from ..router import ModelRouter, preset_anthropic_only
from ..metrics import record_model_request, record_model_response


class RouterAwareLLMChain:
    """LLM chain that selects models based on query complexity."""

    def __init__(self, use_router: bool = False):
        self.use_router = use_router
        self.router = ModelRouter(preset_anthropic_only()) if use_router else None

    def invoke(self, question: str, context_text: str, **kwargs):
        """Chain execution with optional routing."""
        if self.router:
            # Route based on complexity + context
            decision = self.router.route(
                question,
                context_chars=len(context_text),
            )
            model = decision.model.name
            
            start_time = record_model_request(model)
            try:
                result = self._call_llm(question, context_text, model, **kwargs)
                
                # Record metrics
                tokens_in = result.get("input_tokens", 0)
                tokens_out = result.get("output_tokens", 0)
                cost = decision.estimated_cost or 0.0
                record_model_response(model, start_time, tokens_in, tokens_out, cost)
                
                return result
            except Exception as e:
                record_model_response(model, start_time)
                raise
        else:
            return self._call_llm(question, context_text, None, **kwargs)

    def _call_llm(self, question: str, context: str, model: str | None, **kwargs):
        # Original LLM call logic
        pass
```

## Example 3: Multi-Provider Setup with LiteLLM

**File: `src/ragstack/config.py` (new router config)**

```python
from .router import RouterConfig, ModelConfig, ModelTier, ModelRouter

def get_multimodel_router() -> ModelRouter:
    """Create a router supporting multiple LLM providers."""
    config = RouterConfig(
        cheap_models=[
            ModelConfig(
                name="openrouter/openchat-3.5-0106",
                tier=ModelTier.CHEAP,
                cost_per_1k_input=0.000011,
                cost_per_1k_output=0.000011,
                description="Ultra-cheap fast model",
                max_input_tokens=8000,
            ),
            ModelConfig(
                name="together_ai/Mistral-7B",
                tier=ModelTier.CHEAP,
                cost_per_1k_input=0.0002,
                cost_per_1k_output=0.0002,
                description="Mistral on Together AI",
                max_input_tokens=32000,
            ),
        ],
        medium_models=[
            ModelConfig(
                name="openrouter/mixtral-8x7b-instruct",
                tier=ModelTier.MEDIUM,
                cost_per_1k_input=0.00024,
                cost_per_1k_output=0.00024,
                description="Mixtral MoE model",
                max_input_tokens=32000,
            ),
            ModelConfig(
                name="claude-3-5-sonnet-20241022",
                tier=ModelTier.MEDIUM,
                cost_per_1k_input=0.003,
                cost_per_1k_output=0.015,
                description="Claude Sonnet",
                max_input_tokens=200000,
            ),
        ],
        expensive_models=[
            ModelConfig(
                name="claude-3-opus-20250219",
                tier=ModelTier.EXPENSIVE,
                cost_per_1k_input=0.015,
                cost_per_1k_output=0.075,
                description="Claude Opus",
                max_input_tokens=200000,
            ),
            ModelConfig(
                name="openrouter/meta-llama/llama-3-70b-instruct",
                tier=ModelTier.EXPENSIVE,
                cost_per_1k_input=0.00063,
                cost_per_1k_output=0.00063,
                description="Llama 3 70B",
                max_input_tokens=8192,
            ),
        ],
        cheap_threshold=35,
        medium_threshold=70,
        daily_budget_usd=50.0,  # Stop routing expensive queries after $50/day
    )

    return ModelRouter(config)
```

## Example 4: Metrics Dashboard with Prometheus + Grafana

**File: `docker-compose.yml`**

```yaml
version: '3.8'

services:
  ragstack-router:
    build:
      context: .
      dockerfile: Dockerfile.router
    ports:
      - "8000:8000"
    environment:
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
      OPENROUTER_API_KEY: ${OPENROUTER_API_KEY}
    command: >
      uvicorn ragstack.metrics_server:create_app
      --host 0.0.0.0 --port 8000 --reload
    volumes:
      - ./src:/app/src

  prometheus:
    image: prom/prometheus:latest
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
      - prometheus_data:/prometheus
    command:
      - '--config.file=/etc/prometheus/prometheus.yml'
      - '--storage.tsdb.path=/prometheus'

  grafana:
    image: grafana/grafana:latest
    ports:
      - "3000:3000"
    environment:
      GF_SECURITY_ADMIN_PASSWORD: admin
      GF_INSTALL_PLUGINS: grafana-piechart-panel
    volumes:
      - grafana_data:/var/lib/grafana
      - ./grafana/provisioning:/etc/grafana/provisioning
    depends_on:
      - prometheus

volumes:
  prometheus_data:
  grafana_data:
```

**File: `prometheus.yml`**

```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'ragstack-router'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
    scrape_interval: 10s
```

**Access:**
- Metrics: http://localhost:8000/metrics
- Prometheus: http://localhost:9090
- Grafana: http://localhost:3000 (admin/admin)

## Example 5: Test Different Router Presets

**File: `test_router_presets.py`**

```python
from ragstack.router import preset_anthropic_only, preset_openrouter, preset_local
from ragstack.router import ModelRouter

def compare_routing_decisions():
    """Compare how different presets route the same queries."""
    
    queries = [
        "What is AI?",
        "Compare and contrast machine learning approaches",
        "Provide comprehensive analysis of quantum computing's impact",
    ]
    
    presets = {
        "anthropic": preset_anthropic_only(),
        "openrouter": preset_openrouter(),
        "local": preset_local(),
    }
    
    for preset_name, config in presets.items():
        router = ModelRouter(config)
        print(f"\n{preset_name.upper()} Preset:")
        print("-" * 50)
        
        for query in queries:
            decision = router.route(query)
            print(f"\nQuery: '{query[:40]}...'")
            print(f"  → Model: {decision.model.name}")
            print(f"  → Tier: {decision.model.tier.value}")
            print(f"  → Cost: ${decision.estimated_cost:.6f}")

if __name__ == "__main__":
    compare_routing_decisions()
```

## Example 6: Cost Analysis Script

**File: `analyze_router_costs.py`**

```python
from ragstack.router import ModelRouter, preset_anthropic_only
from ragstack.metrics import get_metrics_collector
import json


def analyze_routing_costs(queries: list[str]):
    """Analyze routing and estimated costs for a list of queries."""
    
    router = ModelRouter(preset_anthropic_only())
    costs_by_tier = {}
    queries_by_tier = {}
    
    for query in queries:
        decision = router.route(query)
        tier = decision.model.tier.value
        
        if tier not in costs_by_tier:
            costs_by_tier[tier] = 0.0
            queries_by_tier[tier] = []
        
        costs_by_tier[tier] += decision.estimated_cost
        queries_by_tier[tier].append({
            "query": query,
            "model": decision.model.name,
            "complexity": decision.complexity_score,
            "cost": decision.estimated_cost,
        })
    
    # Print analysis
    print(json.dumps({
        "total_queries": len(queries),
        "total_cost": sum(costs_by_tier.values()),
        "cost_by_tier": costs_by_tier,
        "queries_by_tier": {
            tier: len(queries_by_tier[tier])
            for tier in queries_by_tier
        },
        "breakdown": queries_by_tier,
    }, indent=2))


if __name__ == "__main__":
    sample_queries = [
        "What is Python?",
        "How do neural networks work?",
        "Explain photosynthesis",
        "Compare quantum and classical computing",
        # ... add more queries
    ]
    
    analyze_routing_costs(sample_queries)
```

## Running the Examples

```bash
# Install dependencies
pip install -e ".[router]"

# Run basic routing example
python -m ragstack.router_example

# Run integration test
python -m pytest tests/test_router.py -v

# Start metrics server
uvicorn ragstack.metrics_server:create_app --port 8000

# Run cost analysis
python analyze_router_costs.py

# Query the router API
curl "http://localhost:8000/router/route?question=What%20is%20AI?"
curl "http://localhost:8000/metrics"
```

## Monitoring & Optimization

### Key Metrics to Watch

1. **Cost Distribution**: Check if cheap tier is handling 70%+ of queries
2. **Complexity Scores**: Verify complexity estimation matches actual difficulty
3. **Model Performance**: Monitor latency per model tier
4. **Error Rates**: Track if any tier has higher failure rates

### Cost Optimization Tips

1. **Lower cheap threshold** if expensive queries appear simple
2. **Raise medium threshold** to route more to cheap models
3. **Add cheaper models** to expensive tier for fallback
4. **Set daily budgets** to prevent surprise costs
5. **Use force_tier** in A/B tests to measure savings

### Performance Monitoring

```bash
# Watch real-time metrics
watch -n 5 'curl -s http://localhost:8000/router/stats | jq .'

# Export metrics for analysis
curl http://localhost:8000/metrics > metrics_backup.txt

# Check model-specific latency
curl http://localhost:8000/metrics | grep ragstack_model_latency
```

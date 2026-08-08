# Cost-Optimized Model Router

A production-ready system for intelligently routing queries to cheap or expensive LLM models based on complexity, with spend tracking via Prometheus metrics.

## Quick Start

```bash
# Install router dependencies
pip install -e ".[router]"

# Run basic example
python -c "from ragstack.router_example import example_basic_routing; example_basic_routing()"
```

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    User Query                            │
└──────────────────────┬──────────────────────────────────┘
                       │
                       v
        ┌──────────────────────────┐
        │ Complexity Estimator     │
        │ (0-100 score)            │
        └──────────────┬───────────┘
                       │
                       v
        ┌──────────────────────────┐       ┌──────────────┐
        │ Model Router             │──────>│ Metrics      │
        │ - Route by complexity    │       │ - Track cost │
        │ - Select model tier      │       │ - Histogram  │
        │ - Enforce budgets        │       │ - Counters   │
        └──────────────┬───────────┘       └──────────────┘
                       │
        ┌──────────────┴──────────────────┐
        │                                  │
        v                                  v
   ┌─────────────┐           ┌──────────────────────┐
   │ LLM Call    │           │ FastAPI Metrics      │
   │ (w/ timing) │           │ Server (optional)    │
   └─────────────┘           │ - /metrics           │
                             │ - /router/route      │
                             │ - /router/stats      │
                             └──────────────────────┘
```

## Core Concepts

### Complexity Scoring

The router estimates query complexity (0-100) based on:
- **Length** (0-30 points): Short queries are simpler
- **Reasoning keywords** (0-40 points): "why", "compare", "analyze", etc.
- **Structure** (0-10 points): Multi-part questions, conditionals
- **Context size** (0-20 points): Larger contexts increase complexity

```python
from ragstack.router import estimate_complexity

score = estimate_complexity("What is 2+2?")  # ~10
score = estimate_complexity("Compare quantum mechanics and relativity")  # ~60
score = estimate_complexity("Synthesize multiple viewpoints on determinism...")  # ~85
```

### Model Tiers

Queries are routed to three model tiers based on complexity:

| Tier | Complexity | Use Case | Examples |
|------|-----------|----------|----------|
| **Cheap** | 0-40 | Simple factual questions | Haiku, Mistral, OpenChat |
| **Medium** | 40-70 | General reasoning | Sonnet, Mixtral, Neural Chat |
| **Expensive** | 70-100 | Complex analysis & synthesis | Opus, GPT-4, Claude |

Thresholds are configurable via `RouterConfig`.

### Cost Tracking

Every routing decision includes estimated cost based on:
- Model's per-token pricing
- Query complexity heuristic
- Output token estimates

Cumulative costs tracked in Prometheus metrics for monitoring daily/per-query spend.

## Usage Patterns

### 1. Basic Routing

```python
from ragstack.router import ModelRouter, preset_anthropic_only

# Create router
config = preset_anthropic_only()
router = ModelRouter(config)

# Route a query
decision = router.route("What is machine learning?")

print(f"Model: {decision.model.name}")  # claude-3-5-haiku-20241022
print(f"Tier: {decision.model.tier}")   # ModelTier.CHEAP
print(f"Cost: ${decision.estimated_cost:.6f}")
print(f"Reason: {decision.reason}")
```

### 2. Custom Configuration

```python
from ragstack.router import ModelRouter, RouterConfig, ModelConfig, ModelTier

config = RouterConfig(
    cheap_models=[
        ModelConfig(
            name="claude-3-5-haiku-20241022",
            tier=ModelTier.CHEAP,
            cost_per_1k_input=0.00080,
            cost_per_1k_output=0.004,
            description="Fast, cheap model",
        ),
    ],
    medium_models=[...],
    expensive_models=[...],
    cheap_threshold=35,      # Tune complexity thresholds
    medium_threshold=70,
)

router = ModelRouter(config)
```

### 3. Context-Aware Routing

Include retrieved context size for more accurate routing:

```python
# Query becomes more complex with large context
decision = router.route(
    question="Summarize these passages",
    context_chars=50000,  # 50k chars of retrieved context
)
```

### 4. Force Specific Tier

Override automatic routing for A/B testing or fallback:

```python
from ragstack.router import ModelTier

# Always use cheap model for this query
decision = router.route(
    question="What time is it?",
    force_tier=ModelTier.CHEAP,
)
```

### 5. Integration with RAGStack

Replace the default backend selection in your answer flow:

```python
from ragstack.router import ModelRouter, preset_openrouter
from ragstack import llm, retrieve

# Initialize router
router = ModelRouter(preset_openrouter())

# In answer() flow:
question = "Your question"
hits = retrieve.search(question)

if not hits:
    return llm.AnswerResult(answer="No context", hits=[])

# Route to best model
decision = router.route(question, context_chars=sum(len(h.text) for h in hits))
model_name = decision.model.name

# Call LLM with selected model
result = llm.answer(question, model=model_name, ...)
```

## Preset Configurations

### Anthropic Models Only
```python
from ragstack.router import preset_anthropic_only

config = preset_anthropic_only()
# Routes through: Haiku (cheap) -> Sonnet (medium) -> Opus (expensive)
```

### OpenRouter (Multi-Provider)
```python
from ragstack.router import preset_openrouter

config = preset_openrouter()
# Cheap: OpenChat ($0.000011/1k tokens)
# Medium: Mixtral ($0.00024/1k tokens)
# Expensive: Claude ($0.003-0.015/1k tokens)
```

### Local Models (Ollama)
```python
from ragstack.router import preset_local

config = preset_local()
# Zero-cost: Mistral -> Neural Chat
# Good for privacy-sensitive deployments
```

## Metrics & Monitoring

### Prometheus Metrics

The router tracks everything in Prometheus format:

```
# Query complexity distribution
ragstack_query_complexity_bucket{le="50"} 12
ragstack_query_complexity_bucket{le="100"} 45

# Routing decisions by tier
ragstack_router_cheap_total 320
ragstack_router_medium_total 85
ragstack_router_expensive_total 18

# Cost tracking
ragstack_estimated_cost_total_usd 42.37

# Per-model latency
ragstack_model_latency_bucket{model="claude-3-5-haiku-20241022",le="0.5"} 298
ragstack_model_latency_bucket{model="claude-3-5-haiku-20241022",le="1.0"} 315

# Token usage
ragstack_tokens_input_sum 125430
ragstack_tokens_output_sum 28591
```

### Export Metrics

```python
from ragstack.metrics import get_prometheus_text

metrics = get_prometheus_text()
print(metrics)  # Full Prometheus text format
```

### Track Requests

```python
from ragstack.metrics import record_model_request, record_model_response

start_time = record_model_request("claude-3-5-haiku-20241022")

# ... call LLM ...

record_model_response(
    model_name="claude-3-5-haiku-20241022",
    start_time=start_time,
    input_tokens=450,
    output_tokens=120,
    cost=0.0015,
)
```

Or use context manager:

```python
from ragstack.metrics import track_request

with track_request("claude-3-5-haiku-20241022"):
    # ... LLM call ...
    pass
```

## FastAPI Metrics Server

Expose router decisions and metrics via HTTP:

```python
from ragstack.router import ModelRouter, preset_anthropic_only
from ragstack.metrics_server import create_metrics_app
import uvicorn

# Create router
config = preset_anthropic_only()
router = ModelRouter(config)

# Create FastAPI app
app = create_metrics_app(router)

# Run server
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

### Endpoints

#### Health Check
```bash
curl http://localhost:8000/health
# {"status": "healthy", "version": "0.1.0"}
```

#### Complexity Estimation
```bash
curl "http://localhost:8000/router/estimate?question=What%20is%20AI?"
# {
#   "question": "What is AI?",
#   "complexity": 25,
#   "difficulty": "easy",
#   ...
# }
```

#### Route Query
```bash
curl "http://localhost:8000/router/route?question=Explain%20quantum%20mechanics&context_chars=10000"
# {
#   "model": "claude-3-5-haiku-20241022",
#   "tier": "cheap",
#   "complexity": 55,
#   "estimated_cost_usd": 0.001234,
#   "reasoning": "Complexity 55 < 70",
#   ...
# }
```

#### List Models
```bash
curl http://localhost:8000/router/models
# {
#   "cheap": [...],
#   "medium": [...],
#   "expensive": [...]
# }
```

#### Get Statistics
```bash
curl http://localhost:8000/router/stats
# {
#   "queries_routed": 427,
#   "estimated_daily_spend": 18.42,
#   ...
# }
```

#### Prometheus Metrics
```bash
curl http://localhost:8000/metrics
# Prometheus text format for Grafana scraping
```

## Advanced Usage

### Custom Complexity Estimator

```python
from ragstack.router import ComplexityEstimator, ModelRouter, RouterConfig

class CustomEstimator(ComplexityEstimator):
    def estimate(self, question: str, context_chars: int = 0) -> int:
        # Your custom logic
        if "machine learning" in question.lower():
            return 75
        # Fallback to default
        return super().estimate(question, context_chars)

config = RouterConfig(complexity_estimator=CustomEstimator())
router = ModelRouter(config)
```

### Budget Enforcement

```python
from ragstack.router import ModelRouter, RouterConfig

config = RouterConfig(
    cheap_models=[...],
    medium_models=[...],
    expensive_models=[...],
    daily_budget_usd=100.0,      # Stop routing expensive queries after $100
    query_budget_usd=0.50,        # Reject queries over $0.50 each
)

router = ModelRouter(config)

# Check estimated cost before routing
decision = router.route(query)
if decision.estimated_cost and decision.estimated_cost > 0.50:
    print(f"Query over budget: ${decision.estimated_cost:.2f}")
```

### Multi-Provider with LiteLLM

LiteLLM is included in the `[router]` extra. Use it to support 100+ model providers:

```python
# Configure models from different providers
config = RouterConfig(
    cheap_models=[
        ModelConfig(
            name="openrouter/mistral-7b",
            tier=ModelTier.CHEAP,
            cost_per_1k_input=0.00011,
            cost_per_1k_output=0.00011,
        ),
        ModelConfig(
            name="together_ai/Mistral-7B",
            tier=ModelTier.CHEAP,
            cost_per_1k_input=0.0002,
            cost_per_1k_output=0.0002,
        ),
    ],
    # ... medium and expensive tiers
)
```

## Integration with Existing LLM Module

The router is independent of `ragstack.llm` but can be integrated:

```python
from ragstack import llm, retrieve
from ragstack.router import ModelRouter, preset_anthropic_only
from ragstack.metrics import record_model_request, record_model_response

def answer_with_routing(question: str, **kwargs):
    """Answer using router to select model."""
    # Retrieve context
    hits = retrieve.search(question)
    if not hits:
        return llm.AnswerResult(
            answer="No context found",
            hits=[],
            model="none",
            stop_reason="no_context",
        )

    # Route based on complexity + context
    router = ModelRouter(preset_anthropic_only())
    context_chars = sum(len(h.text) for h in hits)
    decision = router.route(question, context_chars=context_chars)

    # Call LLM with selected model
    start_time = record_model_request(decision.model.name)
    try:
        result = llm.answer(
            question,
            model=decision.model.name,
            **kwargs,
        )
        return result
    finally:
        record_model_response(
            decision.model.name,
            start_time,
            input_tokens=result.usage.get("input_tokens", 0),
            output_tokens=result.usage.get("output_tokens", 0),
            cost=decision.estimated_cost or 0.0,
        )
```

## Testing & Validation

```python
# Test complexity estimation accuracy
from ragstack.router import estimate_complexity

test_cases = [
    ("What time is it?", 10, 30),           # Expected: 10-30
    ("Explain neural networks", 40, 60),    # Expected: 40-60
    ("Deep analysis of...", 70, 100),       # Expected: 70-100
]

for query, min_complexity, max_complexity in test_cases:
    score = estimate_complexity(query)
    assert min_complexity <= score <= max_complexity, f"Failed for: {query}"
```

## Performance Considerations

- **Complexity estimation**: O(n) where n = question length (negligible, <1ms)
- **Routing decision**: O(1) tier selection
- **Metrics recording**: O(1) increments with minimal memory
- **No network overhead**: All routing is local, no external calls

## Production Deployment

### Docker Compose Example

```yaml
services:
  router:
    build: .
    ports:
      - "8000:8000"
    environment:
      ANTHROPIC_API_KEY: ${ANTHROPIC_API_KEY}
    command: uvicorn ragstack.metrics_server:app --host 0.0.0.0

  prometheus:
    image: prom/prometheus
    ports:
      - "9090:9090"
    volumes:
      - ./prometheus.yml:/etc/prometheus/prometheus.yml
    command:
      - "--config.file=/etc/prometheus/prometheus.yml"

  grafana:
    image: grafana/grafana
    ports:
      - "3000:3000"
    depends_on:
      - prometheus
```

### Prometheus Config

```yaml
global:
  scrape_interval: 15s

scrape_configs:
  - job_name: 'ragstack-router'
    static_configs:
      - targets: ['localhost:8000']
    metrics_path: '/metrics'
```

## Troubleshooting

### High cost unexpectedly

1. Check complexity scores: `GET /router/estimate?question=...`
2. Review routing decisions: `GET /router/stats`
3. Lower complexity thresholds to route more to cheap models

### Wrong model selected

1. Verify complexity scoring matches your expectations
2. Custom `ComplexityEstimator` if heuristics don't fit
3. Use `force_tier` parameter to validate behavior

### Missing imports

```bash
# Install all dependencies
pip install -e ".[router]"

# Verify installation
python -c "from ragstack.router import ModelRouter; print('OK')"
```

## Examples

Run all examples:

```python
from ragstack.router_example import main
main()
```

Or individually:

```python
from ragstack.router_example import (
    example_basic_routing,
    example_cost_tracking,
    example_fastapi_server,
)

example_basic_routing()
example_cost_tracking()
example_fastapi_server()
```

## API Reference

See docstrings in:
- `ragstack.router.ModelRouter` - Main routing class
- `ragstack.router.ComplexityEstimator` - Query complexity estimation
- `ragstack.metrics.MetricsCollector` - Prometheus metrics
- `ragstack.metrics_server` - FastAPI endpoints

## License

Same as RAGStack.

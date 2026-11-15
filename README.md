# Cost-Optimized LLM Model Router

Routes every query to the cheapest LLM that can handle it. A local complexity analyzer scores each query from 0 to 100 and sends it to a cheap, medium or expensive model tier, while Prometheus metrics track spend in real time.

**Stack:** Python · FastAPI · Prometheus · Anthropic · OpenRouter · Ollama · LiteLLM · pytest

## Features

- **Complexity estimation** based on length, reasoning keywords, structure and context size
- **Three-tier routing** (cheap / medium / expensive) with configurable thresholds
- **Multi-provider support:** Anthropic, OpenRouter, local Ollama, or any LiteLLM provider
- **Budget enforcement** with daily and per-query limits
- **Cost tracking:** per-query cost estimates and cumulative spend as Prometheus counters, histograms and gauges
- **FastAPI server** exposing `/metrics` and `/router/*` endpoints
- **Zero network overhead:** the routing decision is made locally

## Files

| File | Purpose |
|---|---|
| `router.py` | Complexity scoring and model selection |
| `metrics.py` | Prometheus metrics collection |
| `metrics_server.py`, `metrics_server_main.py` | FastAPI metrics and routing server |
| `router_example.py` | Eight runnable usage examples |
| `tests/test_router.py` | pytest suite |

## Quick start

```python
from router import ModelRouter, preset_anthropic_only

router = ModelRouter(preset_anthropic_only())
decision = router.route("What is machine learning?")
print(decision.model.name, decision.complexity_score, decision.estimated_cost)
```

```bash
pytest tests/
```

See `ROUTER_GUIDE.md` for the full API and `ROUTER_INTEGRATION_EXAMPLE.md` for integration patterns.

Part of the larger [RAGStack platform](https://github.com/bvenkatesulu909/Agentic-Automation-Pipeline).

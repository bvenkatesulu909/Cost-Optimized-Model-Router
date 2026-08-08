# 🚀 Getting Started with the Cost-Optimized Model Router

Your cost-optimized model router is ready to use! This document gets you running in 5 minutes.

## ⚡ Quick Start (5 minutes)

### 1. Verify Installation

```bash
python verify_router_installation.py
```

You should see:
```
✓ Python 3.11 OK
✓ Core router module
✓ Prometheus metrics module
✓ FastAPI server module
✓ All checks passed! Router is ready to use.
```

### 2. Basic Usage (30 seconds)

```python
from ragstack.router import ModelRouter, preset_anthropic_only

# Create router
router = ModelRouter(preset_anthropic_only())

# Route a query
decision = router.route("What is machine learning?")

print(f"Model: {decision.model.name}")           # claude-3-5-haiku-20241022
print(f"Tier: {decision.model.tier.value}")      # cheap
print(f"Complexity: {decision.complexity_score}") # ~25/100
print(f"Cost: ${decision.estimated_cost:.6f}")   # ~$0.001234
```

### 3. Run All Examples (2 minutes)

```bash
python -m ragstack.router_example
```

This runs 8 complete examples:
- ✓ Basic routing
- ✓ Context-aware routing  
- ✓ Forced tier routing
- ✓ Multi-provider routing
- ✓ Cost tracking
- ✓ Prometheus metrics
- ✓ FastAPI server
- ✓ Async request tracking

### 4. Start Metrics Server (1 minute)

```bash
# Terminal 1: Start the server
python -m ragstack.metrics_server_main

# Terminal 2: Try some requests
curl http://localhost:8000/health
curl "http://localhost:8000/router/estimate?question=What%20is%20AI?"
curl "http://localhost:8000/router/route?question=Explain%20quantum%20mechanics"
curl http://localhost:8000/router/stats
curl http://localhost:8000/metrics
```

Expected output from route query:
```json
{
  "model": "claude-3-5-haiku-20241022",
  "tier": "cheap",
  "complexity": 25,
  "estimated_cost_usd": 0.001234,
  "reasoning": "Complexity 25 < 40"
}
```

## 📖 Learning Path

Pick your level:

### Beginner (Start Here)
1. **Read**: [ROUTER_README.md](./ROUTER_README.md) (10 min)
   - Overview and key concepts
   - Quick start and examples
   - Common use cases

2. **Do**: Run examples
   ```bash
   python -m ragstack.router_example
   ```

3. **Try**: Basic integration
   ```python
   from ragstack.router import estimate_complexity
   score = estimate_complexity("Your question")
   print(f"Complexity: {score}/100")
   ```

### Intermediate (Next Level)
1. **Read**: [ROUTER_GUIDE.md](./ROUTER_GUIDE.md) (30 min)
   - Architecture details
   - Complete API reference
   - Configuration options
   - Advanced features

2. **Do**: Integrate with your project
   ```bash
   # See ROUTER_INTEGRATION_EXAMPLE.md for patterns
   ```

3. **Try**: Start metrics server
   ```bash
   python -m ragstack.metrics_server_main
   ```

### Advanced (Production)
1. **Read**: [ROUTER_INTEGRATION_EXAMPLE.md](./ROUTER_INTEGRATION_EXAMPLE.md) (20 min)
   - Real-world integration patterns
   - Multi-provider setup
   - Prometheus + Grafana setup
   - Cost analysis scripts

2. **Do**: Set up monitoring
   ```bash
   # See docker-compose example in ROUTER_INTEGRATION_EXAMPLE.md
   ```

3. **Deploy**: Production deployment
   - Docker setup
   - Kubernetes manifests
   - Load balancing and scaling

## 🎯 Common Tasks

### I want to reduce LLM costs

```python
from ragstack.router import ModelRouter, preset_anthropic_only

# Automatically routes simple queries to cheap models
router = ModelRouter(preset_anthropic_only())

# Simple query → cheap model ($0.0008/1k tokens)
decision = router.route("What time is it?")
print(decision.model.name)  # claude-3-5-haiku-20241022

# Complex query → expensive model ($0.015/1k tokens)
decision = router.route("Deep analysis of quantum computing")
print(decision.model.name)  # claude-3-opus-20250219

# Expected savings: 70-85% cost reduction
```

### I want to integrate with my RAG pipeline

```python
from ragstack import retrieve
from ragstack.router import ModelRouter, preset_anthropic_only

question = "Your question"
hits = retrieve.search(question)

# Route based on complexity + context
router = ModelRouter(preset_anthropic_only())
context_chars = sum(len(h.text) for h in hits)
decision = router.route(question, context_chars=context_chars)

# Use the selected model
result = llm.answer(question, model=decision.model.name)
```

### I want to monitor costs in real-time

```bash
# Start the server
python -m ragstack.metrics_server_main

# Access Prometheus metrics
curl http://localhost:8000/metrics

# Check statistics
curl http://localhost:8000/router/stats

# Example output:
# {
#   "queries_routed": 427,
#   "estimated_daily_spend": 18.42,
#   "cheap_models": 1,
#   "medium_models": 1,
#   "expensive_models": 1
# }
```

### I want to use different models

```python
from ragstack.router import RouterConfig, ModelConfig, ModelTier, ModelRouter

config = RouterConfig(
    cheap_models=[
        ModelConfig(
            name="openrouter/openchat-3.5",
            tier=ModelTier.CHEAP,
            cost_per_1k_input=0.000011,
            cost_per_1k_output=0.000011,
        ),
    ],
    medium_models=[
        ModelConfig(
            name="openrouter/mixtral-8x7b",
            tier=ModelTier.MEDIUM,
            cost_per_1k_input=0.00024,
            cost_per_1k_output=0.00024,
        ),
    ],
    expensive_models=[
        ModelConfig(
            name="claude-3-5-sonnet-20241022",
            tier=ModelTier.EXPENSIVE,
            cost_per_1k_input=0.003,
            cost_per_1k_output=0.015,
        ),
    ],
)

router = ModelRouter(config)
decision = router.route("Your question")
```

### I want to set budget limits

```python
from ragstack.router import RouterConfig, preset_anthropic_only

config = preset_anthropic_only()
config.daily_budget_usd = 100.0    # Stop after $100/day
config.query_budget_usd = 0.50      # Reject queries over $0.50

router = ModelRouter(config)
decision = router.route(question)

if decision.estimated_cost > config.query_budget_usd:
    print(f"Query over budget: ${decision.estimated_cost:.2f}")
else:
    # Safe to route
    pass
```

### I want to run tests

```bash
# Install test dependencies
pip install pytest

# Run all tests
pytest tests/test_router.py -v

# Run specific test
pytest tests/test_router.py::TestComplexityEstimation -v

# Generate coverage report
pytest tests/test_router.py --cov=ragstack.router --cov-report=html
open htmlcov/index.html
```

## 📊 What Gets Tracked

Every routing decision is tracked:

```
Query Complexity          → ragstack_query_complexity
Routing Decisions         → ragstack_router_{cheap,medium,expensive}_total
Cost Estimation          → ragstack_estimated_cost_total_usd
Request Latency          → ragstack_request_latency_seconds
Token Usage              → ragstack_tokens_{input,output}
Per-Model Performance    → ragstack_model_{latency,tokens}
```

Export and visualize:
```bash
# Export to file
curl http://localhost:8000/metrics > metrics.txt

# Import into Prometheus
# (See ROUTER_INTEGRATION_EXAMPLE.md for Grafana setup)
```

## 🔍 Troubleshooting

### "Module not found" error

```bash
# Make sure router dependencies are installed
pip install -e ".[router]"

# Verify installation
python verify_router_installation.py
```

### Router selects wrong model

```python
# Check complexity score
from ragstack.router import estimate_complexity
score = estimate_complexity("Your query")
print(f"Complexity: {score}/100")

# Compare against thresholds
print(f"Cheap threshold: 40")
print(f"Medium threshold: 70")

# If score is wrong, create custom estimator (see ROUTER_GUIDE.md)
```

### Metrics not showing up

```bash
# Check server is running
curl http://localhost:8000/health

# Check metrics endpoint
curl http://localhost:8000/metrics | head -20

# Check if records exist
curl http://localhost:8000/router/stats
```

### FastAPI import error

```bash
# Install optional dependencies
pip install -e ".[router]"

# Verify
python -c "import fastapi, uvicorn; print('OK')"
```

## 📚 Files & Their Purpose

| File | What It Does | When To Read |
|------|-------------|--------------|
| ROUTER_README.md | Overview and quick start | First thing |
| ROUTER_GUIDE.md | Complete API reference | Deep dive |
| ROUTER_INTEGRATION_EXAMPLE.md | Integration patterns | Before integrating |
| START_ROUTER.md | This file! Quick reference | When getting started |
| router_example.py | 8 working examples | When learning by example |
| verify_router_installation.py | Installation checker | After install |

## 🎓 Examples

8 complete examples are included in `router_example.py`:

1. **Basic Routing** - Simple complexity-based routing
2. **Context-Aware** - Routing with retrieved context size
3. **Forced Tier** - Override routing for testing
4. **Multi-Provider** - Route across different providers
5. **Cost Tracking** - Accumulate and monitor spend
6. **Prometheus** - Export metrics in Prometheus format
7. **FastAPI** - HTTP server endpoints
8. **Async Tracking** - Track requests with metrics

Run all:
```bash
python -m ragstack.router_example
```

Or run specific example:
```python
from ragstack.router_example import example_basic_routing
example_basic_routing()
```

## 🚀 Next Steps

1. ✅ Install: `pip install -e ".[router]"`
2. ✅ Verify: `python verify_router_installation.py`
3. ✅ Learn: Read [ROUTER_README.md](./ROUTER_README.md)
4. ✅ Try: `python -m ragstack.router_example`
5. ✅ Integrate: See [ROUTER_INTEGRATION_EXAMPLE.md](./ROUTER_INTEGRATION_EXAMPLE.md)
6. ✅ Monitor: `python -m ragstack.metrics_server_main`
7. ✅ Deploy: Set up Prometheus/Grafana (see guide)

## 💬 Quick Reference

**Estimate complexity:**
```python
from ragstack.router import estimate_complexity
score = estimate_complexity("Your question")
```

**Create router:**
```python
from ragstack.router import ModelRouter, preset_anthropic_only
router = ModelRouter(preset_anthropic_only())
```

**Route query:**
```python
decision = router.route("Your question", context_chars=12345)
```

**Get metrics:**
```python
from ragstack.metrics import get_prometheus_text
text = get_prometheus_text()
```

**Start server:**
```bash
python -m ragstack.metrics_server_main
curl http://localhost:8000/router/stats
```

---

**Ready to get started?** Pick one:

- 📖 Read [ROUTER_README.md](./ROUTER_README.md) for overview
- 🔨 Run `python -m ragstack.router_example` for examples
- 🚀 Start `python -m ragstack.metrics_server_main` to see it in action
- 📋 See [ROUTER_INTEGRATION_EXAMPLE.md](./ROUTER_INTEGRATION_EXAMPLE.md) to integrate

Happy routing! 🎯

"""Entry point for running the metrics server with a pre-configured router.

Usage:
    # Install dependencies
    pip install -e ".[router]"

    # Run server
    python -m ragstack.metrics_server_main

    # Or with uvicorn directly
    uvicorn ragstack.metrics_server:create_app --port 8000 --reload
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    import uvicorn
except ImportError:
    print("Error: uvicorn not installed. Install with: pip install -e '.[router]'")
    sys.exit(1)

from .metrics_server import create_metrics_app
from .router import preset_anthropic_only


def main():
    """Run the metrics server."""
    # Create router with default configuration
    config = preset_anthropic_only()

    from .router import ModelRouter
    router = ModelRouter(config)

    # Create FastAPI app
    app = create_metrics_app(router)

    # Print startup info
    print("\n" + "=" * 60)
    print("RAGStack Model Router Metrics Server")
    print("=" * 60)
    print(f"Router Configuration: {len(config.cheap_models)} cheap, "
          f"{len(config.medium_models)} medium, "
          f"{len(config.expensive_models)} expensive models")
    print("\nEndpoints:")
    print("  GET /health              - Health check")
    print("  GET /metrics             - Prometheus metrics")
    print("  GET /router/estimate     - Estimate query complexity")
    print("  GET /router/route        - Route query to best model")
    print("  GET /router/models       - List configured models")
    print("  GET /router/config       - Show configuration")
    print("  GET /router/stats        - Show statistics")
    print("\nExample requests:")
    print("  curl http://localhost:8000/health")
    print("  curl 'http://localhost:8000/router/estimate?question=What%20is%20AI?'")
    print("  curl 'http://localhost:8000/router/route?question=Explain%20quantum%20mechanics'")
    print("\nStarting server at http://localhost:8000")
    print("Press Ctrl+C to stop")
    print("=" * 60 + "\n")

    # Run server
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )


if __name__ == "__main__":
    main()

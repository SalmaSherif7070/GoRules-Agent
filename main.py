"""
main.py
--------
Entry point for the GoRules Compiler Agent.

Runs TWO interfaces on the same server:
  1. REST API (FastAPI)  →  /api/*     (test via Swagger at /docs)
  2. MCP Server          →  /mcp/*     (for AI assistants like Claude Desktop)

Usage:
    python main.py                  # HTTP server (REST + MCP) — default
    python main.py --stdio          # stdio — for Claude Desktop / MCP CLI
"""

import argparse
import logging
import sys

from dotenv import load_dotenv

load_dotenv()  # Must come before any config/ import

from config import settings  # noqa: E402  (after load_dotenv)
from mcp_server.server import mcp  # noqa: E402


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="GoRules Compiler — MCP Server + REST API"
    )
    parser.add_argument(
        "--stdio",
        action="store_true",
        help="Use stdio transport instead of HTTP (for Claude Desktop / MCP CLI)",
    )
    parser.add_argument(
        "--host",
        default=settings.mcp_server_host,
        help=f"HTTP host (default: {settings.mcp_server_host})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=settings.mcp_server_port,
        help=f"HTTP port (default: {settings.mcp_server_port})",
    )
    args = parser.parse_args()

    use_stdio = args.stdio or settings.mcp_transport.lower() == "stdio"

    if use_stdio:
        logger.info("Starting MCP server — transport: stdio")
        mcp.run(transport="stdio")
    else:
        # --- Build FastAPI app with REST endpoints + MCP mounted together ---
        import uvicorn
        from fastapi import FastAPI
        from api.routes import router as api_router

        app = FastAPI(
            title="GoRules Compiler Agent",
            description=(
                "AI-powered business rule validation engine.\n\n"
                "- **REST API** (`/api/*`): Test endpoints via this Swagger UI\n"
                "- **MCP Server** (`/mcp`): Connect AI assistants (Claude Desktop, etc.)\n\n"
                "The agent uses Gemini to compile business rules into executable "
                "GoRules decision-table JSON, then validates INSERT/UPDATE operations."
            ),
            version="1.0.0",
        )

        # Mount REST API routes
        app.include_router(api_router)

        # Mount MCP server at /mcp so AI clients can connect
        app.mount("/mcp", mcp.sse_app())

        logger.info(
            "Starting server — http://%s:%d",
            args.host, args.port,
        )
        logger.info("  REST API  →  http://%s:%d/docs", args.host, args.port)
        logger.info("  MCP (SSE) →  http://%s:%d/mcp/sse", args.host, args.port)

        uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
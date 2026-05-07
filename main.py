import argparse
import logging
from dotenv import load_dotenv

load_dotenv()

from config import settings
from api.routes import router as api_router
from api.gorules_generator import router as gorules_router
from api.gorules_ui import router as ui_router

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s  %(levelname)-8s  %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")


def main():
    parser = argparse.ArgumentParser(description="GoRules Compiler — REST API")
    parser.add_argument("--host", default=settings.mcp_server_host)
    parser.add_argument("--port", type=int, default=settings.mcp_server_port)
    args = parser.parse_args()

    import uvicorn
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import RedirectResponse

    app = FastAPI(
        title="GoRules Compiler Agent",
        description="AI-powered business rule validation engine.",
        version="1.0.0",
    )

    # CORS — required so the GoRules editor (different port) can call this API
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],          # tighten in production
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/", include_in_schema=False)
    async def root():
        return RedirectResponse(url="/docs")

    app.include_router(api_router)
    app.include_router(gorules_router)
    app.include_router(ui_router)                       # ← new

    logger.info("REST API → http://%s:%d/docs", args.host, args.port)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
"""Flask application factory and entry point."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from flask import Flask, send_from_directory
from flask_cors import CORS

from backend.api.routes import bp as api_bp
from backend.core.config import Settings, get_settings
from backend.core.logging import configure_logging, get_logger
from backend.infra.bitcoin.rpc import BitcoinRPCClient
from backend.infra.indexer.client import IndexerClient
from backend.infra.ipfs.base import IPFSBackend
from backend.infra.ipfs.factory import get_ipfs_backend

logger = get_logger(__name__)

_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@dataclass(frozen=True)
class Runtime:
    """Dependency container passed to blueprints via ``app.config['RUNTIME']``."""

    rpc_client: BitcoinRPCClient
    indexer_client: IndexerClient
    ipfs_backend: IPFSBackend


def create_app(settings: Settings | None = None) -> Flask:
    """Build a Flask app with the configured runtime dependencies."""
    if settings is None:
        settings = get_settings()

    configure_logging()

    app = Flask(
        __name__,
        static_folder=str(_FRONTEND_DIR),
        static_url_path="",
    )
    app.config["SETTINGS"] = settings
    app.config["RUNTIME"] = Runtime(
        rpc_client=BitcoinRPCClient(settings.bitcoin),
        indexer_client=IndexerClient(settings.indexer),
        ipfs_backend=get_ipfs_backend(settings.ipfs),
    )

    if settings.cors_origins:
        CORS(app, origins=settings.cors_origins)

    app.register_blueprint(api_bp)

    _register_frontend_routes(app)
    return app


def _register_frontend_routes(app: Flask) -> None:
    """Serve the static frontend files (index.html, result.html, js/, etc.)."""

    @app.get("/")
    def serve_index():
        return send_from_directory(_FRONTEND_DIR, "index.html")

    @app.get("/result.html")
    def serve_result():
        return send_from_directory(_FRONTEND_DIR, "result.html")


def main() -> None:
    """CLI entry point (``python -m backend.main``)."""
    settings = get_settings()
    app = create_app(settings)
    app.run(
        host=settings.flask_host,
        port=settings.flask_port,
        debug=settings.flask_debug,
    )


if __name__ == "__main__":
    main()
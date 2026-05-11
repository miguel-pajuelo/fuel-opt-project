"""Project entrypoint and compatibility exports.

The implementation has been split into app modules; this file re-exports the
old public names so existing imports keep working. Running this file starts
the web API by default; pass --legacy-cli to run the old Ballenoil-only flow.
"""

from app.legacy_cli.runtime import *
from app.legacy_cli.ballenoil import *
from app.legacy_cli.minetur import *
from app.legacy_cli.scraper import *
from app.legacy_cli.routing import *
from app.legacy_cli.optimizer import *
from app.legacy_cli.cli import *


def run_web_api(host: str = "127.0.0.1", port: int = 8000, reload: bool = False) -> None:
    try:
        import uvicorn
    except ImportError as exc:
        raise SystemExit(
            "Missing web dependency 'uvicorn'. Install it with: pip install -r requirements-web.txt"
        ) from exc

    print("Starting Fuel Optimizer API")
    print(f"  Docs   : http://{host}:{port}/docs")
    print(f"  Health : http://{host}:{port}/health")
    print("  Legacy : python main.py --legacy-cli")
    uvicorn.run("app.api.main:app", host=host, port=port, reload=reload)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Fuel Optimizer project entrypoint.")
    parser.add_argument(
        "--legacy-cli",
        action="store_true",
        help="Run the old Ballenoil-only interactive CLI.",
    )
    parser.add_argument("--host", default="127.0.0.1", help="API host when running the web backend.")
    parser.add_argument("--port", type=int, default=8000, help="API port when running the web backend.")
    parser.add_argument("--reload", action="store_true", help="Enable uvicorn reload for development.")
    args = parser.parse_args()

    if args.legacy_cli:
        run_cli()
        return
    run_web_api(host=args.host, port=args.port, reload=args.reload)


if __name__ == "__main__":
    main()

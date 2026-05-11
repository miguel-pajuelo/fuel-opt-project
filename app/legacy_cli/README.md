# Legacy CLI Package

This package contains the former `main.py` implementation split by responsibility.
`main.py` is now only a compatibility entrypoint that re-exports these modules and
calls `run_cli()` when executed directly.

## Modules

- `runtime.py`: constants, data classes, terminal spinner, text/date/JSON/cache helpers and numeric parsing.
- `ballenoil.py`: Ballenoil HTML fetching and station/detail parsing.
- `minetur.py`: MINETUR and Geoportal WFS fetching, parsing and Ballenoil-to-MINETUR matching.
- `scraper.py`: legacy end-to-end scraping pipeline and final TXT cache read/write.
- `routing.py`: OpenRouteService matrix call used by the legacy optimizer.
- `optimizer.py`: route-cost ranking, Pareto frontier, epsilon winner and comparison table rendering.
- `cli.py`: interactive CLI prompts and result printing.

## Migration Status

The split is intentionally compatibility-first. Some modules still import upstream
legacy namespace with star imports to avoid a risky behavioral rewrite in the same
step. The next cleanup should replace those transitional imports with explicit
imports and move reusable pieces into the web-oriented `app` package where possible.

# AGENTS.md

This file provides guidance to WARP (warp.dev) when working with code in this repository.

## Project Overview

AbraFlexi MCP Server — a Python MCP (Model Context Protocol) server that exposes AbraFlexi (Czech ERP/accounting) REST API operations as MCP tools via [FastMCP](https://github.com/jlowin/fastmcp). It uses [python-abraflexi](https://github.com/VitexSoftware/python-abraflexi) as the API client library.

## Build & Run Commands

```bash
# Install from PyPI (production)
pip install abraflexi-mcp-server
abraflexi-mcp

# Install dependencies for development
uv sync

# Run the MCP server (stdio transport, default)
uv run python scripts/start_server.py

# Run directly without startup validation
uv run python -m abraflexi_mcp_server.server

# Run tests (tool registration + AbraFlexi connection)
uv run python scripts/test_server.py

# Live capability scenario against a real company
python tests/live_capability_scenario.py \
  --url "$ABRAFLEXI_URL" --company "$ABRAFLEXI_COMPANY" \
  --login "$ABRAFLEXI_LOGIN" --password "$ABRAFLEXI_PASSWORD"

# Build PyPI package
python3 -m build
python3 -m twine upload dist/*

# Build Debian package
dpkg-buildpackage -us -uc -b
```

There is no linter, formatter, or type-checker configured. Functional tests are
`scripts/test_server.py` and `tests/live_capability_scenario.py` (run as scripts,
not via pytest).

## Architecture

### Single-module server

All MCP tool definitions and the server entry point live in one file: `abraflexi_mcp_server/server.py`. The module-level `mcp = FastMCP(...)` instance collects tools via `@mcp.tool()` decorators. The `main()` function at the bottom selects transport (stdio or streamable-http) based on environment variables.

### Tool pattern

Every tool follows the same pattern:
1. Read tools create a `ReadOnly` client for a specific AbraFlexi *evidence* (e.g. `faktura-vydana`, `adresar`, `cenik`, `banka`).
2. Write tools call `validate_read_only()` first (raises `ValueError` if `READ_ONLY=true`), then use a `ReadWrite` client.
3. All tools return `format_response(...)` which JSON-serializes the result.

Typed tools with domain-specific CRUD: `invoice_issued_*`, `invoice_received_*`, `contact_*`, `product_*`, `bank_transaction_*`.
Generic tools for any evidence: `evidence_get`, `evidence_create`, `evidence_update`, `evidence_delete`, `evidence_list`.

### Configuration

All config comes from environment variables (loaded from `.env` via `python-dotenv`). Key vars:
- `ABRAFLEXI_URL`, `ABRAFLEXI_COMPANY` — required
- `ABRAFLEXI_LOGIN` / `ABRAFLEXI_PASSWORD` or `ABRAFLEXI_AUTHSESSID` — auth
- `READ_ONLY` — defaults to `true`; controls whether write tools are allowed
- `ABRAFLEXI_MCP_TRANSPORT` — `stdio` (default) or `streamable-http`
- `DEBUG` — enables verbose logging

### Entry points

- `abraflexi-mcp` console script → `abraflexi_mcp_server.server:main` (defined in pyproject.toml)
- `scripts/start_server.py` — validates env, prints config summary, then calls `server.main()`
- `scripts/test_server.py` — tests tool registration signatures and live AbraFlexi connectivity

### Debian packaging

The `debian/` directory contains full Debian packaging. `debian/rules` uses pybuild and installs scripts to `/usr/bin/abraflexi-mcp-{start,test}`. CI builds via `debian/Jenkinsfile` across multiple Debian/Ubuntu distros and publishes to Aptly.

### PyPI Distribution

The package is published on PyPI at https://pypi.org/project/abraflexi-mcp-server/. Users can install with `pip install abraflexi-mcp-server` and run with the `abraflexi-mcp` command.

### Dependency note

`requirements.txt` lists the same dependencies as `pyproject.toml`. For development use `uv sync` which resolves from pyproject.toml (`python-abraflexi>=1.0.0` from PyPI).

## AbraFlexi domain concepts

- **Evidence** = a data entity/table in AbraFlexi (e.g. `faktura-vydana` = issued invoices, `adresar` = contacts, `cenik` = products, `banka` = bank transactions).
- Records are identified by numeric `id` or string `kod` (code). When using `kod`, the API expects `code:VALUE` format.
- Filter expressions use AbraFlexi's own syntax (e.g. `datVyst >= '2024-01-01'`, `nazev like '*text*'`).
- `detail` parameter controls response verbosity: `id`, `summary`, `full`, or `custom:field1,field2`.

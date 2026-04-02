# Implementation Plan: Migrate MCP from SSE/HTTP FastMCP to Local stdio MCP

## 1. Objective

Migrate the existing Parsival MCP service from the current hosted FastMCP SSE/HTTP transport pattern to a local stdio-based MCP implementation (similar conceptual style to paperstack local MCP usage) while preserving application behavior and tool coverage.

- **Current state**: FastMCP + sse transport in `src/app.py`
- **Target state**: standard local MCP over stdio using an MCP server process launched locally (no HTTP transport layer)
- **Deliverable**: planning document only (`implementation_plan.md`)

---

## 2. Current State Assessment

### 2.1 Entry points

- `src/app.py` defines FastMCP instance:
  - `mcp = FastMCP("Parsival", version="0.1.0")`
- Tools registered via:
  - `@mcp.tool()` decorators on functions:
    - `read_file`, `get_metadata`, `extract_table`, `extract_images`, `search_file`, `convert_to_markdown`, `list_supported_formats`
- Startup hook:
  - `_startup()` to initialize `cache_store`
  - `@mcp.on_startup` may not be available in current version (warning shown)

### 2.2 Transport layer (SSE/HTTP)

- Docker and `.vscode/mcp.json` run:
  - `fastmcp run src/app.py:mcp --transport sse`
- Server log:
  - FastMCP initializes and `Uvicorn running on http://0.0.0.0:6969`
- SSE context:
  - `SseServerTransport` in mcp package
  - MCP client currently attempts `http://127.0.0.1:6969/sse`, may fail protocol mismatch/disconnect

### 2.3 FastMCP-specific dependencies

- `requirements.txt` includes `fastmcp`
- `src/app.py` imports `from fastmcp import FastMCP`
- FastMCP orchestrates tool metadata + routes

### 2.4 Request/response flow

- FastMCP manages MCP protocol over SSE
- MCP lifecycle: client init -> tool list -> tool call (JSON-RPC over SSE)
- Mediated by FastMCP settings and SseServerTransport / FastMCP `on_startup` + tool registry

### 2.5 Config/env dependencies

- `.vscode/mcp.json` env:
  - `PYTHONUNBUFFERED`, `PYTHONPATH`, `MCP_WORKSPACE_ROOT`, `MCP_ALLOWED_DIRECTORIES`
  - `FASTMCP_SERVER_HOST`, `FASTMCP_SERVER_PORT` configured
- `src/config.py` handles `MCP_*` via pydantic-settings
- docker `compose` + Dockerfile set runtime env

### 2.6 Hosted-server assumptions not local-style

- FastMCP assumes HTTP host/port globally, path-based routes (`/sse`, `/messages`)
- local stdio does not need ports or network stack

---

## 3. Target Architecture

### 3.1 Local stdio MCP behavior

- Launched server reading/writing JSON over stdio (stdin/stdout)
- No HTTP URL/port requirement
- MCP session via the existing process pipeline
- Tool registration unchanged logically
- Startup via `initialize` on stdio pipeline

### 3.2 FastMCP-hosted vs stdio local comparison

| Concern | FastMCP (current) | stdio local target |
|--------|-------------------|--------------------|
| Transport | SSE/HTTP network | stdio stream/process |
| Entry point | `fastmcp run ...` | `mcp stdio` or direct server module |
| Deployment | container+ports | local process, dev/testing link |
| Scaling | network multi-client | single local client |
| Complexity | router, HTTP layers | thin stdio handling |

### 3.3 Reference paperstack

- paperstack likely uses `mcp.server.stdio` or `mcp.client.stdio`.
- Need verification; use as reference pattern not exact impl structures.

---

## 4. Gap Analysis

### 4.1 Transport changes

- Replace FastMCP SSE with stdio server mode
- Update transport client paths

### 4.2 Server bootstrap changes

- `mcp = FastMCP(...)` replaced with stdio server init
- tool registration should be same where possible

### 4.3 Dependency changes

- remove/replace `fastmcp` requirement
- keep `mcp` and relevant packages

### 4.4 Configuration changes

- drop `FASTMCP_SERVER_*` for set up
- keep `MCP_ALLOWED_DIRECTORIES`, `MCP_WORKSPACE_ROOT`

### 4.5 Startup/runtime changes

- no HTTP ports; stdio-based process in extension or local subprocess

### 4.6 Development workflow

- change from `docker compose up` to `python -m ...` or `docker run ...` stdio

### 4.7 Testing/packaging

- add stdio-based integration tests
- remove HTTP health tests if any

---

## 5. Proposed Migration Steps

### 5.1 Discover stdio APIs

- inspect mcp package for `mcp.server.stdio` and `mcp.client.stdio`.
- verify IO semantics and tool connector patterns.

### 5.2 Create stdio server module

- add `src/mcp_stdio.py` with initialization / run path
- route tools into stdio MCP bridge

### 5.3 Reuse tool definitions

- keep `src/app.py` tool functions, optionally mirror in stdio mode

### 5.4 Update Docker runtime

- CMD to run stdio mode via project image

### 5.5 Update VS Code config

- .vscode/mcp.json command to run stdio client or local process.

### 5.6 Compatibility flag

- set `MCP_TRANSPORT={fastmcp,stdio}` to allow rollbacks

### 5.7 Cleanup

- remove FastMCP code if migrated cleanly

---

## 6. Risks and Mitigations

- protocol mismatch: test with stubs + paperstack patterns
- client ceremony differences: adjust training docs
- lifecycle edge cases: add graceful shutdown handlers
- logging visibility: keep structured stderr logs

---

## 7. Validation Plan

- manual: connect stdio client, call `list_supported_formats`, `read_file`
- unit tests: add `tests/test_mcp_stdio.py`
- smoke tests: `scripts/tool_smoke_test_stdio.py`
- regression: ensure same tool behavior across transports

---

## 8. Out of Scope

- no parser/tool behavior changes
- no deployment pipeline overhaul
- no new feature additions

---

## 9. Assumptions / Open Questions

- Assumption: `mcp` stdio API available from installed package.
- Assumption: `@mcp.tool` decorator is compatible with stdio server registration.
- Needs Verification: exact local stdio entrypoint in paperstack.
- Needs Verification: final desired endpoint path for client (e.g., "/sse" vs "/").

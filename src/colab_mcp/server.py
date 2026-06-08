from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
from typing import Callable, Literal

import nbformat
from mcp.server.fastmcp import Context, FastMCP

from .drive import DriveNotebookClient
from .notebooks import NotebookStore, normalize_colab_notebook

ROOT = Path(os.environ.get("COLAB_MCP_ROOT", Path.cwd()))
CREDENTIALS = Path(
    os.environ.get("COLAB_MCP_GOOGLE_CREDENTIALS", "~/.config/colab-mcp/credentials.json")
)
TOKEN = Path(os.environ.get("COLAB_MCP_GOOGLE_TOKEN", "~/.config/colab-mcp/token.json"))

store = NotebookStore(ROOT)
drive = DriveNotebookClient(CREDENTIALS, TOKEN)
MCP_INSTRUCTIONS = """
This server synchronizes and edits .ipynb notebook files. It is not a notebook
execution service. Never represent its tools as running projects, executing
cells, connecting to Google Colab runtimes, automating the Colab browser,
keeping sessions alive, or bypassing Colab limits. Use pull_drive_notebook and
push_local_notebook only to synchronize files. get_colab_url only returns a
URL; it does not open a browser. Ask before overwriting an existing Drive file.
Use get_google_drive_status before suggesting authorization troubleshooting.
Transfer tools report progress when the MCP client supplies a progress token.
Drive metadata can show synchronization state, but cannot show whether a Colab
runtime is currently executing the notebook.
""".strip()
mcp = FastMCP("colab-drive-sync", instructions=MCP_INSTRUCTIONS)


@mcp.tool()
def list_local_notebooks(query: str = "", limit: int = 100) -> list[dict]:
    """List local .ipynb notebooks under COLAB_MCP_ROOT."""
    return store.list(query, limit)


@mcp.tool()
def get_local_notebook(
    path: str, include_source: bool = True, max_source_chars: int = 4000
) -> dict:
    """Read a local notebook summary and its cells."""
    return store.summary(path, include_source, max_source_chars)


@mcp.tool()
def create_local_notebook(path: str, title: str = "", kernel_name: str = "python3") -> dict:
    """Create a new Colab-compatible local notebook."""
    return store.create(path, title, kernel_name)


@mcp.tool()
def add_local_cell(
    path: str,
    cell_type: Literal["code", "markdown", "raw"],
    source: str,
    index: int | None = None,
) -> dict:
    """Add a cell to a local notebook."""
    return store.add_cell(path, cell_type, source, index)


@mcp.tool()
def update_local_cell(
    path: str,
    index: int,
    source: str,
    cell_type: Literal["code", "markdown", "raw"] | None = None,
) -> dict:
    """Replace a cell's source and optionally its type."""
    return store.update_cell(path, index, source, cell_type)


@mcp.tool()
def delete_local_cell(path: str, index: int) -> dict:
    """Delete a cell from a local notebook."""
    return store.delete_cell(path, index)


@mcp.tool()
def search_local_cells(path: str, query: str, case_sensitive: bool = False) -> list[dict]:
    """Search cell sources in a local notebook."""
    return store.search_cells(path, query, case_sensitive)


@mcp.tool()
def clear_local_outputs(path: str) -> dict:
    """Clear outputs and execution counts from a local notebook."""
    return store.clear_outputs(path)


@mcp.tool()
def get_google_drive_status() -> dict:
    """Check Google Drive setup and authorization without opening a browser."""
    return drive.auth_status()


@mcp.tool()
def authorize_google_drive() -> dict:
    """Open an explicit Google OAuth flow and save the resulting local token."""
    return drive.authorize()


@mcp.tool()
def list_drive_notebooks(query: str = "", limit: int = 100) -> list[dict]:
    """List synchronized notebook files visible through the configured Drive access."""
    return drive.list_notebooks(query, limit)


def _thread_progress(ctx: Context, action: str) -> Callable[[float, str], None]:
    loop = asyncio.get_running_loop()

    def report(fraction: float, message: str) -> None:
        asyncio.run_coroutine_threadsafe(
            ctx.report_progress(fraction * 100, 100, message or action), loop
        )

    return report


@mcp.tool()
async def pull_drive_notebook(file_id: str, local_path: str, ctx: Context) -> dict:
    """Synchronize a Drive notebook file into COLAB_MCP_ROOT without executing it."""
    await ctx.report_progress(0, 100, "Starting Google Drive download")
    raw_notebook = await asyncio.to_thread(
        drive.download_notebook, file_id, _thread_progress(ctx, "Downloading notebook")
    )
    normalized_outputs = normalize_colab_notebook(raw_notebook)
    notebook = nbformat.from_dict(raw_notebook)
    store.write(local_path, notebook)
    result = store.summary(local_path, include_source=False)
    result["normalized_outputs"] = normalized_outputs
    await ctx.report_progress(100, 100, "Notebook downloaded")
    return result


@mcp.tool()
async def push_local_notebook(
    local_path: str, ctx: Context, drive_name: str = "", file_id: str | None = None
) -> dict:
    """Synchronize a local notebook file to Drive without executing it."""
    notebook = store.read(local_path)
    name = drive_name or Path(local_path).name
    await ctx.report_progress(0, 100, "Starting Google Drive upload")
    result = await asyncio.to_thread(
        drive.upload_notebook,
        dict(notebook),
        name,
        file_id,
        _thread_progress(ctx, "Uploading notebook"),
    )
    await ctx.report_progress(100, 100, "Notebook uploaded")
    return result


@mcp.tool()
def get_notebook_sync_status(file_id: str, local_path: str | None = None) -> dict:
    """Compare Drive and local notebook state; cannot detect Colab runtime activity."""
    remote = drive.get_notebook_metadata(file_id)
    result = {
        "file_id": file_id,
        "drive": remote,
        "sync_state": "remote_only" if local_path is None else "unknown",
        "runtime_status": "unavailable",
        "runtime_status_message": (
            "Google Drive metadata does not expose whether a Colab runtime is "
            "connected to or executing this notebook."
        ),
    }
    if local_path is None:
        return result
    notebook = store.read(local_path)
    local_content = drive.notebook_bytes(dict(notebook))
    local_md5 = hashlib.md5(local_content).hexdigest()
    remote_md5 = remote.get("md5Checksum")
    result["local"] = {
        "path": local_path,
        "upload_size": len(local_content),
        "upload_md5": local_md5,
    }
    if remote_md5:
        result["sync_state"] = "in_sync" if remote_md5 == local_md5 else "differs"
    return result


@mcp.tool()
def copy_drive_notebook(file_id: str, name: str) -> dict:
    """Copy a notebook file in Google Drive without executing it."""
    return drive.copy_notebook(file_id, name)


@mcp.tool()
def get_colab_url(file_id: str) -> str:
    """Return a Colab URL for a Drive notebook; this does not open a browser."""
    return drive.colab_url(file_id)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()

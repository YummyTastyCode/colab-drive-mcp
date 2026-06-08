# Colab Drive MCP

An MCP server for safely inspecting, editing, and synchronizing
Google Colab-compatible `.ipynb` notebooks through Google Drive.

> [!IMPORTANT]
> **This is a notebook file synchronization server, not a notebook execution
> service.** It transfers and edits `.ipynb` files through Google Drive. It
> does not connect to Colab runtimes, execute cells, click **Run all**, keep
> sessions alive, automate the Colab browser UI, or bypass Colab limits.

Use this MCP when an AI agent needs to prepare a notebook locally, synchronize
it with Drive, inspect completed outputs, or return an edited notebook to the
user. Open and execute the synchronized notebook separately in Colab, Jupyter,
VS Code, or another notebook runtime.

## Features

- Inspect and edit notebook cells without loading the entire notebook.
- Create, search, copy, upload, and download notebooks.
- Keep local file access inside a configured root directory.
- Normalize Colab-specific stream output metadata during downloads.
- Diagnose Google Drive setup without unexpectedly opening a browser.
- Return actionable errors for missing credentials, expired authorization,
  permissions, missing files, and rate limits.

## Non-goals

- Starting, controlling, or monitoring a Google Colab runtime.
- Executing notebook cells locally or remotely.
- Browser automation, automatic `Run all`, or unattended Colab sessions.
- Circumventing Colab quotas, idle timeouts, access controls, or usage policies.
- Deploying or running the project contained inside a notebook.

## AI Contract

The MCP initialization response includes server-wide instructions that define
this project as file synchronization only. Tool descriptions repeat the same
boundary where it matters.

[`manifest.0`](manifest.0) provides the same purpose, capabilities, and
non-goals as a typed Zero language contract for agents and repository tooling.

## Tools

### Setup

- `get_google_drive_status`: diagnose dependencies, credentials, token, and scope.
- `authorize_google_drive`: explicitly open the Google OAuth browser flow.

### Local notebooks

- `list_local_notebooks`, `get_local_notebook`, `create_local_notebook`
- `add_local_cell`, `update_local_cell`, `delete_local_cell`
- `search_local_cells`, `clear_local_outputs`

### Google Drive

- `list_drive_notebooks`, `pull_drive_notebook`, `push_local_notebook`
- `copy_drive_notebook`, `get_colab_url`

`pull_drive_notebook` and `push_local_notebook` synchronize notebook files.
They never execute notebook code. `get_colab_url` returns a URL but does not
open a browser.

## Install

```bash
git clone https://github.com/YummyTastyCode/colab-drive-mcp.git
cd colab-drive-mcp
python3 -m venv .venv
.venv/bin/pip install -e '.[drive]'
```

Run the server:

```bash
COLAB_MCP_ROOT="$HOME/notebooks" .venv/bin/colab-drive-mcp
```

Local tools can access only `.ipynb` files below `COLAB_MCP_ROOT`.

## Google Drive Setup

First call `get_google_drive_status`. It does not open a browser or modify
files. Its response explains the next required step.

To enable Drive:

1. Create a Google Cloud project.
2. Enable the Google Drive API.
3. Configure the OAuth consent screen and add your account as a test user.
4. Create an OAuth Client ID with application type **Desktop app**.
5. Download the JSON to `~/.config/colab-mcp/credentials.json`.
6. Call `authorize_google_drive` and complete the Google sign-in flow.

The resulting token is stored at `~/.config/colab-mcp/token.json`.

Override these locations with:

- `COLAB_MCP_GOOGLE_CREDENTIALS`
- `COLAB_MCP_GOOGLE_TOKEN`

Never commit OAuth credentials or tokens.

## Drive Access Modes

The default mode is `file`, using Google's narrower `drive.file` scope:

```bash
COLAB_MCP_DRIVE_ACCESS=file
```

This mode can access files created or explicitly opened by this OAuth app. It
cannot reliably list all existing notebooks in a user's Drive.

To find and update existing Drive notebooks, explicitly enable full access:

```bash
COLAB_MCP_DRIVE_ACCESS=full
```

Changing access modes may require deleting `token.json` and calling
`authorize_google_drive` again.

## Codex Configuration

```bash
codex mcp add colab-drive \
  --env COLAB_MCP_ROOT="$HOME/notebooks" \
  --env COLAB_MCP_DRIVE_ACCESS=file \
  -- /absolute/path/to/colab-drive-mcp/.venv/bin/colab-drive-mcp
```

## VS Code Configuration

Add this server to the VS Code MCP configuration:

```json
{
  "servers": {
    "colab-drive": {
      "type": "stdio",
      "command": "/absolute/path/to/colab-drive-mcp/.venv/bin/colab-drive-mcp",
      "env": {
        "COLAB_MCP_ROOT": "/absolute/path/to/notebooks",
        "COLAB_MCP_DRIVE_ACCESS": "file"
      }
    }
  }
}
```

## Colab Compatibility

Google Colab may add a `metadata` property to stream outputs. That property is
invalid under the standard nbformat v4 schema. During Drive downloads, this
server removes only that incompatible property. Stream text and all other
outputs are preserved.

## Security

- OAuth tokens stay on the local machine.
- Local tools are restricted to `COLAB_MCP_ROOT`.
- Authorization requires an explicit `authorize_google_drive` call.
- Use `file` access unless full Drive discovery is required.
- Review actions before overwriting an existing Drive file.

This project is not affiliated with or endorsed by Google.

## Development

```bash
.venv/bin/pip install -e '.[drive,test]'
.venv/bin/pytest
```

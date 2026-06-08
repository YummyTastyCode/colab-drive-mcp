# Security Policy

## Credentials

Do not include Google OAuth client credentials, access tokens, refresh tokens,
notebooks containing secrets, or private Drive file IDs in bug reports.

The default credential locations are:

- `~/.config/colab-mcp/credentials.json`
- `~/.config/colab-mcp/token.json`

Both files should be readable only by the local user.

## Drive Permissions

Use `COLAB_MCP_DRIVE_ACCESS=file` unless the server must discover existing
notebooks across Google Drive. The `full` mode grants broad Drive access.

## Reporting

Report suspected vulnerabilities privately to the repository maintainer.

from __future__ import annotations

import io
import json
import os
from pathlib import Path
from typing import Any

DRIVE_FILE_SCOPE = "https://www.googleapis.com/auth/drive.file"
DRIVE_FULL_SCOPE = "https://www.googleapis.com/auth/drive"
NOTEBOOK_MIME = "application/x-ipynb+json"


class DriveUserError(RuntimeError):
    def __init__(self, code: str, message: str, next_step: str) -> None:
        self.code = code
        self.next_step = next_step
        super().__init__(f"{message}\nNext step: {next_step}\nError code: {code}")


class DriveNotebookClient:
    def __init__(
        self, credentials_path: Path, token_path: Path, access_mode: str | None = None
    ) -> None:
        self.credentials_path = credentials_path.expanduser()
        self.token_path = token_path.expanduser()
        self.access_mode = access_mode or os.environ.get("COLAB_MCP_DRIVE_ACCESS", "file")
        if self.access_mode not in {"file", "full"}:
            raise ValueError("COLAB_MCP_DRIVE_ACCESS must be 'file' or 'full'")
        self._service: Any = None

    @property
    def scopes(self) -> list[str]:
        return [DRIVE_FULL_SCOPE if self.access_mode == "full" else DRIVE_FILE_SCOPE]

    def _imports(self) -> tuple[Any, Any, Any, Any, Any]:
        try:
            from google.auth.transport.requests import Request
            from google.oauth2.credentials import Credentials
            from google_auth_oauthlib.flow import InstalledAppFlow
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload
        except ImportError as exc:
            raise DriveUserError(
                "drive_dependencies_missing",
                "Google Drive support is not installed.",
                "Install it with: pip install 'colab-mcp[drive]'",
            ) from exc
        return Request, Credentials, InstalledAppFlow, build, (MediaIoBaseDownload, MediaIoBaseUpload)

    def auth_status(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "access_mode": self.access_mode,
            "scope": self.scopes[0],
            "credentials_path": str(self.credentials_path),
            "token_path": str(self.token_path),
            "credentials_found": self.credentials_path.is_file(),
            "token_found": self.token_path.is_file(),
        }
        try:
            _, Credentials, _, _, _ = self._imports()
        except DriveUserError as exc:
            return {
                **result,
                "status": "dependencies_missing",
                "ready": False,
                "message": str(exc),
            }
        if not result["token_found"]:
            if not result["credentials_found"]:
                return {
                    **result,
                    "status": "credentials_missing",
                    "ready": False,
                    "message": (
                        "Download an OAuth Desktop client JSON from Google Cloud Console "
                        f"and save it as {self.credentials_path}."
                    ),
                }
            return {
                **result,
                "status": "authorization_required",
                "ready": False,
                "message": "Call authorize_google_drive to sign in with Google.",
            }
        try:
            credentials = Credentials.from_authorized_user_file(
                str(self.token_path), self.scopes
            )
        except (ValueError, json.JSONDecodeError) as exc:
            return {
                **result,
                "status": "token_invalid",
                "ready": False,
                "message": (
                    f"The token file is invalid. Remove {self.token_path} and call "
                    "authorize_google_drive again."
                ),
                "details": str(exc),
            }
        if credentials.valid:
            return {
                **result,
                "status": "ready",
                "ready": True,
                "message": "Google Drive authorization is ready.",
            }
        if credentials.expired and credentials.refresh_token:
            return {
                **result,
                "status": "token_expired_refreshable",
                "ready": True,
                "message": "The access token is expired and will be refreshed automatically.",
            }
        message = (
            f"Authorization is no longer valid. Remove {self.token_path} and call "
            "authorize_google_drive again."
        )
        if not result["credentials_found"]:
            message += f" OAuth Desktop credentials are also required at {self.credentials_path}."
        return {
            **result,
            "status": "authorization_required",
            "ready": False,
            "message": message,
        }

    def authorize(self) -> dict[str, Any]:
        Request, Credentials, InstalledAppFlow, _, _ = self._imports()
        if self.token_path.is_file():
            try:
                credentials = Credentials.from_authorized_user_file(
                    str(self.token_path), self.scopes
                )
                if credentials.valid:
                    return self.auth_status()
                if credentials.expired and credentials.refresh_token:
                    credentials.refresh(Request())
                    self.token_path.write_text(credentials.to_json(), encoding="utf-8")
                    return self.auth_status()
            except Exception:
                pass
        if not self.credentials_path.is_file():
            raise DriveUserError(
                "oauth_credentials_missing",
                f"OAuth Desktop client JSON was not found at {self.credentials_path}.",
                "Create a Desktop OAuth client in Google Cloud Console and save its JSON there.",
            )
        flow = InstalledAppFlow.from_client_secrets_file(
            str(self.credentials_path), self.scopes
        )
        credentials = flow.run_local_server(port=0)
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(credentials.to_json(), encoding="utf-8")
        self._service = None
        return self.auth_status()

    def service(self) -> Any:
        if self._service is not None:
            return self._service
        Request, Credentials, _, build, _ = self._imports()
        status = self.auth_status()
        if not status["ready"]:
            raise DriveUserError(
                status["status"],
                status["message"],
                "Call get_google_drive_status for setup details, then authorize_google_drive.",
            )
        credentials = Credentials.from_authorized_user_file(
            str(self.token_path), self.scopes
        )
        if not credentials.valid and credentials.expired and credentials.refresh_token:
            try:
                credentials.refresh(Request())
                self.token_path.write_text(credentials.to_json(), encoding="utf-8")
            except Exception as exc:
                raise DriveUserError(
                    "token_refresh_failed",
                    "Google authorization expired or was revoked.",
                    f"Remove {self.token_path} and call authorize_google_drive again.",
                ) from exc
        try:
            self._service = build(
                "drive", "v3", credentials=credentials, cache_discovery=False
            )
        except Exception as exc:
            raise DriveUserError(
                "drive_client_initialization_failed",
                "Could not initialize the Google Drive client.",
                "Check network access and call get_google_drive_status.",
            ) from exc
        return self._service

    @staticmethod
    def _raise_api_error(exc: Exception) -> None:
        status = getattr(getattr(exc, "resp", None), "status", None)
        if status == 401:
            raise DriveUserError(
                "google_unauthorized",
                "Google rejected the saved authorization.",
                "Remove the token file and call authorize_google_drive again.",
            ) from exc
        if status == 403:
            raise DriveUserError(
                "google_forbidden",
                "Google Drive denied this operation.",
                (
                    "Enable the Drive API, verify OAuth test-user access, and use "
                    "COLAB_MCP_DRIVE_ACCESS=full if this operation needs existing files."
                ),
            ) from exc
        if status == 404:
            raise DriveUserError(
                "drive_file_not_found",
                "The Google Drive file was not found or is not visible to this OAuth client.",
                "Verify the file_id and the configured Drive access mode.",
            ) from exc
        if status == 429:
            raise DriveUserError(
                "drive_rate_limited",
                "Google Drive temporarily rate-limited the request.",
                "Wait briefly and retry with fewer requests.",
            ) from exc
        raise DriveUserError(
            "drive_request_failed",
            "The Google Drive request failed.",
            "Check Google Cloud API status, network access, and OAuth configuration.",
        ) from exc

    def _execute(self, request: Any) -> Any:
        try:
            return request.execute()
        except Exception as exc:
            self._raise_api_error(exc)

    def list_notebooks(self, query: str = "", limit: int = 100) -> list[dict[str, Any]]:
        escaped = query.replace("\\", "\\\\").replace("'", "\\'")
        clauses = ["trashed = false", "name contains '.ipynb'"]
        if query:
            clauses.append(f"name contains '{escaped}'")
        request = (
            self.service()
            .files()
            .list(
                q=" and ".join(clauses),
                pageSize=limit,
                fields="files(id,name,modifiedTime,size,webViewLink,parents)",
                orderBy="modifiedTime desc",
            )
        )
        result = self._execute(request)
        return result.get("files", [])

    def download_notebook(self, file_id: str) -> dict[str, Any]:
        _, _, _, _, media = self._imports()
        MediaIoBaseDownload, _ = media
        buffer = io.BytesIO()
        downloader = MediaIoBaseDownload(
            buffer, self.service().files().get_media(fileId=file_id)
        )
        done = False
        while not done:
            try:
                _, done = downloader.next_chunk()
            except Exception as exc:
                self._raise_api_error(exc)
        return json.loads(buffer.getvalue())

    def upload_notebook(
        self, notebook: dict[str, Any], name: str, file_id: str | None = None
    ) -> dict[str, Any]:
        _, _, _, _, media = self._imports()
        _, MediaIoBaseUpload = media
        content = json.dumps(notebook, ensure_ascii=False).encode()
        upload = MediaIoBaseUpload(io.BytesIO(content), mimetype=NOTEBOOK_MIME, resumable=False)
        fields = "id,name,modifiedTime,size,webViewLink"
        if file_id:
            request = (
                self.service()
                .files()
                .update(fileId=file_id, media_body=upload, fields=fields)
            )
            return self._execute(request)
        request = (
            self.service()
            .files()
            .create(body={"name": name, "mimeType": NOTEBOOK_MIME}, media_body=upload, fields=fields)
        )
        return self._execute(request)

    def copy_notebook(self, file_id: str, name: str) -> dict[str, Any]:
        request = (
            self.service()
            .files()
            .copy(fileId=file_id, body={"name": name}, fields="id,name,modifiedTime,webViewLink")
        )
        return self._execute(request)

    @staticmethod
    def colab_url(file_id: str) -> str:
        return f"https://colab.research.google.com/drive/{file_id}"

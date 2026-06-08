from pathlib import Path
import json

import pytest

from colab_mcp.drive import DRIVE_FILE_SCOPE, DRIVE_FULL_SCOPE, DriveNotebookClient, DriveUserError


def test_colab_url() -> None:
    assert (
        DriveNotebookClient.colab_url("abc123")
        == "https://colab.research.google.com/drive/abc123"
    )


def test_auth_status_explains_missing_credentials(tmp_path: Path) -> None:
    client = DriveNotebookClient(
        tmp_path / "credentials.json", tmp_path / "token.json"
    )

    status = client.auth_status()

    assert status["status"] == "credentials_missing"
    assert status["ready"] is False
    assert "OAuth Desktop client JSON" in status["message"]


def test_valid_token_does_not_require_credentials_file(tmp_path: Path) -> None:
    token = tmp_path / "token.json"
    token.write_text(
        json.dumps(
            {
                "token": "access-token",
                "refresh_token": "refresh-token",
                "token_uri": "https://oauth2.googleapis.com/token",
                "client_id": "client-id",
                "client_secret": "client-secret",
                "scopes": [DRIVE_FILE_SCOPE],
                "expiry": "2999-01-01T00:00:00Z",
            }
        ),
        encoding="utf-8",
    )
    client = DriveNotebookClient(tmp_path / "missing.json", token)

    status = client.auth_status()

    assert status["status"] == "ready"
    assert status["ready"] is True


def test_drive_access_defaults_to_minimal_scope(tmp_path: Path) -> None:
    client = DriveNotebookClient(
        tmp_path / "credentials.json", tmp_path / "token.json"
    )
    full_client = DriveNotebookClient(
        tmp_path / "credentials.json", tmp_path / "token.json", access_mode="full"
    )

    assert client.scopes == [DRIVE_FILE_SCOPE]
    assert full_client.scopes == [DRIVE_FULL_SCOPE]


def test_service_error_is_actionable_without_credentials(tmp_path: Path) -> None:
    client = DriveNotebookClient(
        tmp_path / "credentials.json", tmp_path / "token.json"
    )

    with pytest.raises(DriveUserError, match="get_google_drive_status"):
        client.service()


@pytest.mark.parametrize(
    ("status", "code"),
    [(401, "google_unauthorized"), (403, "google_forbidden"), (404, "drive_file_not_found"), (429, "drive_rate_limited")],
)
def test_google_api_errors_are_actionable(status: int, code: str) -> None:
    class Response:
        pass

    class ApiError(Exception):
        pass

    error = ApiError("raw Google error")
    error.resp = Response()
    error.resp.status = status

    with pytest.raises(DriveUserError) as caught:
        DriveNotebookClient._raise_api_error(error)

    assert caught.value.code == code
    assert "Next step:" in str(caught.value)


def test_upload_notebook_reports_resumable_progress(tmp_path: Path) -> None:
    class UploadStatus:
        @staticmethod
        def progress() -> float:
            return 0.5

    class Request:
        calls = 0

        def next_chunk(self):
            self.calls += 1
            if self.calls == 1:
                return UploadStatus(), None
            return None, {"id": "drive-id", "md5Checksum": "checksum"}

    class Files:
        def create(self, **kwargs):
            assert kwargs["media_body"].resumable()
            return Request()

    class Service:
        @staticmethod
        def files():
            return Files()

    client = DriveNotebookClient(tmp_path / "credentials.json", tmp_path / "token.json")
    client._service = Service()
    client._imports = lambda: (None, None, None, None, (None, FakeMediaUpload))
    events = []

    result = client.upload_notebook(
        {"cells": []},
        "demo.ipynb",
        progress=lambda value, message: events.append((value, message)),
    )

    assert result["id"] == "drive-id"
    assert events == [(0.5, "Uploading notebook to Google Drive")]


def test_download_notebook_reports_progress(tmp_path: Path) -> None:
    class Files:
        @staticmethod
        def get_media(fileId: str):
            return fileId

    class Service:
        @staticmethod
        def files():
            return Files()

    client = DriveNotebookClient(tmp_path / "credentials.json", tmp_path / "token.json")
    client._service = Service()
    client._imports = lambda: (None, None, None, None, (FakeMediaDownload, None))
    events = []

    result = client.download_notebook(
        "drive-id", progress=lambda value, message: events.append((value, message))
    )

    assert result == {"cells": []}
    assert events == [(1.0, "Downloading notebook from Google Drive")]


class FakeMediaUpload:
    def __init__(self, stream, mimetype: str, chunksize: int, resumable: bool) -> None:
        self.stream = stream
        self.mimetype = mimetype
        self.chunksize = chunksize
        self._resumable = resumable

    def resumable(self) -> bool:
        return self._resumable


class FakeMediaDownload:
    def __init__(self, stream, request, chunksize: int) -> None:
        self.stream = stream
        self.chunksize = chunksize

    def next_chunk(self):
        self.stream.write(b'{"cells": []}')
        return FakeDownloadStatus(), True


class FakeDownloadStatus:
    @staticmethod
    def progress() -> float:
        return 1.0

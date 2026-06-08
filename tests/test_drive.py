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

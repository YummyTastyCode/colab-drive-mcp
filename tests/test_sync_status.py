import hashlib

import nbformat

import colab_mcp.server as server
from colab_mcp.notebooks import NotebookStore


def test_sync_status_compares_local_upload_content(tmp_path, monkeypatch) -> None:
    store = NotebookStore(tmp_path)
    notebook = nbformat.v4.new_notebook(cells=[nbformat.v4.new_code_cell("answer = 42")])
    store.write("demo.ipynb", notebook)
    upload_content = server.drive.notebook_bytes(dict(store.read("demo.ipynb")))
    remote_md5 = hashlib.md5(upload_content).hexdigest()
    monkeypatch.setattr(server, "store", store)
    monkeypatch.setattr(
        server.drive,
        "get_notebook_metadata",
        lambda file_id: {"id": file_id, "md5Checksum": remote_md5},
    )

    result = server.get_notebook_sync_status("drive-id", "demo.ipynb")

    assert result["sync_state"] == "in_sync"
    assert result["runtime_status"] == "unavailable"


def test_sync_status_detects_different_content(tmp_path, monkeypatch) -> None:
    store = NotebookStore(tmp_path)
    store.write("demo.ipynb", nbformat.v4.new_notebook())
    monkeypatch.setattr(server, "store", store)
    monkeypatch.setattr(
        server.drive,
        "get_notebook_metadata",
        lambda file_id: {"id": file_id, "md5Checksum": "different"},
    )

    result = server.get_notebook_sync_status("drive-id", "demo.ipynb")

    assert result["sync_state"] == "differs"

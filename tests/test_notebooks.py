from pathlib import Path

import nbformat
import pytest

from colab_mcp.notebooks import NotebookStore, normalize_colab_notebook


def test_notebook_lifecycle(tmp_path: Path) -> None:
    store = NotebookStore(tmp_path)

    created = store.create("experiments/demo.ipynb", "Demo")
    assert created["cell_count"] == 1
    assert created["cells"][0]["source"] == "# Demo"

    added = store.add_cell("experiments/demo.ipynb", "code", "answer = 42")
    assert added["index"] == 1
    store.add_cell("experiments/demo.ipynb", "markdown", "Find the answer", index=1)

    store.update_cell("experiments/demo.ipynb", 2, "answer = 43")
    results = store.search_cells("experiments/demo.ipynb", "43")
    assert [result["index"] for result in results] == [2]
    assert results[0]["source"] == "answer = 43"

    deleted = store.delete_cell("experiments/demo.ipynb", 1)
    assert deleted["deleted_type"] == "markdown"
    assert store.summary("experiments/demo.ipynb")["cell_count"] == 2


def test_clear_outputs(tmp_path: Path) -> None:
    store = NotebookStore(tmp_path)
    notebook = nbformat.v4.new_notebook(
        cells=[
            nbformat.v4.new_code_cell(
                "print('hello')",
                execution_count=1,
                outputs=[nbformat.v4.new_output("stream", name="stdout", text="hello\n")],
            )
        ]
    )
    store.write("output.ipynb", notebook)

    result = store.clear_outputs("output.ipynb")
    cell = store.read("output.ipynb").cells[0]

    assert result["cleared_cells"] == 1
    assert cell.outputs == []
    assert cell.execution_count is None


def test_paths_cannot_escape_root(tmp_path: Path) -> None:
    store = NotebookStore(tmp_path)

    with pytest.raises(ValueError, match="inside"):
        store.create("../escape.ipynb")

    with pytest.raises(ValueError, match=".ipynb"):
        store.create("not-a-notebook.txt")


def test_list_excludes_checkpoints_and_sorts(tmp_path: Path) -> None:
    store = NotebookStore(tmp_path)
    store.create("first.ipynb")
    store.create(".ipynb_checkpoints/hidden.ipynb")
    store.create("nested/second.ipynb")

    paths = {item["path"] for item in store.list()}

    assert paths == {"first.ipynb", "nested/second.ipynb"}


def test_normalize_colab_stream_output_metadata() -> None:
    notebook = {
        "cells": [
            {
                "cell_type": "code",
                "outputs": [
                    {
                        "output_type": "stream",
                        "name": "stdout",
                        "text": "done\n",
                        "metadata": {"colab": "extension"},
                    },
                    {
                        "output_type": "display_data",
                        "data": {"text/plain": "plot"},
                        "metadata": {"keep": True},
                    },
                ],
            }
        ]
    }

    normalized = normalize_colab_notebook(notebook)

    assert normalized == 1
    assert "metadata" not in notebook["cells"][0]["outputs"][0]
    assert notebook["cells"][0]["outputs"][1]["metadata"] == {"keep": True}

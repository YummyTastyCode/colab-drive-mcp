from __future__ import annotations

from pathlib import Path
from typing import Any

import nbformat
from nbformat import NotebookNode


def normalize_colab_notebook(notebook: dict[str, Any]) -> int:
    """Remove Colab extensions that are invalid under the nbformat v4 schema."""
    normalized = 0
    for cell in notebook.get("cells", []):
        for output in cell.get("outputs", []):
            if output.get("output_type") == "stream" and "metadata" in output:
                del output["metadata"]
                normalized += 1
    return normalized


class NotebookStore:
    def __init__(self, root: Path) -> None:
        self.root = root.expanduser().resolve()

    def _path(self, relative_path: str, *, must_exist: bool = True) -> Path:
        path = (self.root / relative_path).resolve()
        if not path.is_relative_to(self.root):
            raise ValueError(f"Path must stay inside {self.root}")
        if path.suffix.lower() != ".ipynb":
            raise ValueError("Notebook path must end with .ipynb")
        if must_exist and not path.is_file():
            raise FileNotFoundError(path)
        return path

    def list(self, query: str = "", limit: int = 100) -> list[dict[str, Any]]:
        query = query.casefold()
        notebooks = []
        for path in self.root.rglob("*.ipynb"):
            if ".ipynb_checkpoints" in path.parts:
                continue
            relative = str(path.relative_to(self.root))
            if query and query not in relative.casefold():
                continue
            stat = path.stat()
            notebooks.append(
                {
                    "path": relative,
                    "size_bytes": stat.st_size,
                    "modified_at": stat.st_mtime,
                }
            )
        notebooks.sort(key=lambda item: item["modified_at"], reverse=True)
        return notebooks[:limit]

    def read(self, relative_path: str) -> NotebookNode:
        return nbformat.read(self._path(relative_path), as_version=4)

    def write(self, relative_path: str, notebook: NotebookNode) -> None:
        path = self._path(relative_path, must_exist=False)
        path.parent.mkdir(parents=True, exist_ok=True)
        nbformat.validate(notebook)
        nbformat.write(notebook, path)

    def create(
        self, relative_path: str, title: str = "", kernel_name: str = "python3"
    ) -> dict[str, Any]:
        path = self._path(relative_path, must_exist=False)
        if path.exists():
            raise FileExistsError(path)
        notebook = nbformat.v4.new_notebook()
        notebook.metadata.kernelspec = {
            "display_name": "Python 3",
            "language": "python",
            "name": kernel_name,
        }
        notebook.metadata.language_info = {"name": "python"}
        if title:
            notebook.cells.append(nbformat.v4.new_markdown_cell(f"# {title}"))
        self.write(relative_path, notebook)
        return self.summary(relative_path)

    def summary(
        self, relative_path: str, include_source: bool = True, max_source_chars: int = 4000
    ) -> dict[str, Any]:
        notebook = self.read(relative_path)
        cells = []
        for index, cell in enumerate(notebook.cells):
            item: dict[str, Any] = {
                "index": index,
                "id": cell.get("id"),
                "cell_type": cell.cell_type,
                "source_chars": len(cell.source),
            }
            if include_source:
                item["source"] = cell.source[:max_source_chars]
                item["source_truncated"] = len(cell.source) > max_source_chars
            if cell.cell_type == "code":
                item["execution_count"] = cell.execution_count
                item["output_count"] = len(cell.outputs)
            cells.append(item)
        return {
            "path": relative_path,
            "cell_count": len(notebook.cells),
            "metadata": dict(notebook.metadata),
            "cells": cells,
        }

    def add_cell(
        self, relative_path: str, cell_type: str, source: str, index: int | None = None
    ) -> dict[str, Any]:
        notebook = self.read(relative_path)
        cell = self._new_cell(cell_type, source)
        if index is None:
            notebook.cells.append(cell)
            index = len(notebook.cells) - 1
        else:
            if index < 0 or index > len(notebook.cells):
                raise IndexError(index)
            notebook.cells.insert(index, cell)
        self.write(relative_path, notebook)
        return {"path": relative_path, "index": index, "id": cell.get("id")}

    def update_cell(
        self, relative_path: str, index: int, source: str, cell_type: str | None = None
    ) -> dict[str, Any]:
        notebook = self.read(relative_path)
        old_cell = notebook.cells[index]
        target_type = cell_type or old_cell.cell_type
        new_cell = self._new_cell(target_type, source)
        if old_cell.get("id"):
            new_cell.id = old_cell.id
        notebook.cells[index] = new_cell
        self.write(relative_path, notebook)
        return {"path": relative_path, "index": index, "id": new_cell.get("id")}

    def delete_cell(self, relative_path: str, index: int) -> dict[str, Any]:
        notebook = self.read(relative_path)
        deleted = notebook.cells.pop(index)
        self.write(relative_path, notebook)
        return {
            "path": relative_path,
            "deleted_index": index,
            "deleted_type": deleted.cell_type,
        }

    def clear_outputs(self, relative_path: str) -> dict[str, Any]:
        notebook = self.read(relative_path)
        cleared = 0
        for cell in notebook.cells:
            if cell.cell_type == "code" and (cell.outputs or cell.execution_count is not None):
                cell.outputs = []
                cell.execution_count = None
                cleared += 1
        self.write(relative_path, notebook)
        return {"path": relative_path, "cleared_cells": cleared}

    def search_cells(
        self, relative_path: str, query: str, case_sensitive: bool = False
    ) -> list[dict[str, Any]]:
        notebook = self.read(relative_path)
        needle = query if case_sensitive else query.casefold()
        results = []
        for index, cell in enumerate(notebook.cells):
            source = cell.source if case_sensitive else cell.source.casefold()
            if needle in source:
                results.append(
                    {
                        "index": index,
                        "id": cell.get("id"),
                        "cell_type": cell.cell_type,
                        "source": cell.source,
                    }
                )
        return results

    @staticmethod
    def _new_cell(cell_type: str, source: str) -> NotebookNode:
        if cell_type == "code":
            return nbformat.v4.new_code_cell(source)
        if cell_type == "markdown":
            return nbformat.v4.new_markdown_cell(source)
        if cell_type == "raw":
            return nbformat.v4.new_raw_cell(source)
        raise ValueError("cell_type must be code, markdown, or raw")

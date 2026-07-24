"""Drawings on disk: one JSON file each.

Readable on purpose. If the app ever writes something wrong, the artist's work
is still sitting there in a text file they can open, which is not true of a
binary blob or a database.
"""
import json
import os
import re
from dataclasses import asdict
from pathlib import Path

from art_kit.model import Drawing, Palette

FORMAT = 1


class CorruptDrawing(Exception):
    """A file that cannot be turned back into a drawing."""


def to_dict(drawing):
    if drawing.is_letters():
        cells = ["".join(c if c else "." for c in row) for row in drawing.cells]
    else:
        cells = [[list(c) if isinstance(c, tuple) else c for c in row]
                 for row in drawing.cells]
    return {
        "format": FORMAT,
        "name": drawing.name,
        "species": drawing.species,
        "model": drawing.model,
        "kind": drawing.kind,
        "palette": asdict(drawing.palette),
        "cells": cells,
    }


def from_dict(data):
    # The whole parse lives inside one try block, not just the field lookups.
    # A row or cell of the wrong shape (a stray int from a hand-edit, say)
    # raises TypeError from ordinary iteration further down, and that needs to
    # come out as CorruptDrawing too -- otherwise one malformed file crashes
    # Library.load_all() for every other drawing instead of being skipped.
    try:
        palette = Palette(**data["palette"])
        raw = data["cells"]
        name, species, model = data["name"], data["species"], data["model"]
        if not isinstance(raw, list) or not raw:
            raise CorruptDrawing("cells must be a non-empty list of rows")
        cells = []
        for row in raw:
            if isinstance(row, str):
                cells.append([ch if ch != "." else None for ch in row])
            else:
                cells.append([tuple(c) if isinstance(c, list) else c for c in row])
        width = len(cells[0])
        if any(len(row) != width for row in cells):
            raise CorruptDrawing("rows are not all the same length")
        kind = data.get("kind", "letters")
    except (KeyError, TypeError) as exc:
        raise CorruptDrawing(f"missing or malformed field: {exc}") from exc
    return Drawing(name=name, species=species, model=model, cells=cells,
                   palette=palette, kind=kind)


def save(drawing, path):
    """Write path, but never as a half-finished file.

    `to_dict` and `json.dumps` run to completion, in memory, before any file
    is touched. The result then goes to a sibling temp file; only a complete
    temp file gets swapped into place, with a single rename. A save that
    fails partway (disk full, process killed) leaves the OLD file exactly as
    it was -- opening `path` directly in write mode would instead truncate it
    on open, before the new content is known good, so a failed write could
    lose the artist's last-saved copy for nothing.
    """
    path = Path(path)
    text = json.dumps(to_dict(drawing), indent=1)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def load(path):
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise CorruptDrawing(f"{path}: {exc}") from exc
    return from_dict(data)


def _slug(text):
    return re.sub(r"[^a-z0-9_-]+", "_", text.lower()).strip("_") or "drawing"


class Library:
    """The drawings folder. Knows nothing about widgets."""

    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.drawings = []
        self._paths = {}

    def load_all(self):
        """Returns the files it could NOT read, so the app can say so."""
        self.drawings, self._paths, skipped = [], {}, []
        for path in sorted(self.root.glob("*.json")):
            try:
                drawing = load(path)
            except CorruptDrawing:
                skipped.append(path)
                continue
            self.drawings.append(drawing)
            self._paths[id(drawing)] = path
        return skipped

    def _free_path(self, drawing):
        base = _slug(f"{drawing.species}_{drawing.model}_{drawing.name}")
        path = self.root / f"{base}.json"
        n = 2
        while path.exists():
            path = self.root / f"{base}-{n}.json"
            n += 1
        return path

    def add(self, drawing):
        path = self._free_path(drawing)
        self._paths[id(drawing)] = path
        self.drawings.append(drawing)
        save(drawing, path)
        return drawing

    def save(self, drawing):
        save(drawing, self._paths[id(drawing)])

    def remove(self, drawing):
        path = self._paths.pop(id(drawing), None)
        if path and path.exists():
            path.unlink()
        if drawing in self.drawings:
            self.drawings.remove(drawing)

    def duplicate(self, drawing):
        clone = drawing.copy()
        clone.name = f"{drawing.name} copy"
        return self.add(clone)

    def seed_from_engine(self):
        """Fill an empty library with the shipped flowers. No-op if not empty."""
        if self.drawings:
            return self.drawings
        from art_kit import engine_io
        for drawing in engine_io.import_all():
            self.add(drawing)
        return self.drawings

"""Drawings on disk: one JSON file each.

Readable on purpose. If the app ever writes something wrong, the artist's work
is still sitting there in a text file they can open, which is not true of a
binary blob or a database.
"""
import json
import os
import re
import shutil
from dataclasses import asdict
from pathlib import Path

from art_kit.model import Drawing, LETTERS, Palette

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
        "label": drawing.label,
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
                for ch in row:
                    if ch != "." and ch not in LETTERS:
                        raise CorruptDrawing(f"unknown letter {ch!r} in a cell")
                cells.append([ch if ch != "." else None for ch in row])
            else:
                out = []
                for c in row:
                    if c is None:
                        out.append(None)
                    elif isinstance(c, str):
                        # A mixed drawing serialises as list-rows but keeps its
                        # letter cells as bare letters alongside the [r,g,b,a]s.
                        if c not in LETTERS:
                            raise CorruptDrawing(f"unknown letter {c!r} in a cell")
                        out.append(c)
                    elif (isinstance(c, list) and len(c) == 4
                          and all(isinstance(n, int) for n in c)):
                        out.append(tuple(c))
                    else:
                        raise CorruptDrawing(
                            f"a colour cell must be null, a letter, or "
                            f"[r,g,b,a], got {c!r}")
                cells.append(out)
        width = len(cells[0])
        if any(len(row) != width for row in cells):
            raise CorruptDrawing("rows are not all the same length")
        # `kind` is derived from the cells now, not stored on the Drawing, but
        # a garbage value in the file still means a corrupt file — reject it.
        stored_kind = data.get("kind", "letters")
        if stored_kind not in ("letters", "pixels"):
            raise CorruptDrawing(f"unknown kind {stored_kind!r}")
    except (KeyError, TypeError) as exc:
        raise CorruptDrawing(f"missing or malformed field: {exc}") from exc
    # Optional (#v2.6.0): files from older versions have no label; a
    # non-string one is a hand-edit gone wrong, not worth losing the drawing.
    label = data.get("label", "")
    if not isinstance(label, str):
        label = ""
    return Drawing(name=name, species=species, model=model, cells=cells,
                   palette=palette, label=label.strip())


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
        self._backed_up = set()  # paths already .bak'd this session

    def load_all(self):
        """Returns the files it could NOT read, so the app can say so."""
        self.drawings, self._paths, skipped = [], {}, []
        for path in sorted(self.root.glob("*.json")):
            try:
                drawing = load(path)
            except CorruptDrawing:
                skipped.append(path)
                continue
            if not drawing.label:
                # A library from before labels existed: the seeded flowers and
                # forest props at least know what kind of thing they are.
                from art_kit import engine_io
                drawing.label = engine_io.default_label(drawing.species)
            self.drawings.append(drawing)
            self._paths[id(drawing)] = path
        return skipped

    def labels(self):
        """Every distinct label in use, sorted, empties left out."""
        return sorted({d.label for d in self.drawings if d.label})

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
        self._backed_up.add(path)  # fresh file; nothing worth backing up
        save(drawing, path)
        return drawing

    def save(self, drawing):
        path = self._paths[id(drawing)]
        if path not in self._backed_up:
            # First save of this session over an existing file: keep what the
            # artist STARTED the session with. Undo history dies with the app;
            # this is the one rescue left after "ruined it, then closed it".
            self._backed_up.add(path)
            if path.exists():
                shutil.copy2(path, path.with_name(path.name + ".bak"))
        save(drawing, path)

    def remove(self, drawing):
        path = self._paths.pop(id(drawing), None)
        if path and path.exists():
            path.unlink()
        # By identity, not ==: two value-equal drawings would otherwise let
        # list.remove() splice out the wrong one and orphan this from _paths.
        self.drawings = [d for d in self.drawings if d is not drawing]

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

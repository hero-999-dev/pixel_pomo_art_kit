"""The bridge to Pixel Pomo's sprite generator.

Everything the art kit knows about the engine's file format comes from
`gen_objects.py` itself — imported, never copied. A reimplementation would be a
second source of truth that drifts the first time either side is touched, and
the whole point of this app is that its output IS the shipped sprite.
"""
import functools
import importlib.util
import os
import sys
from pathlib import Path

# Overridable so a checkout somewhere else can still run the app.
GEN_OBJECTS_DIR = Path(
    os.environ.get("PIXEL_POMO_TOOLS", r"C:\Users\claude\pixel_pomo\flutter\tools")
)


@functools.lru_cache(maxsize=1)
def gen_objects():
    """The `gen_objects` module, imported from the Pixel Pomo checkout."""
    path = GEN_OBJECTS_DIR / "gen_objects.py"
    if not path.exists():
        raise FileNotFoundError(
            f"gen_objects.py not found at {path}. Point the PIXEL_POMO_TOOLS "
            f"environment variable at pixel_pomo\\flutter\\tools."
        )
    spec = importlib.util.spec_from_file_location("gen_objects", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

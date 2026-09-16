"""python -m art_kit"""
import tkinter as tk
from pathlib import Path

from art_kit import paths, store
from art_kit.app import ArtKitApp, base_dir, fallback_dir
from art_kit.settings import Settings
from art_kit.version import VERSION


def writable(folder):
    """Can this process create and write files under `folder`? Probed for
    real rather than guessed from permissions bits: on macOS the answer
    depends on a privacy prompt, not on the mode."""
    try:
        folder.mkdir(parents=True, exist_ok=True)
        probe = folder / ".write-test"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def data_dir():
    """base_dir(), unless it cannot be written to — then fallback_dir()
    (#v2.4.0: a frozen macOS build denied access to ~/Documents used to run
    with every save silently failing)."""
    primary = base_dir()
    if writable(primary):
        return primary, None
    secondary = fallback_dir()
    if secondary != primary and writable(secondary):
        return secondary, primary
    return primary, None


def main():
    data, refused = data_dir()
    # #v2.5.0: drawings an older Windows build kept beside the .exe are copied
    # into the per-user folder (never moved), so the first run of this
    # version starts with everything the artist already had.
    migrated = paths.migrate_legacy(data)
    library = store.Library(data / "library")
    skipped = library.load_all()
    library.seed_from_engine()
    settings = Settings(data / "settings.json")
    root = tk.Tk()
    root.geometry("1280x820")
    root.minsize(980, 640)
    ArtKitApp(root, library, settings)
    from tkinter import messagebox
    if migrated:
        messagebox.showinfo(
            "Pixel Pomo Art Kit",
            f"Pixel Pomo Art Kit v{VERSION} keeps your drawings in\n{data}\n\n"
            f"{migrated} drawing(s) from the old folder next to the program were copied "
            f"there. The old folder was left as it was. You can now move or replace the "
            f"program freely — the drawings stay.")
    if refused is not None:
        messagebox.showwarning(
            "Pixel Pomo Art Kit",
            f"This app is not allowed to write to\n{refused}\n\n"
            f"Your drawings are being kept in\n{data}\ninstead. "
            f"(On macOS: System Settings → Privacy & Security → Files and Folders "
            f"to allow Documents, then restart the app.)")
    if skipped:
        messagebox.showwarning(
            "Pixel Pomo Art Kit",
            f"{len(skipped)} drawing file(s) could not be read and were skipped.")
    root.mainloop()


if __name__ == "__main__":
    main()

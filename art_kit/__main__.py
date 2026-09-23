"""python -m art_kit"""
import tkinter as tk
from pathlib import Path

from art_kit import paths, store
from art_kit.app import ArtKitApp, base_dir, fallback_dir
from art_kit.i18n import t
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
    library.seed_missing_kinds()  # bugs into a library that predates them (#v2.7.0)
    settings = Settings(data / "settings.json")
    root = tk.Tk()
    root.geometry("1280x820")
    root.minsize(980, 640)
    ArtKitApp(root, library, settings)
    # The kit's own message boxes, like every other popup in it (#v2.8.0).
    from art_kit import dialogs as messagebox
    if migrated:
        messagebox.showinfo("Pixel Pomo Art Kit",
                            t("migrated_msg", v=VERSION, data=data, n=migrated))
    if refused is not None:
        messagebox.showwarning("Pixel Pomo Art Kit",
                               t("refused_msg", refused=refused, data=data))
    if skipped:
        messagebox.showwarning("Pixel Pomo Art Kit", t("skipped_msg", n=len(skipped)))
    root.mainloop()


if __name__ == "__main__":
    main()

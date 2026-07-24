"""python -m art_kit"""
import tkinter as tk
from pathlib import Path

from art_kit import store
from art_kit.app import ArtKitApp

LIBRARY = Path(__file__).resolve().parent.parent / "library"


def main():
    library = store.Library(LIBRARY)
    skipped = library.load_all()
    library.seed_from_engine()
    root = tk.Tk()
    root.geometry("1280x820")
    ArtKitApp(root, library)
    if skipped:
        from tkinter import messagebox
        messagebox.showwarning(
            "Pixel Pomo Art Kit",
            f"{len(skipped)} drawing file(s) could not be read and were skipped.")
    root.mainloop()


if __name__ == "__main__":
    main()

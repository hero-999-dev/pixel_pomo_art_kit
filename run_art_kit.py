"""PyInstaller entry point. Runs the same app as `python -m art_kit`.

Kept as a top-level script because PyInstaller freezes a script, not a package's
`__main__`; this puts the repo root on the path so `import art_kit` resolves.
"""
from art_kit.__main__ import main

main()

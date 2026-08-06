"""PyInstaller runtime hook: keep ``sys.stdout``/``sys.stderr`` usable.

In a windowed (console=False) PyInstaller bundle launched without redirection,
the bootloader leaves ``sys.stdout`` and ``sys.stderr`` as ``None``. Libraries
such as uvicorn (``sys.stdout.isatty()``, StreamHandler writes) crash on that.
This hook redirects both to ``os.devnull`` so the launcher and uvicorn run
without a console; application logs still go to the workspace structured-log
files via the observability module.
"""

from __future__ import annotations

import os
import sys

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

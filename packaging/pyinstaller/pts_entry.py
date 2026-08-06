"""PyInstaller entry point for Pelican Town Specials.

PyInstaller runs this file as ``__main__``. It must use an absolute import
(never ``from .`` relative imports) so the launcher package is resolved from
the bundle's site-packages instead of as a sibling of ``__main__``.
"""

from __future__ import annotations

from pelican_town_specials.launcher.main import main

if __name__ == "__main__":
    raise SystemExit(main())

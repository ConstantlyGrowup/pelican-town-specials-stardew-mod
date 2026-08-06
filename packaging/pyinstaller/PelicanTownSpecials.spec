# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir spec for Pelican Town Specials (Windows).

Build layout (contents_directory disabled so the bundle matches the
launcher's frozen expectations):

    dist/PelicanTownSpecials-windows-x64/
        PelicanTownSpecials.exe
        frontend/dist/       <- Vite production build (launcher static dir)
        resources/           <- vanilla catalogs (catalog loader)
        pelican_town_specials/...  <- Python package and dependencies

The spec consumes the already-built ``frontend/dist`` and the repo
``resources`` directory; both are gitignored build inputs. Version metadata
comes from ``version_info.txt``.
"""

import os

repo_root = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
backend_src = os.path.join(repo_root, "backend", "src")

datas = [
    (os.path.join(repo_root, "frontend", "dist"), "frontend/dist"),
    (os.path.join(repo_root, "resources"), "resources"),
]

a = Analysis(
    [os.path.join(SPECPATH, "pts_entry.py")],
    pathex=[backend_src],
    binaries=[],
    datas=datas,
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[os.path.join(SPECPATH, "rthook_fix_stdio.py")],
    excludes=[
        # Dev/test tooling that must never reach the user bundle.
        "IPython",
        "jupyter_client",
        "jupyter",
        "notebook",
        "jedi",
        "parso",
        "mypy",
        "pytest",
        "respx",
        "prompt_toolkit",
        "zmq",
        "tornado",
        "IPython.core",
        "IPython.terminal",
        "IPython.lib",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PelicanTownSpecials",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory=".",
    version=os.path.join(SPECPATH, "version_info.txt"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="PelicanTownSpecials-windows-x64",
)

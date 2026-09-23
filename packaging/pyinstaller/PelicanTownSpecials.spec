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
from PyInstaller.utils.hooks import collect_dynamic_libs

repo_root = os.path.abspath(os.path.join(SPECPATH, "..", ".."))
backend_src = os.path.join(repo_root, "backend", "src")
ingredient_rag_resources = os.path.join(
    repo_root, "output", "m14-task65", "ingredient-rag-spm"
)
ingredient_rag_files = [
    "model-int8.onnx",
    "sentencepiece.bpe.model",
    "ingredient-vectors.f32",
    "ingredient-index.manifest.json",
]
missing_ingredient_rag_files = [
    filename
    for filename in ingredient_rag_files
    if not os.path.isfile(os.path.join(ingredient_rag_resources, filename))
]
if missing_ingredient_rag_files:
    raise FileNotFoundError(
        "Missing built ingredient-RAG resources: "
        + ", ".join(missing_ingredient_rag_files)
    )

ort_binaries = collect_dynamic_libs("onnxruntime")

datas = [
    (os.path.join(repo_root, "frontend", "dist"), "frontend/dist"),
    (os.path.join(repo_root, "resources"), "resources"),
    (ingredient_rag_resources, "resources/ingredient-rag"),
]

a = Analysis(
    [os.path.join(SPECPATH, "pts_entry.py")],
    pathex=[backend_src],
    binaries=ort_binaries,
    datas=datas,
    hiddenimports=[
        "onnxruntime.capi._pybind_state",
        "onnxruntime.capi.onnxruntime_pybind11_state",
        "sentencepiece",
    ],
    hookspath=[],
    runtime_hooks=[os.path.join(SPECPATH, "rthook_fix_stdio.py")],
    excludes=[
        # Evaluation/build-only libraries can be installed in a developer's
        # shared environment; none belongs in the production CPU onedir.
        "torch",
        "torchvision",
        "torchaudio",
        "tensorflow",
        "scipy",
        "sklearn",
        "sentence_transformers",
        "transformers",
        "huggingface_hub",
        "onnx",
        "tokenizers",
        "datasets",
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
    icon=os.path.join(repo_root, "packaging", "assets", "pelican-town-specials.ico"),
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

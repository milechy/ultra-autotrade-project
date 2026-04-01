"""Cython build script for AI judgment logic protection."""

import os

from Cython.Build import cythonize
from setuptools import setup

# Cython化対象ファイル
CYTHON_TARGETS = []

# backend/app/ai/ 以下の対象ファイルを検出
# 除外: __init__.py, schemas.py, router.py, decisions_router.py, decisions_schemas.py, models.py
EXCLUDE_FILES = {
    "__init__.py",
    "schemas.py",
    "router.py",
    "decisions_router.py",
    "decisions_schemas.py",
    "models.py",
}

ai_dir = os.path.join("app", "ai")
for f in sorted(os.listdir(ai_dir)):
    if f.endswith(".py") and f not in EXCLUDE_FILES:
        pyx_path = os.path.join(ai_dir, f)
        CYTHON_TARGETS.append(pyx_path)

if CYTHON_TARGETS:
    print(f"Cython targets: {CYTHON_TARGETS}")
    setup(
        ext_modules=cythonize(
            CYTHON_TARGETS,
            compiler_directives={
                "language_level": "3",
                "boundscheck": False,
                "wraparound": False,
            },
        ),
    )
else:
    print("No Cython targets found.")

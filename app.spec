# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for 玄机子 desktop app."""
import sys
from pathlib import Path

root = Path('.')

a = Analysis(
    ['desktop_app.py'],
    pathex=[str(root)],
    binaries=[],
    datas=[
        ('templates', 'templates'),
        ('static', 'static'),
        ('knowledge-base', 'knowledge-base'),
        ('prompts', 'prompts'),
        ('report_to_pdf.py', '.'),
        ('config.py', '.'),
    ],
    hiddenimports=[
        'uvicorn.loops.auto',
        'uvicorn.protocols.http.httptools_impl',
        'uvicorn.protocols.http.auto',
        'uvicorn.logging',
        'fastapi',
        'pydantic',
        'pydantic.deprecated.decorator',
        'sqlite3',
        'json',
        'asyncio',
        'fpdf',
        'importlib.util',
        'auto_analyzer',
        'config',
        'claude_api',
        'report_builder',
        'lunar_calendar',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tests',
        'docs',
        'reports',
        'quality',
        'tools',
        'matplotlib',
        'numpy',
        'scipy',
        'pandas',
        'playwright',
        'pytest',
        'pip',
        'setuptools',
        'tkinter',
    ],
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='XuanJiZi',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='XuanJiZi',
)

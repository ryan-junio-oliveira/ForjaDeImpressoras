"""
Gera o arquivo .spec do PyInstaller (Forja de Impressoras).

Uso:
    python scripts/gen_spec.py
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAIN_PY = os.path.join(ROOT, 'main.py').replace('\\', '/')
ICON_ICO = os.path.join(ROOT, 'app', 'resources', 'icon.ico').replace('\\', '/')
RES_DIR = os.path.join(ROOT, 'app', 'resources').replace('\\', '/')
STATIC_DIR = os.path.join(ROOT, 'app', 'presentation', 'static').replace('\\', '/')
DATA_DIR = os.path.join(ROOT, 'app', 'data').replace('\\', '/')
VERSION_FILE = os.path.join(ROOT, 'VERSION').replace('\\', '/')

print("[INFO] Gerando spec do PyInstaller")

excludes = [
    "unittest", "test", "distutils", "ensurepip", "venv", "lib2to3",
    "turtle", "idlelib", "pdb", "xmlrpc", "doctest", "tabnanny",
    "pickletools", "msilib", "json.tool", "compileall", "py_compile",
    "curses", "antigravity", "this", "smtplib", "telnetlib", "poplib",
    "imaplib", "nntplib",
    # nao usados (mantem QtWebEngine!)
    "matplotlib", "pandas", "scipy", "sympy", "notebook", "jupyter",
    "setuptools", "pip", "wheel", "IPython", "PyQt5", "PyQt6",
    "PySide2", "tornado", "django", "flask", "numpy",
    "lxml", "beautifulsoup4", "cssselect", "Cython",
    "pytest", "sphinx", "black", "flake8",
]
texcludes = ",".join(f"'{m}'" for m in excludes)

spec = f'''# -*- mode: python ; coding: utf-8 -*-
# Gerado por scripts/gen_spec.py — nao editar a mao.
block_cipher = None

a = Analysis(
    ['{MAIN_PY}'],
    pathex=[],
    binaries=[],
    datas=[
        ('{RES_DIR}', 'app/resources'),
        ('{STATIC_DIR}', 'app/presentation/static'),
        ('{DATA_DIR}', 'app/data'),
        ('{VERSION_FILE}', '.'),
    ],
    hiddenimports=[
        'PySide6.QtWebEngineWidgets',
        'PySide6.QtWebEngineCore',
        'app.core.scanner',
        'app.core.usb_scanner',
        'app.core.driver_manager',
        'app.core.driver_download',
        'app.core.printer_install',
        'app.presentation.api',
        'app.presentation.server',
        'app.presentation.desktop',
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[{texcludes}],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='ForjaDeImpressoras',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    uac_admin=True,
    icon='{ICON_ICO}',
)
'''

out_dir = os.path.join(ROOT, 'build', 'windows')
os.makedirs(out_dir, exist_ok=True)
out = os.path.join(out_dir, 'ForjaDeImpressoras.spec')
with open(out, 'w', encoding='utf-8') as fh:
    fh.write(spec)
print(f'[OK] spec gerado: {out}')

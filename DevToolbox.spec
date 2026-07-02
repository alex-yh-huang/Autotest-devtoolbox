# -*- mode: python ; coding: utf-8 -*-
# 打包指令：pyinstaller --clean DevToolbox.spec

from pathlib import Path
block_cipher = None
root = Path(SPECPATH)

a = Analysis(
    ['main.py'],
    pathex=[str(root)],
    binaries=[],
    datas=[
        (str(root / 'plugins'), 'plugins'),
        (str(root / 'core'), 'core'),
    ],
    hiddenimports=[
        'PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets',
        'PyQt6.QtDBus',
        'configparser', 'yaml', 'importlib.util', 'importlib.machinery',

        # plugins
        'plugins.p01_ssh_forwarder',
        'plugins.p02_ota_version_set',

        # PyMySQL
        'pymysql',
        'pymysql.cursors',
        'pymysql.connections',
        'pymysql.converters',
        'pymysql.err',
        'pymysql.optionfile',
        'pymysql.protocol',
        'pymysql.times',
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=[],
    cipher=block_cipher,
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name='DevToolbox',
    debug=False,
    strip=False,
    upx=False,
    console=False,
    runtime_tmpdir=None,
    uac_admin=False,
    # Windows DPI-aware manifest
    manifest='''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<assembly xmlns="urn:schemas-microsoft-com:asm.v1" manifestVersion="1.0">
  <application xmlns="urn:schemas-microsoft-com:asm.v3">
    <windowsSettings>
      <dpiAware xmlns="http://schemas.microsoft.com/SMI/2005/WindowsSettings">true/PM</dpiAware>
      <dpiAwareness xmlns="http://schemas.microsoft.com/SMI/2016/WindowsSettings">PerMonitorV2</dpiAwareness>
    </windowsSettings>
  </application>
</assembly>''',
)

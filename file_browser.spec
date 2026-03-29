# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec file for LAN File Browser
# 用途: CI 构建 和 scripts/build-release.sh 使用
# 输出名: lan-file-browser（小写横线，适合自动化发布）
# 另见: FileBrowser.spec（本地手动构建用，输出名 FileBrowser）

import os

# 需要嵌入的数据文件（打赏二维码、README 等）
datas = [
    ('docs/wechat_pay.jpg', 'docs'),
    ('docs/alipay.jpg', 'docs'),
    ('docs/bmc_qr.png', 'docs'),
    ('README.md', '.'),
    ('stop_server.bat', '.'),
    ('stop_server.sh', '.'),
    ('static', 'static'),
]

# 如果 docs/ 下还有其他文件也打包进去
docs_dir = 'docs'
if os.path.isdir(docs_dir):
    for f in os.listdir(docs_dir):
        full = os.path.join(docs_dir, f)
        if os.path.isfile(full) and (os.path.normpath(full), docs_dir) not in [(os.path.normpath(d[0]), d[1]) for d in datas]:
            datas.append((full, docs_dir))

a = Analysis(
    ['file_browser.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=['flask'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='lan-file-browser',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

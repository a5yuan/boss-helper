# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for BOSS Helper GUI.

打包模式: onedir（文件夹，含 .exe + 依赖）
输出目录: build/boss-helper/

使用方式:
    pyinstaller boss.spec
    或: python build_exe.py
"""
import os
import sys
import shutil
from pathlib import Path

block_cipher = None

# ============================================================================
# 版本号（与 src/__version__.py 保持一致）
# 改完记得：同步更新 src/__version__.py + git tag v{VERSION}
# ============================================================================
APP_NAME = "BOSS直聘助手"
APP_EXE_NAME = "BOSS直聘助手"
VERSION = "0.1.0"
COMPANY = "BOSS Helper"
COPYRIGHT = "Internal Use Only"
DESCRIPTION = "BOSS 直聘岗位信息整理与助手工具"

# ============================================================================
# Windows 版本资源（让右键属性→详细信息能看到版本/作者/公司）
# ============================================================================
try:
    try:
        from PyInstaller.utils.win32.versioninfo import (
            VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct,
        )
    except ImportError:
        from PyInstaller.utils.win32.version_info import (
            VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct,
        )
    VERSION_RESOURCE = VSVersionInfo(
        ffi=FixedFileInfo(
            filevers=(0, 1, 0, 0),     # 文件版本 0.1.0.0
            prodvers=(0, 1, 0, 0),     # 产品版本 0.1.0.0
            mask=0x3F,                 # 标准权限位
            flags=0x0,
            OS=0x40004,                # Win32 NT
            fileType=0x1,              # APP
            subtype=0x0,
            date=(0, 0),
        ),
        kids=[
            StringFileInfo([
                StringTable(
                    "080404b0",  # 简体中文 + Unicode
                    [
                        StringStruct("CompanyName", COMPANY),
                        StringStruct("FileDescription", DESCRIPTION),
                        StringStruct("FileVersion", VERSION),
                        StringStruct("InternalName", APP_EXE_NAME),
                        StringStruct("LegalCopyright", COPYRIGHT),
                        StringStruct("OriginalFilename", APP_EXE_NAME + ".exe"),
                        StringStruct("ProductName", APP_NAME),
                        StringStruct("ProductVersion", VERSION),
                    ],
                ),
            ]),
            StringFileInfo([  # 备用：英文
                StringTable(
                    "040904e4",
                    [
                        StringStruct("CompanyName", COMPANY),
                        StringStruct("FileDescription", "BOSS Helper Desktop Tool"),
                        StringStruct("FileVersion", VERSION),
                        StringStruct("ProductName", APP_NAME),
                        StringStruct("ProductVersion", VERSION),
                    ],
                ),
            ]),
        ],
    )
except Exception as _e:
    print(f"[WARN] 无法注入 Windows 版本资源（{_e}），右键属性将看不到版本号")
    VERSION_RESOURCE = None

# ============================================================================
# 路径常量
# ============================================================================
# __spec__ 由 PyInstaller 在执行 spec 文件时自动注入
PROJECT_ROOT = Path(__spec__.origin).parent.resolve()
SERVER_STATIC = PROJECT_ROOT / "server" / "static"
SRC_DIR = PROJECT_ROOT / "src"
SERVER_DIR = PROJECT_ROOT / "server"
BUILD_DIR = PROJECT_ROOT / "build"
DIST_DIR = PROJECT_ROOT / "dist"

# 确保 server/static 已有构建产物（前端必须先 npm run build）
if not SERVER_STATIC.exists():
    print("[WARN] server/static 不存在，前端可能未构建，跳过静态资源打包")
    STATIC_FILES = []
else:
    STATIC_FILES = [(str(SERVER_STATIC), "server/static")]

# ============================================================================
# PyInstaller 分析器
# ============================================================================
a = Analysis(
    [str(PROJECT_ROOT / "run_gui.py")],
    pathex=[str(PROJECT_ROOT)],
    binaries=[],
    datas=[
        # 静态资源
        *STATIC_FILES,
        # src/ 业务代码
        (str(SRC_DIR), "src"),
        # server/ 代码
        (str(SERVER_DIR), "server"),
    ],
    hiddenimports=[
        # FastAPI 全家桶
        "fastapi",
        "uvicorn",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "starlette",
        "starlette.applications",
        "starlette.routing",
        "starlette.middleware",
        "starlette.middleware.cors",
        "starlette.staticfiles",
        "starlette.responses",
        "pydantic",
        # 业务模块
        "src.config",
        "src.collector",
        "src.core",
        "src.core.cities",
        "src.utils",
        "src.utils.salary",
        "server.app",
        "server.session",
        # WebSocket
        "websocket",
        "websocket._abnf",
        # YAML
        "yaml",
        "yaml.parser",
        "yaml.scanner",
        # 其他常用
        "json",
        "glob",
        "urllib.request",
        "urllib.error",
    ],
    hookspath=[],
    hooksconfig={},
    keys=[],
    debug=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# ============================================================================
# 打包集合
# ============================================================================
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_EXE_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # GUI 模式：启动报错通过日志文件查看（见 run_gui.py 顶部重定向）
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='boss_helper.ico',             # 可替换为 .ico 文件路径
    version=VERSION_RESOURCE,  # Windows 资源：右键属性→详细信息能看到版本/作者/公司
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name=APP_EXE_NAME,
)

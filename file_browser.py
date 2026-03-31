# -*- coding: utf-8 -*-
"""
局域网文件浏览器 (LAN File Browser) v2.6.0
==========================================
一个运行在电脑端的 Web 文件浏览器，可通过手机（同局域网内）
使用浏览器访问 http://<电脑IP>:25600 来浏览、搜索、预览和下载电脑中的文件。

功能特性 v2.6.0:
  - 密码保护（启动时自动生成访问密码）
  - 访问日志（记录所有操作到日志文件）
  - 文件上传（手机上传文件到电脑）
  - 批量下载（多选文件打包 zip 下载）
  - 新建文件夹 / 删除 / 重命名
  - 剪贴板互传（手机和电脑共享文本）
  - 二维码显示（扫码直接访问）
  - 记住上次位置（自动回到上次浏览的目录）
  - 常用目录书签（收藏常用路径）
  - 文件内容搜索（搜索文件内部文字）
  - 在线预览：图片、视频、音频、PDF、Markdown、代码/文本

作者: 白白LOVE尹尹
协议: MIT

依赖:
  - Python 3.8+
  - Flask (pip install flask)

启动方式:
  python file_browser.py
"""

__version__ = "2.6.0"

import os
import sys
import io
import re
import hmac
import hashlib as _hl
import threading
import time
import shutil
import socket
import mimetypes
import secrets
import string
import json
import zipfile
import logging
import tempfile
import random as _rnd
from pathlib import Path
from datetime import datetime
from functools import wraps
from logging.handlers import RotatingFileHandler

from flask import (
    Flask, render_template_string, request, send_file,
    jsonify, abort, make_response, Response, stream_with_context,
)

# ════════════════════════════════════════════════════════════
# Flask 应用实例
# ════════════════════════════════════════════════════════════
# PyInstaller frozen 模式下，静态文件在 sys._MEIPASS 中；开发模式下在脚本同目录
if getattr(sys, 'frozen', False):
    _static_folder = os.path.join(sys._MEIPASS, 'static')
else:
    _static_folder = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
app = Flask(__name__, static_folder=_static_folder)
app.secret_key = secrets.token_hex(32)
app.config['MAX_CONTENT_LENGTH'] = None  # 不限制上传文件大小

# 关闭 Flask/Werkzeug 默认的启动横幅和开发服务器警告
import flask.cli
flask.cli.show_server_banner = lambda *a, **k: None
import logging as _logging
_logging.getLogger('werkzeug').setLevel(_logging.WARNING)

# ════════════════════════════════════════════════════════════
# 配置项（可根据需要修改）
# ════════════════════════════════════════════════════════════
PORT = 25600

# 密码保护: 设为 None 则自动生成 32 位高强度密码并在终端显示
# 设为空字符串 "" 则禁用密码保护
PASSWORD = None

# 允许访问的目录白名单（沙箱模式）
# 设为空列表 [] 则不限制，允许访问整台电脑的所有文件（默认行为）
# 设为目录列表则只能访问这些目录及其子目录中的文件，其它路径一律拒绝
# 示例: ALLOWED_ROOTS = ["D:/shared", "E:/projects"]
# 示例: ALLOWED_ROOTS = ["/home/user/public", "/tmp/shared"]
ALLOWED_ROOTS = []

# 只读模式: 设为 True 则禁用所有写操作（上传/删除/重命名/编辑/复制/移动/解压等）
# 适合教师分享课件等场景，学生只能浏览、预览和下载
READ_ONLY = False

# 多用户模式: 设为空字典 {} 则使用单密码模式（由 PASSWORD 控制）
# 设为用户字典则启用多用户模式，每个用户有独立密码和权限
# 权限: "admin"=完全权限, "readonly"=只读（只能浏览、预览、下载）
# 示例: USERS = {"teacher": {"password": "abc123", "role": "admin"},
#                "student": {"password": "stu456", "role": "readonly"}}
USERS = {}

# 阻止电脑睡眠: 设为 True 则服务运行期间阻止系统进入睡眠/休眠状态
# Windows 使用 SetThreadExecutionState API；macOS 使用 caffeinate 命令；Linux 使用 systemd-inhibit
PREVENT_SLEEP = True

# 数据文件存放目录
# PyInstaller --onefile 模式下:
#   DATA_DIR    = exe 所在目录（存放 bookmarks.json、access.log 等用户数据）
#   BUNDLE_DIR  = 内嵌资源目录（存放 README.md、收款码图片等）
if getattr(sys, 'frozen', False):
    DATA_DIR = os.path.dirname(os.path.abspath(sys.executable))
    BUNDLE_DIR = sys._MEIPASS
else:
    DATA_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = DATA_DIR
BOOKMARKS_FILE = os.path.join(DATA_DIR, "bookmarks.json")
ACCESS_LOG_FILE = os.path.join(DATA_DIR, "access.log")

# 登录速率限制
LOGIN_RATE_WINDOW = 60   # 检测窗口（秒）
LOGIN_RATE_MAX    = 10   # 窗口内单 IP 最多尝试次数，超出返回 429

# 搜索限制
SEARCH_MAX_RESULTS = 100    # 文件名搜索最大结果数
SEARCH_MAX_DEPTH = 6        # 文件名搜索最大递归深度
CONTENT_SEARCH_MAX_SIZE = 512 * 1024  # 内容搜索单文件大小上限 (512KB)
CONTENT_SEARCH_MAX_FILES = 500        # 内容搜索最大扫描文件数
CONTENT_SEARCH_MAX_RESULTS = 50       # 内容搜索最大结果数

# 系统关键目录黑名单（禁止删除），所有路径必须小写
_PROTECTED_PATHS = {
    # Windows 系统目录
    "c:\\windows", "c:\\program files", "c:\\program files (x86)",
    "c:\\users", "c:\\system32", "c:\\programdata",
    "c:\\windows\\system32", "c:\\windows\\syswow64",
    # macOS 特有
    "/users", "/applications", "/volumes",
    # Linux 补充
    "/snap", "/srv", "/media", "/mnt",
    # macOS / Linux 通用系统目录
    "/", "/bin", "/sbin", "/usr", "/etc", "/var", "/tmp",
    "/system", "/library", "/private",
    "/boot", "/dev", "/proc", "/sys", "/run",
    "/usr/bin", "/usr/sbin", "/usr/lib", "/usr/local",
    "/home", "/root", "/opt",
}
# Windows A:\ ~ Z:\ 全盘符根目录
_PROTECTED_PATHS |= {f"{chr(c)}:\\" for c in range(ord('a'), ord('z') + 1)}

# 操作系统隐藏文件（在文件列表中过滤）
_SYSTEM_HIDDEN_FILES = {'.DS_Store', 'Thumbs.db', 'desktop.ini',
                        '.Spotlight-V100', '.Trashes', '.fseventsd'}

# ════════════════════════════════════════════════════════════
# 全局状态
# ════════════════════════════════════════════════════════════
# 认证 token（启动时生成，单密码模式使用）
AUTH_TOKEN = secrets.token_hex(16)

# 多用户 session: {token: {"user": username, "role": "admin"|"readonly"}}
user_sessions = {}

# 共享剪贴板（内存存储，多用户模式按用户隔离）
# 结构: {user_key: {"text": "", "updated": ""}}
clipboard_data = {}

# 访问密码（启动时确定）
access_password = ""

# 登录速率限制: {ip: [timestamp1, timestamp2, ...]}
login_attempts = {}

# HTTPS 模式标志（在 main 块中根据 SSL 配置设置）
_use_https = False

# 临时分享链接: {token: {"path": str, "expires_at": float}}
share_tokens = {}

# 线程安全锁（保护上述全局字典的并发访问）
_state_lock = threading.Lock()

# ── 分片续传相关 ──
_CHUNK_SIZE = 5 * 1024 * 1024                           # 每个分片 5MB
_CHUNK_THRESHOLD = 5 * 1024 * 1024                       # 文件 ≥5MB 使用分片上传
_UPLOAD_TMP_DIR = os.path.join(tempfile.gettempdir(), "lan_fb_uploads")
_UPLOAD_SESSION_EXPIRY = 24 * 3600                       # 上传会话 24 小时过期
_upload_sessions = {}           # {upload_id: session_info}
_upload_sessions_lock = threading.Lock()

# ════════════════════════════════════════════════════════════
# API 错误消息国际化
# ════════════════════════════════════════════════════════════
_API_MESSAGES = {
    "readonly_mode":        {"zh": "当前为只读模式，禁止修改操作", "en": "Read-only mode, write operations are not allowed"},
    "readonly_role":        {"zh": "当前账户为只读权限，禁止修改操作", "en": "Your account has read-only access, write operations are not allowed"},
    "not_logged_in":        {"zh": "未登录", "en": "Not logged in"},
    "rate_limited":         {"zh": "尝试次数过多，请稍后再试", "en": "Too many attempts, please try again later"},
    "invalid_request":      {"zh": "请求无效", "en": "Invalid request"},
    "wrong_password":       {"zh": "密码错误", "en": "Wrong password"},
    "path_not_found":       {"zh": "路径不存在", "en": "Path not found"},
    "is_file_not_dir":      {"zh": "这是一个文件，不是目录", "en": "This is a file, not a directory"},
    "no_permission_dir":    {"zh": "没有权限访问此目录", "en": "No permission to access this directory"},
    "regex_too_long":       {"zh": "正则表达式过长", "en": "Regular expression too long"},
    "regex_nested":         {"zh": "不支持嵌套量词的正则表达式", "en": "Nested quantifiers in regex are not supported"},
    "file_not_found":       {"zh": "文件不存在", "en": "File not found"},
    "not_text_file":        {"zh": "不是文本文件", "en": "Not a text file"},
    "memory_error":         {"zh": "内存不足，文件过大", "en": "Out of memory, file too large"},
    "decode_error":         {"zh": "无法解码文件", "en": "Unable to decode file"},
    "file_protected_edit":  {"zh": "此文件受保护，无法编辑", "en": "This file is protected and cannot be edited"},
    "unsupported_edit":     {"zh": "不支持编辑此文件类型", "en": "Editing this file type is not supported"},
    "no_permission_write":  {"zh": "没有权限写入此文件", "en": "No permission to write this file"},
    "dir_not_found":        {"zh": "目录不存在", "en": "Directory not found"},
    "path_not_exist":       {"zh": "路径不存在", "en": "Path does not exist"},
    "no_files_selected":    {"zh": "没有选择文件", "en": "No files selected"},
    "memory_pack_error":    {"zh": "内存不足，文件过大无法打包", "en": "Out of memory, files too large to pack"},
    "target_dir_not_found": {"zh": "目标目录不存在", "en": "Target directory not found"},
    "no_upload_files":      {"zh": "没有上传文件", "en": "No files uploaded"},
    "folder_name_empty":    {"zh": "文件夹名不能为空", "en": "Folder name cannot be empty"},
    "folder_name_invalid":  {"zh": "文件夹名包含非法字符", "en": "Folder name contains invalid characters"},
    "parent_not_found":     {"zh": "父目录不存在", "en": "Parent directory not found"},
    "name_exists":          {"zh": "该名称已存在", "en": "This name already exists"},
    "filename_empty":       {"zh": "文件名不能为空", "en": "Filename cannot be empty"},
    "filename_invalid":     {"zh": "文件名包含非法字符", "en": "Filename contains invalid characters"},
    "filename_exists":      {"zh": "该文件名已存在", "en": "This filename already exists"},
    "no_permission_create": {"zh": "没有权限在此目录创建文件", "en": "No permission to create files in this directory"},
    "file_protected_del":   {"zh": "此文件受保护，无法删除", "en": "This file is protected and cannot be deleted"},
    "protected_sys_dir":    {"zh": "禁止删除系统关键目录", "en": "Deleting system directories is not allowed"},
    "dir_not_empty":        {"zh": "文件夹不为空", "en": "Folder is not empty"},
    "unknown_type":         {"zh": "未知的文件类型", "en": "Unknown file type"},
    "no_permission_del":    {"zh": "没有权限删除", "en": "No permission to delete"},
    "new_name_empty":       {"zh": "新名称不能为空", "en": "New name cannot be empty"},
    "name_invalid":         {"zh": "名称包含非法字符", "en": "Name contains invalid characters"},
    "file_protected_rename":{"zh": "此文件受保护，无法重命名", "en": "This file is protected and cannot be renamed"},
    "name_exists_rename":   {"zh": "该名称已存在", "en": "This name already exists"},
    "no_permission_rename": {"zh": "没有权限重命名", "en": "No permission to rename"},
    "path_empty":           {"zh": "路径不能为空", "en": "Path cannot be empty"},
    "already_bookmarked":   {"zh": "该路径已收藏", "en": "This path is already bookmarked"},
    "src_not_found":        {"zh": "源路径不存在", "en": "Source path not found"},
    "dest_dir_not_found":   {"zh": "目标目录不存在", "en": "Destination directory not found"},
    "no_permission":        {"zh": "没有权限", "en": "No permission"},
    "file_protected_move":  {"zh": "此文件受保护，无法移动", "en": "This file is protected and cannot be moved"},
    "move_into_self":       {"zh": "不能将文件夹移动到自身或其子目录中", "en": "Cannot move a folder into itself or its subdirectory"},
    "dest_name_conflict":   {"zh": "目标目录中已存在同名文件/文件夹", "en": "A file/folder with the same name already exists in the destination"},
    "zip_not_found":        {"zh": "ZIP 文件不存在", "en": "ZIP file not found"},
    "invalid_zip":          {"zh": "不是有效的 ZIP 文件", "en": "Not a valid ZIP file"},
    "no_permission_extract":{"zh": "没有权限解压到该目录", "en": "No permission to extract to this directory"},
    "calc_timeout":         {"zh": "计算超时", "en": "Calculation timed out"},
    "regex_error":          {"zh": "正则表达式错误", "en": "Regular expression error"},
    "zip_illegal_path":     {"zh": "ZIP 包含非法路径", "en": "ZIP contains illegal path"},
    "upload_path_traversal":{"zh": "上传路径包含非法遍历", "en": "Upload path contains illegal traversal"},
    "upload_session_expired":{"zh":"上传会话不存在或已过期","en":"Upload session not found or expired"},
    "upload_no_chunk":      {"zh": "未收到分片数据", "en": "No chunk data received"},
    "upload_temp_missing":  {"zh": "临时文件丢失", "en": "Temporary file missing"},
    "internal_error":       {"zh": "内部服务器错误", "en": "Internal server error"},
}

def _api_t(key):
    """根据当前请求的语言偏好返回对应的 API 错误消息。"""
    msgs = _API_MESSAGES.get(key)
    if not msgs:
        return key
    # 语言检测优先级: cookie fb_lang > Accept-Language > 默认中文
    try:
        lang = request.cookies.get("fb_lang", "")
        if not lang:
            accept = request.headers.get("Accept-Language", "")
            lang = "en" if accept and not accept.lower().startswith("zh") else "zh"
    except RuntimeError:
        lang = "zh"
    return msgs.get(lang, msgs.get("zh", key))

_RES_MARKERS = ['\u767d\u767dLOVE\u5c39\u5c39', 'LFB-bbloveyy-2026',
                'bbyybb', 'buymeacoffee.com/bbyybb', 'sponsors/bbyybb']
_RES_EXPECTED = 'c908d591dce0b0df'

_SEAL_HASHES = {
    "README.md": "af0b52196bd8cfa8471f743aaaceb9e42701ec6486eb09da188d4f238f082314",
    "docs/wechat_pay.jpg": "686b9d5bba59d6831580984cb93804543f346d943f2baf4a94216fd13438f1e6",
    "docs/alipay.jpg": "510155042b703d23f7eeabc04496097a7cc13772c5712c8d0716bab5962172dd",
    "docs/bmc_qr.png": "bfd20ef305007c3dacf30dde49ce8f0fe4d7ac3ffcc86ac1f83bc1e75cccfcd6",
}

def _check_res_integrity(tpl):
    for m in _RES_MARKERS:
        if m not in tpl:
            return False
    sig = _hl.sha256('|'.join(sorted(_RES_MARKERS)).encode()).hexdigest()[:16]
    return hmac.compare_digest(sig, _RES_EXPECTED)

def _check_file_integrity():
    if len(_SEAL_HASHES) < 2:
        return False, ["_SEAL_HASHES has been cleared or corrupted"]
    tampered = []
    for rel_path, expected_hash in _SEAL_HASHES.items():
        full_path = os.path.join(BUNDLE_DIR, rel_path)
        if not os.path.isfile(full_path):
            tampered.append(f"{rel_path} (missing)")
            continue
        with open(full_path, 'rb') as f:
            actual = _hl.sha256(f.read()).hexdigest()
        if not hmac.compare_digest(actual, expected_hash):
            tampered.append(f"{rel_path} (modified)")
    return len(tampered) == 0, tampered


def _is_sealed_path(real_path):
    if not _SEAL_HASHES:
        return False
    try:
        real_norm = os.path.normpath(os.path.realpath(real_path))
        for rel_path in _SEAL_HASHES:
            sealed = os.path.normpath(os.path.realpath(os.path.join(BUNDLE_DIR, rel_path)))
            if real_norm == sealed:
                return True
    except Exception:
        pass
    return False


# ════════════════════════════════════════════════════════════
# 内部辅助
# ════════════════════════════════════════════════════════════

def _init_render_engine():
    _f1 = globals().get('_check_res_integrity')
    _f2 = globals().get('_check_file_integrity')
    if _f1 is None or _f2 is None or not callable(_f1) or not callable(_f2):
        return False
    _m = globals().get('_RES_MARKERS', [])
    if len(_m) < 5:
        return False
    _names1 = getattr(getattr(_f1, '__code__', None), 'co_names', ())
    if '_RES_MARKERS' not in _names1:
        return False
    return True


def _resolve_template_vars(t=None):
    _tpl = globals().get('HTML_TEMPLATE', '')
    if not _tpl:
        return True
    _m = globals().get('_RES_MARKERS', [])
    if len(_m) < 5:
        return False
    for _k in _m:
        if _k not in _tpl:
            return False
    _ire = globals().get('_init_render_engine')
    if not callable(_ire):
        return False
    _consts2 = getattr(getattr(_ire, '__code__', None), 'co_consts', ())
    if '_check_res_integrity' not in _consts2:
        return False
    return True


# ════════════════════════════════════════════════════════════
# 只读模式守卫
# ════════════════════════════════════════════════════════════

def require_writable(f):
    """
    写操作守卫装饰器：
    - 全局 READ_ONLY=True 时拒绝所有写操作
    - 多用户模式下 readonly 角色拒绝写操作
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        if READ_ONLY:
            return jsonify({"error": _api_t("readonly_mode")}), 403
        # 多用户模式下检查角色
        if USERS:
            role = _get_current_role()
            if role == "readonly":
                return jsonify({"error": _api_t("readonly_role")}), 403
        return f(*args, **kwargs)
    return decorated


# ════════════════════════════════════════════════════════════
# 访问日志
# ════════════════════════════════════════════════════════════
def setup_access_log():
    """配置访问日志记录器，将日志写入文件。"""
    logger = logging.getLogger("access")
    logger.setLevel(logging.INFO)
    # 避免重复添加 handler
    if not logger.handlers:
        handler = RotatingFileHandler(
            ACCESS_LOG_FILE, maxBytes=10*1024*1024, backupCount=5, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        ))
        logger.addHandler(handler)
    return logger

try:
    access_logger = setup_access_log()
except Exception:
    # 日志文件创建失败时（如只读目录），使用空日志器，不阻止服务启动
    access_logger = logging.getLogger("access_fallback")
    access_logger.addHandler(logging.NullHandler())

def log_access(action, detail=""):
    """
    记录一条访问日志（同时写入文件和终端）。

    Args:
        action (str): 操作类型，如 "LOGIN", "BROWSE", "DOWNLOAD"
        detail (str): 操作详情，如文件路径
    """
    ip = request.remote_addr or "unknown"
    msg = f"{ip} | {action} | {detail}"
    access_logger.info(msg)
    # 同时输出到终端（stderr，避免被 Flask 缓冲）
    try:
        ts = datetime.now().strftime("%H:%M:%S")
        sys.stderr.write(f"  {ts} {msg}\n")
        sys.stderr.flush()
    except Exception:
        pass


# ════════════════════════════════════════════════════════════
# 认证中间件
# ════════════════════════════════════════════════════════════
def _get_current_role():
    """获取当前请求用户的角色。返回 "admin"/"readonly"/None(未登录)。"""
    token = request.cookies.get("auth_token", "")
    if not token:
        return None
    # 多用户模式
    with _state_lock:
        if USERS and token in user_sessions:
            user_sessions[token]["last_active"] = time.time()
            return user_sessions[token]["role"]
    # 单密码模式
    if not USERS and hmac.compare_digest(token, AUTH_TOKEN):
        return "admin"
    return None

def _get_current_username():
    """获取当前请求的用户名。多用户模式返回用户名，单密码/无密码返回 None。"""
    token = request.cookies.get("auth_token", "")
    if not token:
        return None
    with _state_lock:
        if USERS and token in user_sessions:
            return user_sessions[token]["user"]
    return None


def _clipboard_key():
    """获取当前用户的剪贴板隔离键。"""
    if USERS:
        u = _get_current_username()
        return u if u else "_default"
    return "_default"


def require_auth(f):
    """
    认证装饰器：检查请求中的 token cookie 是否有效。
    支持单密码模式和多用户模式。
    """
    @wraps(f)
    def decorated(*args, **kwargs):
        # 密码为空且无多用户配置，禁用密码保护
        if not access_password and not USERS:
            return f(*args, **kwargs)
        role = _get_current_role()
        if role is None:
            return jsonify({"error": _api_t("not_logged_in"), "auth_required": True}), 401
        # 轻量完整性二次校验：每次请求快速确认关键标识仍在模板中
        # 使用计数器隔离，每 50 次请求校验一次，不影响性能
        require_auth._req_count = getattr(require_auth, '_req_count', 0) + 1
        if require_auth._req_count % 50 == 0:
            if not all(m in HTML_TEMPLATE for m in _RES_MARKERS):
                return jsonify({"error": "Service unavailable"}), 503
        return f(*args, **kwargs)
    return decorated


# ════════════════════════════════════════════════════════════
# 阻止系统睡眠
# ════════════════════════════════════════════════════════════

_sleep_inhibit_process = None  # macOS/Linux 子进程引用

def prevent_sleep_start():
    """
    阻止操作系统进入睡眠/休眠状态。
    - Windows: 调用 SetThreadExecutionState API
    - macOS: 启动 caffeinate -i -w <pid> 子进程
    - Linux: 启动 systemd-inhibit 子进程
    服务退出时自动恢复（Windows API 自动重置；子进程随父进程终止）。
    """
    global _sleep_inhibit_process
    import subprocess

    if sys.platform == 'win32':
        try:
            import ctypes
            # ES_CONTINUOUS | ES_SYSTEM_REQUIRED: 阻止系统空闲睡眠
            ES_CONTINUOUS = 0x80000000
            ES_SYSTEM_REQUIRED = 0x00000001
            ctypes.windll.kernel32.SetThreadExecutionState(
                ES_CONTINUOUS | ES_SYSTEM_REQUIRED
            )
            return True
        except Exception:
            return False
    elif sys.platform == 'darwin':
        # caffeinate -i: 阻止空闲睡眠; -w <pid>: 父进程退出后自动终止
        try:
            _sleep_inhibit_process = subprocess.Popen(
                ['caffeinate', '-i', '-w', str(os.getpid())],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            return True
        except Exception:
            return False
    else:
        # Linux: 尝试 systemd-inhibit
        try:
            _sleep_inhibit_process = subprocess.Popen(
                ['systemd-inhibit', '--what=idle', '--who=FileBrowser',
                 '--reason=LAN File Browser is running',
                 'sleep', 'infinity'],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
            )
            return True
        except Exception:
            return False


def prevent_sleep_stop():
    """恢复系统正常睡眠行为。"""
    global _sleep_inhibit_process
    if sys.platform == 'win32':
        try:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000)  # ES_CONTINUOUS only
        except Exception:
            pass
    if _sleep_inhibit_process:
        try:
            _sleep_inhibit_process.terminate()
        except Exception:
            pass
        _sleep_inhibit_process = None


# ════════════════════════════════════════════════════════════
# 工具函数
# ════════════════════════════════════════════════════════════

def get_drives():
    """
    获取首页显示的根目录列表。
    如果配置了 ALLOWED_ROOTS 白名单，则只返回白名单中的目录；
    否则 Windows 遍历 A-Z 盘符，Linux/macOS 返回 "/"。
    """
    if ALLOWED_ROOTS:
        return [os.path.normpath(r) for r in ALLOWED_ROOTS if os.path.isdir(r)]
    drives = []
    if sys.platform == 'win32':
        import string as str_mod
        for letter in str_mod.ascii_uppercase:
            drive = f"{letter}:\\"
            if os.path.exists(drive):
                drives.append(drive)
    else:
        drives.append("/")
    return drives


def get_local_ip():
    """
    获取本机局域网 IP 地址。
    优先通过 UDP 探测（无需外网），失败时遍历所有网卡接口。
    纯局域网（无默认网关）环境也能正确返回局域网 IP。
    """
    # 方法 1: UDP connect 探测（经典方法）
    # 优先尝试局域网广播地址，不依赖外网可达性
    for probe_addr in ("10.255.255.255", "8.8.8.8"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.1)
            s.connect((probe_addr, 80))
            ip = s.getsockname()[0]
            s.close()
            if ip and ip != "0.0.0.0" and not ip.startswith("127."):
                return ip
        except Exception:
            pass

    # 方法 2: 遍历所有网卡接口（兜底方案）
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127."):
                return ip
    except Exception:
        pass

    return "127.0.0.1"


def format_size(size_bytes):
    """将字节数格式化为人类可读的大小字符串。"""
    if size_bytes < 1024:
        return f"{size_bytes} B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f} KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f} MB"
    else:
        return f"{size_bytes / (1024 * 1024 * 1024):.2f} GB"


def format_time(timestamp):
    """将 Unix 时间戳格式化为日期时间字符串。"""
    return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M")


_FILE_TYPE_MAP = {
        'image': {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp', '.svg', '.ico', '.tiff', '.tif'},
        'video': {'.mp4', '.webm', '.mkv', '.avi', '.mov', '.flv', '.wmv', '.m4v', '.3gp'},
        'audio': {'.mp3', '.wav', '.ogg', '.flac', '.aac', '.wma', '.m4a', '.opus'},
        'markdown': {'.md', '.markdown', '.mdown', '.mkd'},
        'text': {
            # 纯文本 / 数据
            '.txt', '.text', '.log', '.csv', '.tsv', '.nfo',
            # Web 前端
            '.html', '.htm', '.css', '.js', '.ts', '.jsx', '.tsx', '.vue', '.svelte',
            '.scss', '.sass', '.less', '.styl', '.astro',
            '.ejs', '.hbs', '.pug', '.njk', '.liquid', '.twig',
            '.wxml', '.wxss',
            '.mjs', '.cjs', '.mts', '.cts',     # Node.js 模块格式
            '.coffee', '.litcoffee',             # CoffeeScript
            '.mdx', '.svx',                      # MDX / Svelte Markdown
            # 模板引擎
            '.erb', '.haml', '.slim',            # Ruby 模板
            '.j2', '.jinja', '.jinja2',          # Jinja 模板
            '.tmpl', '.tpl', '.mustache',        # 通用模板
            # 服务端页面
            '.jsp', '.asp', '.aspx', '.phtml',
            # 数据格式
            '.json', '.jsonc', '.json5', '.ndjson', '.jsonl', '.geojson',
            '.xml', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf',
            '.proto', '.avsc',
            '.jsonnet', '.libsonnet',            # Jsonnet 配置语言
            '.dhall',                            # Dhall 配置语言
            # 主流编程语言
            '.py', '.pyw', '.pyi',
            '.java', '.kt', '.kts', '.scala', '.groovy', '.gradle',
            '.c', '.h', '.cpp', '.hpp', '.cc', '.cxx', '.hxx', '.m', '.mm',
            '.cs', '.fs', '.fsx', '.vb',
            '.go', '.rs', '.swift', '.dart', '.zig', '.nim', '.v', '.d',
            '.rb', '.php', '.pl', '.pm', '.lua', '.r', '.jl',
            '.sql', '.prisma',
            # 函数式 / 脚本语言
            '.hs', '.lhs', '.ml', '.mli', '.ex', '.exs', '.erl', '.hrl',
            '.clj', '.cljs', '.lisp', '.el', '.rkt', '.tcl',
            '.cr', '.hx',
            '.elm', '.purs',                     # Elm / PureScript
            '.res', '.resi', '.re', '.rei',      # ReScript / ReasonML
            '.scm', '.ss',                       # Scheme
            '.sml', '.sig',                      # Standard ML
            '.idr', '.agda', '.lean',            # 依赖类型语言
            # Raku / Perl6
            '.raku', '.rakumod',
            # Fortran
            '.f', '.f90', '.f95', '.f03', '.f08', '.for', '.fpp',
            # Pascal / Delphi
            '.pas', '.pp', '.lpr', '.dpr',
            # COBOL
            '.cob', '.cbl',
            # Ada
            '.ada', '.adb', '.ads',
            # 区块链 / 智能合约
            '.sol', '.vy',
            # GPU / 着色器语言
            '.glsl', '.hlsl', '.wgsl', '.metal', '.vert', '.frag', '.comp',
            '.cu', '.cuh',                       # CUDA
            # Shell / 终端
            '.sh', '.bash', '.zsh', '.fish', '.csh', '.ksh',
            '.bat', '.cmd', '.ps1', '.psm1',
            # AutoHotkey / AutoIt
            '.ahk', '.au3',
            # Awk / Sed
            '.awk', '.sed',
            # AppleScript
            '.applescript',
            # Nix
            '.nix',
            # 系统配置 — Windows
            '.reg', '.inf', '.vbs', '.vba', '.wsf',
            # 系统配置 — macOS / iOS
            '.plist', '.strings', '.entitlements', '.pbxproj',
            # 系统配置 — Linux
            '.desktop', '.service', '.timer', '.socket', '.mount',
            # DevOps / CI / 构建
            '.tf', '.tfvars', '.hcl', '.properties', '.sbt', '.cmake',
            '.mk', '.mak', '.cabal', '.gemspec', '.podspec',
            # .NET / Visual Studio 项目文件（XML 文本）
            '.csproj', '.vbproj', '.fsproj', '.sln', '.vcxproj',
            # Spec 文件
            '.spec',
            # Web 服务器 / API
            '.htaccess', '.nginx', '.graphql', '.gql',
            # 文档 / 标记
            '.rst', '.asciidoc', '.adoc', '.tex', '.latex', '.bib', '.sty', '.cls',
            '.dtd', '.xsd', '.xsl', '.xslt',
            '.org',                              # Emacs Org Mode
            '.rmd', '.rnw',                      # R Markdown / Sweave
            '.typ',                              # Typst
            # 字幕
            '.srt', '.vtt', '.ass', '.ssa', '.sub', '.lrc',
            # 多媒体播放列表 / 元数据（纯文本）
            '.m3u', '.m3u8', '.cue',
            # 日历 / 通讯录（纯文本）
            '.ics', '.vcf',
            # 证书 / 密钥（Base64 文本）
            '.pem', '.crt', '.csr', '.key', '.pub', '.cer',
            # Diff / Patch
            '.diff', '.patch',
            # 汇编
            '.asm', '.s',
            # 点文件扩展名（匹配 something.dockerfile 等复合文件名）
            '.dockerfile',
        },
        'pdf': {'.pdf'},
        'archive': {'.zip', '.rar', '.7z', '.tar', '.gz', '.bz2', '.xz', '.zst', '.tgz'},
        'office': {'.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx', '.odt', '.ods', '.odp', '.rtf'},
        'font': {'.ttf', '.otf', '.woff', '.woff2'},
    }

_TEXT_FILENAMES = {
        # 构建 / 项目文件
        'makefile', 'dockerfile', 'containerfile', 'vagrantfile',
        'gemfile', 'rakefile', 'procfile', 'brewfile', 'justfile',
        'cmakelists.txt', 'jenkinsfile', 'snakefile',
        'sconscript', 'sconstruct', 'podfile', 'cartfile',
        'fastfile', 'appfile', 'dangerfile', 'guardfile',
        'berksfile', 'capfile', 'thorfile', 'earthfile', 'tiltfile',
        # Bazel / Buck
        'build', 'build.bazel', 'workspace', 'workspace.bazel', 'buck',
        # Go
        'go.mod', 'go.sum',
        # Python
        'pipfile',
        # 项目说明文件
        'license', 'licence', 'authors', 'contributors', 'changelog',
        'readme', 'todo', 'copying', 'install', 'news', 'thanks',
        # Git
        '.gitignore', '.gitattributes', '.gitmodules', '.gitconfig',
        '.gitkeep', '.mailmap',
        # Docker / CI
        '.dockerignore', '.dockerfile',
        # 各种 ignore 文件
        '.prettierignore', '.eslintignore', '.helmignore', '.slugignore',
        # 编辑器 / IDE 配置
        '.editorconfig', '.prettierrc', '.eslintrc', '.stylelintrc',
        '.babelrc', '.npmrc', '.yarnrc', '.nvmrc', '.pylintrc', '.flake8',
        '.vimrc', '.viminfo', '.gvimrc', '.nanorc', '.emacs',
        '.clang-format', '.clang-tidy',
        '.yamllint', '.markdownlint', '.rubocop',
        # 版本管理器
        '.ruby-version', '.python-version', '.node-version', '.java-version',
        '.tool-versions',
        # 环境变量
        '.env', '.env.local', '.env.development', '.env.production',
        '.env.test', '.env.staging', '.env.example',
        # Shell 配置
        '.profile', '.login', '.logout',
        '.bashrc', '.bash_profile', '.bash_login', '.bash_logout', '.bash_aliases',
        '.zshrc', '.zshenv', '.zprofile', '.zlogin', '.zlogout',
        '.cshrc', '.tcshrc', '.inputrc',
        # Shell 历史
        '.bash_history', '.zsh_history', '.history',
        # 网络 / 工具配置
        '.wgetrc', '.curlrc', '.screenrc', '.netrc', '.htpasswd',
        '.condarc', '.gemrc',
    }


def get_file_type(filename):
    """根据文件扩展名判断文件类别。"""
    ext = Path(filename).suffix.lower()
    for ftype, exts in _FILE_TYPE_MAP.items():
        if ext in exts:
            return ftype
    if Path(filename).name.lower() in _TEXT_FILENAMES:
        return 'text'
    return 'other'


def get_file_icon(file_type, is_dir=False):
    """返回文件类型对应的 Emoji 图标。"""
    if is_dir:
        return '\U0001f4c1'
    icons = {
        'image': '\U0001f5bc\ufe0f', 'video': '\U0001f3ac', 'audio': '\U0001f3b5',
        'markdown': '\U0001f4d8', 'text': '\U0001f4dd', 'pdf': '\U0001f4d5',
        'archive': '\U0001f4e6', 'office': '\U0001f4ca', 'font': '\U0001f524',
        'other': '\U0001f4c4',
    }
    return icons.get(file_type, '\U0001f4c4')


def safe_path(raw_path):
    """
    安全地将前端传入的路径转为本地路径。
    规范化路径并验证存在性。
    如果配置了 ALLOWED_ROOTS 白名单，还会检查路径是否在允许的目录范围内。
    """
    if not raw_path:
        return None
    p = os.path.normpath(raw_path)
    # Windows 盘符根目录修正: "D:" → "D:\"，避免 os.scandir("D:") 返回相对路径
    if sys.platform == 'win32' and len(p) == 2 and p[1] == ':':
        p = p + os.sep
    if not os.path.exists(p):
        return None
    # 白名单模式：检查路径是否在允许的根目录及其子目录中
    if ALLOWED_ROOTS:
        real = os.path.realpath(p)
        allowed = False
        for root in ALLOWED_ROOTS:
            root_real = os.path.realpath(os.path.normpath(root))
            # Windows 文件系统不区分大小写，统一转小写比较
            if sys.platform == 'win32':
                real_cmp = real.lower()
                root_cmp = root_real.lower()
            else:
                real_cmp = real
                root_cmp = root_real
            # 去掉尾部分隔符后再加，防止 Windows 盘符根目录（E:\）重复分隔符
            root_prefix = root_cmp.rstrip(os.sep) + os.sep
            if real_cmp == root_cmp or real_cmp.startswith(root_prefix):
                allowed = True
                break
        if not allowed:
            return None
    return p


def detect_encoding(filepath):
    """
    检测文件编码。依次尝试 utf-8 -> gbk -> gb18030 -> latin-1。
    只读取前 8KB 进行探测，避免大文件性能问题。

    Returns:
        str | None: 检测到的编码名称，全部失败返回 None
    """
    _DETECT_SIZE = 8192
    try:
        with open(filepath, 'rb') as f:
            raw = f.read(_DETECT_SIZE)
    except OSError:
        return None
    for enc in ['utf-8', 'gbk', 'gb18030', 'latin-1']:
        try:
            raw.decode(enc)
            return enc
        except (UnicodeDecodeError, UnicodeError):
            continue
    return None


def read_text_file(filepath, max_size=0):
    """
    安全读取文本文件，自动检测编码。
    依次尝试 utf-8 -> gbk -> gb18030 -> latin-1。
    max_size=0 表示不限制大小。

    Returns:
        str | None: 文件内容，读取失败返回 None
    """
    if max_size and os.path.getsize(filepath) > max_size:
        return None
    for enc in ['utf-8', 'gbk', 'gb18030', 'latin-1']:
        try:
            with open(filepath, 'r', encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    return None


def _bookmarks_file(username=None):
    """获取书签文件路径（多用户模式按用户隔离）。"""
    if username:
        safe_name = re.sub(r'[^\w\-]', '_', username)
        return os.path.join(DATA_DIR, f"bookmarks_{safe_name}.json")
    return BOOKMARKS_FILE


def load_bookmarks(username=None):
    """从 JSON 文件加载书签列表。"""
    filepath = _bookmarks_file(username)
    if os.path.exists(filepath):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def save_bookmarks(bookmarks, username=None):
    """将书签列表保存到 JSON 文件。"""
    filepath = _bookmarks_file(username)
    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(bookmarks, f, ensure_ascii=False, indent=2)
    except (IOError, OSError) as e:
        app.logger.error("Failed to save bookmarks to %s: %s", filepath, e)


def _is_dangerous_regex(pattern_str):
    """
    检测可能导致灾难性回溯 (ReDoS) 的正则表达式模式。
    检测嵌套量词（如 (a+)+, (?:a+)+, (a{2,})*, ([a-z]+)+ 等）。
    """
    # 匹配各种形式的分组（普通分组、非捕获分组等），内含量词，外接量词
    # (?:...) | (?=...) | (?!...) | (?<=...) | (?<!...) | (...)
    dangerous_patterns = [
        r'\([^)]*[+*][^)]*\)[+*?]',           # (a+)+, (a*)*
        r'\(\?[^)]*[+*][^)]*\)[+*?]',         # (?:a+)+, (?:a*)*
        r'\([^)]*\{[0-9]*,[0-9]*\}[^)]*\)[+*?]',  # (a{2,})+
        r'\[[^\]]+\][+*]\)+[+*?]',            # ([a-z]+)+
    ]
    for dp in dangerous_patterns:
        if re.search(dp, pattern_str):
            return True
    return False


# ════════════════════════════════════════════════════════════
# 请求预处理
# ════════════════════════════════════════════════════════════


@app.after_request
def _add_security_headers(response):
    """添加安全响应头。"""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline' blob:; "
        "style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; "
        "font-src 'self' data:; "
        "connect-src 'self'; "
        "media-src 'self' blob:; "
        "frame-src 'self' blob:; "
        "object-src 'none'; "
        "base-uri 'self'"
    )
    return response


@app.before_request
def _enforce_security_policy():
    # CSRF 保护: 所有 POST 请求（除 /api/login 和文件上传外）必须携带自定义 Header
    # 浏览器同源策略阻止跨站请求设置自定义 Header，因此这能有效防御 CSRF
    if request.method in ("POST", "DELETE", "PUT", "PATCH") and request.path not in ("/api/login",):
        # 所有修改型请求必须携带自定义 Header（浏览器同源策略阻止跨站设置）
        if request.headers.get("X-Requested-With") != "XMLHttpRequest":
            return jsonify({"error": _api_t("invalid_request")}), 403
    if _rnd.random() < 0.03:
        if not _resolve_template_vars():
            abort(503)
        if not _init_render_engine():
            abort(503)
    # 低概率清理过期分享 token（约 1% 请求触发，避免内存持续增长）
    if share_tokens and _rnd.random() < 0.01:
        now_ts = time.time()
        with _state_lock:
            expired = [k for k, v in share_tokens.items() if now_ts > v["expires_at"]]
            for k in expired:
                share_tokens.pop(k, None)


# ════════════════════════════════════════════════════════════
# API 路由 — 认证
# ════════════════════════════════════════════════════════════

@app.route("/")
def index():
    """返回单页面应用 HTML。"""
    return render_template_string(HTML_TEMPLATE, server_lang=app.config.get("SERVER_LANG", "auto"))


@app.route("/api/login", methods=["POST"])
def api_login():
    """
    登录接口。支持单密码模式和多用户模式。

    请求体: {"password": "xxx"}
    """
    # 密码保护已禁用且无多用户配置
    if not access_password and not USERS:
        resp = make_response(jsonify({"ok": True}))
        return resp

    # ── 速率限制 ──
    ip = request.remote_addr or "unknown"
    now = datetime.now().timestamp()
    with _state_lock:
        # 清理过期条目；若仍超过上限则强制淘汰最旧条目（防止分布式攻击下内存泄漏）
        if len(login_attempts) > 100:
            expired_ips = [k for k, v in login_attempts.items() if all(now - ts > LOGIN_RATE_WINDOW for ts in v)]
            for k in expired_ips:
                del login_attempts[k]
        if len(login_attempts) > 10000:
            to_remove = sorted(login_attempts, key=lambda k: max(login_attempts[k]))[:len(login_attempts) - 5000]
            for k in to_remove:
                del login_attempts[k]
        timestamps = login_attempts.get(ip, [])
        timestamps = [t for t in timestamps if now - t < LOGIN_RATE_WINDOW]
        if len(timestamps) >= LOGIN_RATE_MAX:
            log_access("LOGIN", f"rate_limited ip={ip}")
            return jsonify({"ok": False, "error": _api_t("rate_limited")}), 429
        timestamps.append(now)
        login_attempts[ip] = timestamps

    if request.content_length and request.content_length > 1024:
        return jsonify({"ok": False, "error": _api_t("invalid_request")}), 400

    data = request.get_json(silent=True) or {}
    pwd = data.get("password", "")

    # ── 多用户模式 ──
    if USERS:
        for username, info in USERS.items():
            if hmac.compare_digest(pwd, info.get("password", "")):
                role = info.get("role", "readonly")
                token = secrets.token_hex(16)
                with _state_lock:
                    # 限制 session 数量，按最后活跃时间淘汰最不活跃的
                    if len(user_sessions) > 1000:
                        by_active = sorted(user_sessions, key=lambda k: user_sessions[k].get("last_active", 0))
                        for k in by_active[:len(user_sessions) - 500]:
                            del user_sessions[k]
                    user_sessions[token] = {"user": username, "role": role, "last_active": time.time()}
                    login_attempts.pop(ip, None)
                log_access("LOGIN", f"success user={username} role={role}")
                resp = make_response(jsonify({"ok": True, "user": username, "role": role}))
                resp.set_cookie("auth_token", token, httponly=True, samesite="Lax", secure=_use_https)
                return resp
        log_access("LOGIN", f"failed ip={ip}")
        return jsonify({"ok": False, "error": _api_t("wrong_password")}), 401

    # ── 单密码模式 ──
    if hmac.compare_digest(pwd, access_password):
        log_access("LOGIN", "success")
        with _state_lock:
            login_attempts.pop(ip, None)
        resp = make_response(jsonify({"ok": True}))
        resp.set_cookie("auth_token", AUTH_TOKEN, httponly=True, samesite="Lax", secure=_use_https)
        return resp
    else:
        log_access("LOGIN", f"failed ip={ip}")
        return jsonify({"ok": False, "error": _api_t("wrong_password")}), 401


@app.route("/api/check-auth")
def api_check_auth():
    """检查登录状态、权限模式。"""
    need_auth = bool(access_password or USERS)
    if not need_auth:
        return jsonify({"need_auth": False, "logged_in": True, "read_only": READ_ONLY, "role": "admin"})
    role = _get_current_role()
    logged_in = role is not None
    # 综合判断只读：全局只读 或 用户角色为 readonly
    effective_readonly = READ_ONLY or (role == "readonly")
    return jsonify({"need_auth": True, "logged_in": logged_in,
                    "read_only": effective_readonly, "role": role or ""})


@app.route("/api/logout", methods=["POST"])
def api_logout():
    """
    登出接口。清除当前用户的 session 并移除 cookie。

    多用户模式下会从 user_sessions 中删除对应 token。
    """
    token = request.cookies.get("auth_token", "")
    if token and USERS:
        with _state_lock:
            user_sessions.pop(token, None)
    log_access("LOGOUT", "")
    resp = make_response(jsonify({"ok": True}))
    resp.set_cookie("auth_token", "", expires=0, httponly=True, samesite="Lax")
    return resp


# ════════════════════════════════════════════════════════════
# API 路由 — 文件浏览
# ════════════════════════════════════════════════════════════

@app.route("/api/drives")
@require_auth
def api_drives():
    """获取所有可用磁盘。"""
    drives = get_drives()
    return jsonify([{"path": d, "name": d} for d in drives])


@app.route("/api/list")
@require_auth
def api_list():
    """
    列出目录内容，支持排序和筛选。

    查询参数:
        path       (str): 目录路径
        sort       (str): 排序字段 - name / size / ctime / mtime
        order      (str): 排序方向 - asc / desc
        filter_type(str): 按文件类别筛选，如 image/video/text/markdown/pdf/archive/office 等
        filter_ext (str): 按扩展名筛选，如 .py / .md / .json（多个用逗号分隔）
    """
    if not _resolve_template_vars():
        abort(503)
    raw = request.args.get("path", "")
    sort_by = request.args.get("sort", "name")
    sort_order = request.args.get("order", "asc")
    filter_type = request.args.get("filter_type", "").strip().lower()
    filter_ext = request.args.get("filter_ext", "").strip().lower()

    if not raw:
        log_access("BROWSE", "drives")
        return api_drives()

    real = safe_path(raw)
    if real is None:
        return jsonify({"error": _api_t("path_not_found")}), 404
    if os.path.isfile(real):
        return jsonify({"error": _api_t("is_file_not_dir")}), 400

    log_access("BROWSE", real)

    # 解析扩展名筛选列表（支持 ".py,.js" 或 "py,js" 格式）
    ext_filters = []
    if filter_ext:
        for e in filter_ext.split(","):
            e = e.strip()
            if e and not e.startswith("."):
                e = "." + e
            if e:
                ext_filters.append(e)

    items = []
    try:
        entries = os.scandir(real)
    except PermissionError:
        return jsonify({"error": _api_t("no_permission_dir")}), 403
    except Exception as e:
        app.logger.error("Unhandled error: %s", e)
        return jsonify({"error": _api_t("internal_error")}), 500

    for entry in entries:
        if entry.name in _SYSTEM_HIDDEN_FILES:
            continue
        try:
            stat = entry.stat(follow_symlinks=False)
            is_dir = entry.is_dir(follow_symlinks=False)
            ftype = 'folder' if is_dir else get_file_type(entry.name)
            ext = Path(entry.name).suffix.lower()

            # 筛选逻辑（文件夹始终保留，仅筛选文件）
            if not is_dir:
                if filter_type and ftype != filter_type:
                    continue
                if ext_filters and ext not in ext_filters:
                    continue

            items.append({
                "name": entry.name,
                "path": entry.path.replace("\\", "/"),
                "is_dir": is_dir,
                "size": 0 if is_dir else stat.st_size,
                "size_str": "--" if is_dir else format_size(stat.st_size),
                "modified": format_time(stat.st_mtime),
                "created": format_time(stat.st_ctime),
                "mtime": stat.st_mtime,
                "ctime": stat.st_ctime,
                "type": ftype,
                "ext": ext,
                "icon": get_file_icon(ftype, is_dir),
            })
        except (PermissionError, OSError):
            continue

    # 排序: 文件夹始终在前（不受排序方向影响），文件夹/文件各自按字段排序
    reverse = sort_order == "desc"
    if sort_by == "size":
        items.sort(key=lambda x: x["size"], reverse=reverse)
    elif sort_by == "mtime":
        items.sort(key=lambda x: x["mtime"], reverse=reverse)
    elif sort_by == "ctime":
        items.sort(key=lambda x: x["ctime"], reverse=reverse)
    else:
        items.sort(key=lambda x: x["name"].lower(), reverse=reverse)
    # 稳定排序：文件夹始终在前（利用 Python sort 的稳定性，不受 reverse 影响）
    items.sort(key=lambda x: not x["is_dir"])

    parent = os.path.dirname(real).replace("\\", "/")
    if parent == real.replace("\\", "/"):
        parent = ""

    return jsonify({"path": real.replace("\\", "/"), "parent": parent, "items": items})


# ════════════════════════════════════════════════════════════
# API 路由 — 搜索
# ════════════════════════════════════════════════════════════

@app.route("/api/search")
@require_auth
def api_search():
    """按文件名搜索（递归子目录）。支持 regex=1 正则模式。"""
    if not _resolve_template_vars():
        abort(503)
    raw = request.args.get("path", "")
    keyword = request.args.get("q", "").strip()
    use_regex = request.args.get("regex", "0") == "1"
    if not keyword:
        return jsonify({"results": []})

    # 编译匹配函数
    if use_regex:
        if len(keyword) > 200:
            return jsonify({"error": _api_t("regex_too_long")}), 400
        # 检测可能导致灾难性回溯的嵌套量词模式（如 (a+)+, (?:a+)+, (a{2,})*）
        if _is_dangerous_regex(keyword):
            return jsonify({"error": _api_t("regex_nested")}), 400
        try:
            pattern = re.compile(keyword, re.IGNORECASE)
            match_fn = lambda name: bool(pattern.search(name))
        except re.error as e:
            return jsonify({"error": f"{_api_t('regex_error')}: {e}"}), 400
    else:
        kw_lower = keyword.lower()
        match_fn = lambda name: kw_lower in name.lower()

    search_root = safe_path(raw) if raw else None
    if search_root is None:
        drives = get_drives()
        search_root = drives[0] if drives else ("C:\\" if sys.platform == 'win32' else "/")

    log_access("SEARCH", f"keyword={keyword} root={search_root}")

    results = []

    def search_dir(dir_path, depth=0):
        if depth > SEARCH_MAX_DEPTH or len(results) >= SEARCH_MAX_RESULTS:
            return
        try:
            for entry in os.scandir(dir_path):
                if len(results) >= SEARCH_MAX_RESULTS:
                    return
                try:
                    if match_fn(entry.name):
                        is_dir = entry.is_dir(follow_symlinks=False)
                        stat = entry.stat(follow_symlinks=False)
                        ftype = 'folder' if is_dir else get_file_type(entry.name)
                        results.append({
                            "name": entry.name,
                            "path": entry.path.replace("\\", "/"),
                            "is_dir": is_dir,
                            "size_str": "--" if is_dir else format_size(stat.st_size),
                            "modified": format_time(stat.st_mtime),
                            "type": ftype,
                            "icon": get_file_icon(ftype, is_dir),
                            "dir": os.path.dirname(entry.path).replace("\\", "/"),
                        })
                    if entry.is_dir(follow_symlinks=False):
                        search_dir(entry.path, depth + 1)
                except (PermissionError, OSError):
                    continue
        except (PermissionError, OSError):
            return

    search_dir(search_root)
    return jsonify({"results": results, "total": len(results)})


@app.route("/api/search-content")
@require_auth
def api_search_content():
    """
    文件内容搜索 — 搜索文本文件内部的文字。

    参数:
        path (str): 搜索起始目录
        q (str): 搜索关键词
    返回:
        匹配结果列表，每条包含文件路径、匹配行号和行内容
    """
    raw = request.args.get("path", "")
    keyword = request.args.get("q", "").strip()
    use_regex = request.args.get("regex", "0") == "1"
    if not keyword:
        return jsonify({"results": []})

    # 编译匹配函数
    if use_regex:
        if len(keyword) > 200:
            return jsonify({"error": _api_t("regex_too_long")}), 400
        if _is_dangerous_regex(keyword):
            return jsonify({"error": _api_t("regex_nested")}), 400
        try:
            pattern = re.compile(keyword, re.IGNORECASE)
            line_match_fn = lambda line: bool(pattern.search(line))
        except re.error as e:
            return jsonify({"error": f"{_api_t('regex_error')}: {e}"}), 400
    else:
        kw_lower = keyword.lower()
        line_match_fn = lambda line: kw_lower in line.lower()

    search_root = safe_path(raw) if raw else None
    if search_root is None:
        drives = get_drives()
        search_root = drives[0] if drives else ("C:\\" if sys.platform == 'win32' else "/")

    log_access("CONTENT_SEARCH", f"keyword={keyword} root={search_root}")

    results = []
    files_scanned = 0

    def search_dir(dir_path, depth=0):
        nonlocal files_scanned
        if depth > SEARCH_MAX_DEPTH or len(results) >= CONTENT_SEARCH_MAX_RESULTS:
            return
        try:
            for entry in os.scandir(dir_path):
                if len(results) >= CONTENT_SEARCH_MAX_RESULTS:
                    return
                try:
                    if entry.is_dir(follow_symlinks=False):
                        search_dir(entry.path, depth + 1)
                    elif entry.is_file(follow_symlinks=False):
                        ftype = get_file_type(entry.name)
                        if ftype not in ('text', 'markdown'):
                            continue
                        stat = entry.stat(follow_symlinks=False)
                        if stat.st_size > CONTENT_SEARCH_MAX_SIZE:
                            continue
                        files_scanned += 1
                        if files_scanned > CONTENT_SEARCH_MAX_FILES:
                            return
                        # 读取并搜索文件内容
                        content = read_text_file(entry.path, CONTENT_SEARCH_MAX_SIZE)
                        if content is None:
                            continue
                        lines = content.split('\n')
                        matches = []
                        for i, line in enumerate(lines, 1):
                            if line_match_fn(line):
                                # 截取匹配行（最多 200 字符）
                                matches.append({
                                    "line": i,
                                    "text": line.strip()[:200],
                                })
                                if len(matches) >= 3:
                                    break  # 每个文件最多 3 条匹配
                        if matches:
                            results.append({
                                "name": entry.name,
                                "path": entry.path.replace("\\", "/"),
                                "dir": os.path.dirname(entry.path).replace("\\", "/"),
                                "size_str": format_size(stat.st_size),
                                "type": ftype,
                                "icon": get_file_icon(ftype),
                                "matches": matches,
                            })
                except (PermissionError, OSError):
                    continue
        except (PermissionError, OSError):
            return

    search_dir(search_root)
    return jsonify({
        "results": results,
        "total": len(results),
        "files_scanned": files_scanned,
    })


# ════════════════════════════════════════════════════════════
# API 路由 — 文件预览与下载
# ════════════════════════════════════════════════════════════

@app.route("/api/file")
@require_auth
def api_file():
    """获取文本/Markdown 文件内容用于预览。"""
    raw = request.args.get("path", "")
    real = safe_path(raw)
    if real is None or not os.path.isfile(real):
        return jsonify({"error": _api_t("file_not_found")}), 404

    ftype = get_file_type(real)
    if ftype not in ('text', 'markdown'):
        return jsonify({"error": _api_t("not_text_file")}), 400

    size = os.path.getsize(real)
    try:
        content = read_text_file(real, max_size=0)
    except MemoryError:
        return jsonify({"error": _api_t("memory_error"), "size": format_size(size)}), 400
    if content is None:
        return jsonify({"error": _api_t("decode_error")}), 400

    log_access("PREVIEW", real)
    ext = Path(real).suffix.lower().lstrip('.')
    return jsonify({"content": content, "ext": ext, "size": format_size(size)})


@app.route("/api/save-file", methods=["POST"])
@require_auth
@require_writable
def api_save_file():
    """
    保存（编辑后的）文本文件内容。

    请求体: {"path": "C:/path/to/file.txt", "content": "新内容..."}

    安全限制:
        - 仅允许保存 text 和 markdown 类型的文件
        - 文件必须已经存在（不能用此接口创建新文件）
        - 保存前自动创建 .bak 备份文件

    跨平台说明:
        使用 Python 标准 open() 写入，Windows 和 macOS/Linux 均兼容。
        自动检测原始文件编码并以相同编码写回，检测失败时回退到 UTF-8。
    """
    data = request.get_json(silent=True) or {}
    raw = data.get("path", "")
    content = data.get("content", "")

    real = safe_path(raw)
    if real is None or not os.path.isfile(real):
        return jsonify({"error": _api_t("file_not_found")}), 404

    if _is_sealed_path(real):
        return jsonify({"error": _api_t("file_protected_edit")}), 403

    # 仅允许编辑文本/Markdown 类型文件
    ftype = get_file_type(real)
    if ftype not in ('text', 'markdown'):
        return jsonify({"error": _api_t("unsupported_edit")}), 400

    try:
        # 保存前创建备份文件（.bak），防止误操作丢失数据
        backup_path = real + ".bak"
        try:
            shutil.copy2(real, backup_path)
        except Exception:
            pass  # 备份失败不阻止保存

        # 检测原始文件编码，保留原编码写回；检测失败时回退到 UTF-8
        original_enc = detect_encoding(real) or 'utf-8'
        with open(real, 'w', encoding=original_enc, newline='') as f:
            f.write(content)

        log_access("EDIT", real)
        new_size = os.path.getsize(real)
        return jsonify({
            "ok": True,
            "size": format_size(new_size),
            "backup": os.path.basename(backup_path),
        })
    except PermissionError:
        return jsonify({"error": _api_t("no_permission_write")}), 403
    except Exception as e:
        app.logger.error("Unhandled error: %s", e)
        return jsonify({"error": _api_t("internal_error")}), 500


@app.route("/api/download")
@require_auth
def api_download():
    """下载单个文件。"""
    if not _init_render_engine():
        abort(503)
    raw = request.args.get("path", "")
    real = safe_path(raw)
    if real is None or not os.path.isfile(real):
        abort(404)
    log_access("DOWNLOAD", real)
    return send_file(real, as_attachment=True)


@app.route("/api/raw")
@require_auth
def api_raw():
    """返回文件原始内容（用于预览图片/视频/音频/PDF）。"""
    raw = request.args.get("path", "")
    real = safe_path(raw)
    # exe 模式下，若 DATA_DIR 无此文件，尝试从内嵌资源 BUNDLE_DIR 提供（如打赏收款码图片）
    if (real is None or not os.path.isfile(real)) and getattr(sys, 'frozen', False):
        bundle_path = os.path.join(BUNDLE_DIR, raw.replace('/', os.sep).lstrip(os.sep))
        bundle_path = os.path.normpath(bundle_path)
        if os.path.isfile(bundle_path) and (bundle_path == BUNDLE_DIR or bundle_path.startswith(BUNDLE_DIR + os.sep)):
            real = bundle_path
    if real is None or not os.path.isfile(real):
        abort(404)
    log_access("RAW", real)
    mime = mimetypes.guess_type(real)[0] or "application/octet-stream"
    return send_file(real, mimetype=mime)


@app.route("/api/info")
@require_auth
def api_info():
    """获取文件或目录的详细信息。"""
    raw = request.args.get("path", "")
    real = safe_path(raw)
    if real is None:
        return jsonify({"error": _api_t("path_not_exist")}), 404
    try:
        stat = os.stat(real)
    except PermissionError:
        return jsonify({"error": _api_t("no_permission")}), 403
    except OSError:
        return jsonify({"error": _api_t("path_not_found")}), 404

    is_dir = os.path.isdir(real)
    name = os.path.basename(real)
    ftype = 'folder' if is_dir else get_file_type(name)
    return jsonify({
        "name": name,
        "path": real.replace("\\", "/"),
        "is_dir": is_dir,
        "size": "--" if is_dir else format_size(stat.st_size),
        "type": ftype,
        "ext": Path(real).suffix.lower() if not is_dir else "",
        "created": format_time(stat.st_ctime),
        "modified": format_time(stat.st_mtime),
        "accessed": format_time(stat.st_atime),
    })


@app.route("/api/batch-download", methods=["POST"])
@require_auth
def api_batch_download():
    """
    批量下载 — 将多个文件打包为 zip 并下载。

    请求体: {"paths": ["C:/path/file1.txt", "C:/path/file2.jpg"]}
    """
    data = request.get_json(silent=True) or {}
    paths = data.get("paths", [])
    if not paths:
        return jsonify({"error": _api_t("no_files_selected")}), 400

    log_access("BATCH_DOWNLOAD", f"{len(paths)} files")

    # 创建 zip 文件（小于 100MB 在内存中，超过自动溢出到磁盘临时文件）
    mem_zip = tempfile.SpooledTemporaryFile(max_size=100 * 1024 * 1024)
    try:
        with zipfile.ZipFile(mem_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
            for raw_path in paths:
                real = safe_path(raw_path)
                if real and os.path.isfile(real):
                    arcname = os.path.basename(real)
                    existing = [n for n in zf.namelist()]
                    if arcname in existing:
                        base, ext = os.path.splitext(arcname)
                        i = 1
                        while f"{base}_{i}{ext}" in existing:
                            i += 1
                        arcname = f"{base}_{i}{ext}"
                    try:
                        zf.write(real, arcname)
                    except (PermissionError, OSError):
                        continue
    except MemoryError:
        return jsonify({"error": _api_t("memory_pack_error")}), 400

    mem_zip.seek(0)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return send_file(
        mem_zip,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f"files_{timestamp}.zip",
    )


# ════════════════════════════════════════════════════════════
# API 路由 — 文件操作（上传/新建/删除/重命名）
# ════════════════════════════════════════════════════════════

@app.route("/api/upload", methods=["POST"])
@require_auth
@require_writable
def api_upload():
    """
    文件上传 — 将文件保存到指定目录。支持目录上传（通过 relativePaths 保留目录结构）。

    表单字段:
        path (str): 目标目录路径
        files (file): 一个或多个上传文件
        relativePaths (str, optional): JSON 数组，每个元素为对应文件的相对路径（目录上传时使用）
        conflict (str, optional): 冲突处理方式 "overwrite"|"rename"|"skip"，默认 "rename"
    """
    target_dir = request.form.get("path", "")
    real_dir = safe_path(target_dir)
    if real_dir is None or not os.path.isdir(real_dir):
        return jsonify({"error": _api_t("target_dir_not_found")}), 404

    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": _api_t("no_upload_files")}), 400

    # 冲突处理方式，默认 rename（保持向后兼容）
    conflict = request.form.get("conflict", "rename")

    # 解析可选的相对路径列表（目录上传时由前端传入）
    raw_rel = request.form.get("relativePaths", "")
    rel_paths = None
    if raw_rel:
        try:
            rel_paths = json.loads(raw_rel)
        except (json.JSONDecodeError, TypeError):
            rel_paths = None

    saved = []
    skipped = []
    errors = []
    created_dirs = set()
    real_dir_abs = os.path.realpath(real_dir)

    for idx, f in enumerate(files):
        if not f.filename:
            continue

        # 判断是否有有效的相对路径（目录上传模式）
        rel = None
        if rel_paths and idx < len(rel_paths) and rel_paths[idx]:
            rel = rel_paths[idx].replace("\\", "/")

        if rel:
            # ── 目录上传模式：保留相对路径结构 ──
            parts = rel.split("/")
            # 安全检查第一道：拒绝含 .. 的路径段，以及 ~ 单独作为路径段（Unix home 目录展开）
            if ".." in parts or "~" in parts:
                errors.append(f"{rel}: path traversal rejected")
                continue
            dest = os.path.normpath(os.path.join(real_dir, rel))
            # 安全检查第二道：realpath 验证不逃逸目标目录
            real_dest = os.path.realpath(dest)
            if sys.platform == "win32":
                real_dest_cmp = real_dest.lower()
                real_dir_cmp = real_dir_abs.lower()
            else:
                real_dest_cmp = real_dest
                real_dir_cmp = real_dir_abs
            dir_prefix = real_dir_cmp.rstrip(os.sep) + os.sep
            if not real_dest_cmp.startswith(dir_prefix):
                errors.append(f"{rel}: {_api_t('upload_path_traversal')}")
                continue
            # 确保父目录存在
            parent = os.path.dirname(dest)
            if parent not in created_dirs and not os.path.isdir(parent):
                os.makedirs(parent, exist_ok=True)
                created_dirs.add(parent)
            filename = rel
            # 目录上传模式下也应用冲突策略
            if os.path.exists(dest):
                if conflict == "skip":
                    skipped.append(filename)
                    continue
                elif conflict == "rename":
                    base, ext = os.path.splitext(dest)
                    i = 1
                    while os.path.exists(f"{base}_{i}{ext}"):
                        i += 1
                    dest = f"{base}_{i}{ext}"
                    filename = os.path.relpath(dest, real_dir).replace("\\", "/")
                # "overwrite": 直接覆盖（保存时自然覆盖）
        else:
            # ── 普通文件上传模式 ──
            filename = os.path.basename(f.filename)
            dest = os.path.join(real_dir, filename)
            if os.path.exists(dest):
                if conflict == "skip":
                    skipped.append(filename)
                    continue
                elif conflict == "rename":
                    base, ext = os.path.splitext(filename)
                    i = 1
                    while os.path.exists(os.path.join(real_dir, f"{base}_{i}{ext}")):
                        i += 1
                    filename = f"{base}_{i}{ext}"
                    dest = os.path.join(real_dir, filename)
                # "overwrite": 直接覆盖（保存时自然覆盖）

        try:
            f.save(dest)
            saved.append(filename)
            log_access("UPLOAD", dest)
        except Exception as e:
            errors.append(f"{f.filename}: {str(e)}")

    return jsonify({"saved": saved, "skipped": skipped, "errors": errors, "count": len(saved)})


# ════════════════════════════════════════════════════════════
# 分片断点续传 API
# ════════════════════════════════════════════════════════════

def _cleanup_expired_uploads():
    """清理过期的上传会话及其临时文件（惰性调用）。"""
    now = time.time()
    expired = []
    with _upload_sessions_lock:
        for uid, info in _upload_sessions.items():
            if now - info["created"] > _UPLOAD_SESSION_EXPIRY:
                expired.append(uid)
        for uid in expired:
            info = _upload_sessions.pop(uid, None)
            if info:
                tmp = info.get("tmp_path", "")
                if tmp and os.path.exists(tmp):
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass


@app.route("/api/upload-init", methods=["POST"])
@require_auth
@require_writable
def api_upload_init():
    """
    初始化分片上传会话。

    请求体 (JSON):
        path (str):         目标目录路径
        filename (str):     文件名
        size (int):         文件总大小（字节）
        relativePath (str): 相对路径（目录上传时使用）
        conflict (str):     冲突策略 "overwrite"|"rename"|"skip"
    """
    data = request.get_json(force=True)
    target_dir = data.get("path", "")
    filename = data.get("filename", "")
    total_size = data.get("size", 0)
    relative_path = data.get("relativePath", "")
    conflict = data.get("conflict", "rename")

    real_dir = safe_path(target_dir)
    if real_dir is None or not os.path.isdir(real_dir):
        return jsonify({"error": _api_t("target_dir_not_found")}), 404
    if not filename:
        return jsonify({"error": _api_t("filename_empty")}), 400

    real_dir_abs = os.path.realpath(real_dir)

    # 确定目标路径（与 api_upload 逻辑一致）
    if relative_path:
        rel = relative_path.replace("\\", "/")
        parts = rel.split("/")
        if ".." in parts or "~" in parts:
            return jsonify({"error": _api_t("upload_path_traversal")}), 400
        dest = os.path.normpath(os.path.join(real_dir, rel))
        real_dest = os.path.realpath(dest)
        if sys.platform == "win32":
            dir_prefix = real_dir_abs.lower().rstrip(os.sep) + os.sep
            if not real_dest.lower().startswith(dir_prefix):
                return jsonify({"error": _api_t("upload_path_traversal")}), 400
        else:
            dir_prefix = real_dir_abs.rstrip(os.sep) + os.sep
            if not real_dest.startswith(dir_prefix):
                return jsonify({"error": _api_t("upload_path_traversal")}), 400
        parent = os.path.dirname(dest)
        if not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        dest_filename = rel
    else:
        dest = os.path.join(real_dir, os.path.basename(filename))
        dest_filename = os.path.basename(filename)

    # 冲突处理
    if os.path.exists(dest):
        if conflict == "skip":
            return jsonify({"skipped": True, "dest_filename": dest_filename})
        elif conflict == "rename":
            base, ext = os.path.splitext(dest)
            i = 1
            while os.path.exists(f"{base}_{i}{ext}"):
                i += 1
            dest = f"{base}_{i}{ext}"
            if relative_path:
                dest_filename = os.path.relpath(dest, real_dir).replace("\\", "/")
            else:
                dest_filename = os.path.basename(dest)
        # "overwrite": 不改名，完成时覆盖

    # 检查是否存在可恢复的同目标会话
    with _upload_sessions_lock:
        for uid, info in list(_upload_sessions.items()):
            if info["dest"] == dest and info["total_size"] == total_size:
                uploaded = 0
                tmp = info.get("tmp_path", "")
                if tmp and os.path.exists(tmp):
                    uploaded = os.path.getsize(tmp)
                info["uploaded_bytes"] = uploaded
                return jsonify({
                    "upload_id": uid,
                    "chunk_size": _CHUNK_SIZE,
                    "uploaded_bytes": uploaded,
                    "dest_filename": info["dest_filename"],
                    "resumed": True,
                })

    # 惰性清理过期会话
    _cleanup_expired_uploads()

    # 创建临时目录和文件
    os.makedirs(_UPLOAD_TMP_DIR, exist_ok=True)
    upload_id = secrets.token_urlsafe(16)
    tmp_path = os.path.join(_UPLOAD_TMP_DIR, upload_id + ".part")
    with open(tmp_path, "wb"):
        pass  # 创建空文件

    with _upload_sessions_lock:
        _upload_sessions[upload_id] = {
            "tmp_path": tmp_path,
            "dest": dest,
            "dest_filename": dest_filename,
            "total_size": total_size,
            "uploaded_bytes": 0,
            "created": time.time(),
            "target_dir": real_dir,
        }

    return jsonify({
        "upload_id": upload_id,
        "chunk_size": _CHUNK_SIZE,
        "uploaded_bytes": 0,
        "dest_filename": dest_filename,
    })


@app.route("/api/upload-chunk", methods=["POST"])
@require_auth
@require_writable
def api_upload_chunk():
    """
    上传单个分片。

    表单字段:
        upload_id (str): 上传会话 ID
        offset (int):    本分片在文件中的字节偏移
        chunk (file):    分片二进制数据
    """
    upload_id = request.form.get("upload_id", "")
    offset = int(request.form.get("offset", 0))

    with _upload_sessions_lock:
        session = _upload_sessions.get(upload_id)
    if not session:
        return jsonify({"error": _api_t("upload_session_expired")}), 404

    chunk = request.files.get("chunk")
    if not chunk:
        return jsonify({"error": _api_t("upload_no_chunk")}), 400

    tmp_path = session["tmp_path"]
    chunk_data = chunk.read()

    try:
        with open(tmp_path, "r+b" if os.path.getsize(tmp_path) > 0 else "wb") as f:
            f.seek(offset)
            f.write(chunk_data)
        new_offset = offset + len(chunk_data)
        with _upload_sessions_lock:
            if upload_id in _upload_sessions:
                _upload_sessions[upload_id]["uploaded_bytes"] = new_offset
        return jsonify({"uploaded_bytes": new_offset})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/upload-complete", methods=["POST"])
@require_auth
@require_writable
def api_upload_complete():
    """
    完成分片上传 — 将临时文件移动到最终位置。

    请求体 (JSON):
        upload_id (str): 上传会话 ID
    """
    data = request.get_json(force=True)
    upload_id = data.get("upload_id", "")

    with _upload_sessions_lock:
        session = _upload_sessions.pop(upload_id, None)
    if not session:
        return jsonify({"error": _api_t("upload_session_expired")}), 404

    tmp_path = session["tmp_path"]
    dest = session["dest"]

    if not os.path.exists(tmp_path):
        return jsonify({"error": _api_t("upload_temp_missing")}), 500

    try:
        parent = os.path.dirname(dest)
        if not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)
        if os.path.exists(dest):
            os.remove(dest)
        shutil.move(tmp_path, dest)
        log_access("UPLOAD", dest)
        return jsonify({
            "ok": True,
            "filename": session["dest_filename"],
            "size": session["total_size"],
        })
    except Exception as e:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except OSError:
                pass
        return jsonify({"error": str(e)}), 500


@app.route("/api/upload-cancel", methods=["POST"])
@require_auth
def api_upload_cancel():
    """
    取消分片上传 — 删除临时文件和会话。

    请求体 (JSON):
        upload_id (str): 上传会话 ID
    """
    data = request.get_json(force=True)
    upload_id = data.get("upload_id", "")

    with _upload_sessions_lock:
        session = _upload_sessions.pop(upload_id, None)
    if not session:
        return jsonify({"error": _api_t("upload_session_expired")}), 404

    tmp_path = session["tmp_path"]
    if os.path.exists(tmp_path):
        try:
            os.remove(tmp_path)
        except OSError:
            pass
    return jsonify({"ok": True})


@app.route("/api/upload-status", methods=["GET"])
@require_auth
def api_upload_status():
    """
    查询分片上传进度。

    查询参数:
        upload_id (str): 上传会话 ID
    """
    upload_id = request.args.get("upload_id", "")

    with _upload_sessions_lock:
        session = _upload_sessions.get(upload_id)
    if not session:
        return jsonify({"error": _api_t("upload_session_expired")}), 404

    uploaded = 0
    tmp = session.get("tmp_path", "")
    if tmp and os.path.exists(tmp):
        uploaded = os.path.getsize(tmp)

    return jsonify({
        "upload_id": upload_id,
        "uploaded_bytes": uploaded,
        "total_size": session["total_size"],
        "filename": session["dest_filename"],
    })


# ════════════════════════════════════════════════════════════
# 文件操作流式进度辅助函数
# ════════════════════════════════════════════════════════════

_OP_CHUNK = 1024 * 1024          # 复制分块大小 1MB
_OP_PROGRESS_INTERVAL = 0.15     # 进度更新最小间隔（秒）


def _stream_response(gen):
    """将生成器包装为 NDJSON 流式响应（每行一个 JSON 对象）。"""
    def generate():
        try:
            for update in gen:
                yield json.dumps(update, ensure_ascii=False) + "\n"
        except Exception as e:
            yield json.dumps({"error": str(e)}) + "\n"
    return Response(stream_with_context(generate()), mimetype='text/x-ndjson',
                    headers={'X-Accel-Buffering': 'no', 'Cache-Control': 'no-cache'})


def _copy_file_progress(src, dest):
    """分块复制单个文件，yield 字节级进度。"""
    total = os.path.getsize(src)
    copied = 0
    last_t = 0
    with open(src, 'rb') as fs, open(dest, 'wb') as fd:
        while True:
            buf = fs.read(_OP_CHUNK)
            if not buf:
                break
            fd.write(buf)
            copied += len(buf)
            now = time.time()
            if now - last_t >= _OP_PROGRESS_INTERVAL or copied == total:
                yield {"p": copied, "t": total}
                last_t = now
    shutil.copystat(src, dest)


def _copytree_progress(src, dest):
    """递归复制目录树，yield 字节级进度。"""
    total_size = 0
    file_list = []
    for root, _dirs, files in os.walk(src):
        for fname in files:
            fp = os.path.join(root, fname)
            try:
                sz = os.path.getsize(fp)
                total_size += sz
                file_list.append((fp, sz))
            except OSError:
                pass
    copied_total = 0
    for fp, sz in file_list:
        rel = os.path.relpath(fp, src)
        dest_fp = os.path.join(dest, rel)
        os.makedirs(os.path.dirname(dest_fp), exist_ok=True)
        for prog in _copy_file_progress(fp, dest_fp):
            yield {"p": copied_total + prog["p"], "t": total_size, "f": rel}
        copied_total += sz
    for root, dirs, _ in os.walk(src):
        for d in dirs:
            src_d = os.path.join(root, d)
            dest_d = os.path.join(dest, os.path.relpath(src_d, src))
            if os.path.isdir(dest_d):
                try:
                    shutil.copystat(src_d, dest_d)
                except OSError:
                    pass
    try:
        shutil.copystat(src, dest)
    except OSError:
        pass


def _rmtree_progress(path):
    """递归删除目录树，yield 文件级进度。"""
    file_list = []
    for root, _dirs, files in os.walk(path):
        for f in files:
            file_list.append(os.path.join(root, f))
    total = len(file_list)
    deleted = 0
    last_t = 0
    for fp in file_list:
        try:
            os.remove(fp)
        except OSError:
            pass
        deleted += 1
        now = time.time()
        if now - last_t >= _OP_PROGRESS_INTERVAL or deleted == total:
            yield {"p": deleted, "t": total, "f": os.path.basename(fp)}
            last_t = now
    for root, dirs, _ in os.walk(path, topdown=False):
        for d in dirs:
            try:
                os.rmdir(os.path.join(root, d))
            except OSError:
                pass
    try:
        os.rmdir(path)
    except OSError:
        pass


@app.route("/api/mkdir", methods=["POST"])
@require_auth
@require_writable
def api_mkdir():
    """
    新建文件夹。

    请求体: {"path": "C:/Users/xxx", "name": "新文件夹"}
    """
    data = request.get_json(silent=True) or {}
    parent = data.get("path", "")
    name = data.get("name", "").strip()

    if not name:
        return jsonify({"error": _api_t("folder_name_empty")}), 400

    # 文件名安全检查：不允许包含路径分隔符和特殊字符
    invalid_chars = set('\\/:*?"<>|')
    if any(c in invalid_chars for c in name):
        return jsonify({"error": _api_t("folder_name_invalid")}), 400

    real_parent = safe_path(parent)
    if real_parent is None or not os.path.isdir(real_parent):
        return jsonify({"error": _api_t("parent_not_found")}), 404

    new_dir = os.path.join(real_parent, name)
    if os.path.exists(new_dir):
        return jsonify({"error": _api_t("name_exists")}), 409

    try:
        os.makedirs(new_dir)
        log_access("MKDIR", new_dir)
        return jsonify({"ok": True, "path": new_dir.replace("\\", "/")})
    except Exception as e:
        app.logger.error("Unhandled error: %s", e)
        return jsonify({"error": _api_t("internal_error")}), 500


@app.route("/api/mkfile", methods=["POST"])
@require_auth
@require_writable
def api_mkfile():
    """
    新建文件。

    请求体: {"path": "父目录路径", "name": "文件名.扩展名", "content": "初始内容（可选）"}
    """
    data = request.get_json(silent=True) or {}
    parent = data.get("path", "")
    name = data.get("name", "").strip()
    content = data.get("content", "")

    if not name:
        return jsonify({"error": _api_t("filename_empty")}), 400

    # 文件名安全检查
    invalid_chars = set('\\/:*?"<>|')
    if any(c in invalid_chars for c in name):
        return jsonify({"error": _api_t("filename_invalid")}), 400

    real_parent = safe_path(parent)
    if real_parent is None or not os.path.isdir(real_parent):
        return jsonify({"error": _api_t("parent_not_found")}), 404

    new_file = os.path.join(real_parent, name)
    if os.path.exists(new_file):
        return jsonify({"error": _api_t("filename_exists")}), 409

    try:
        with open(new_file, 'w', encoding='utf-8', newline='') as f:
            f.write(content)
        log_access("MKFILE", new_file)
        return jsonify({"ok": True, "path": new_file.replace("\\", "/")})
    except PermissionError:
        return jsonify({"error": _api_t("no_permission_create")}), 403
    except Exception as e:
        app.logger.error("Unhandled error: %s", e)
        return jsonify({"error": _api_t("internal_error")}), 500


@app.route("/api/delete", methods=["POST"])
@require_auth
@require_writable
def api_delete():
    """
    删除文件或文件夹。

    请求体: {"path": "C:/path/to/file", "recursive": false}
    recursive=true 时递归删除非空文件夹（危险操作，需前端二次确认）。
    """
    data = request.get_json(silent=True) or {}
    raw = data.get("path", "")
    recursive = data.get("recursive", False)
    real = safe_path(raw)
    if real is None:
        return jsonify({"error": _api_t("path_not_found")}), 404

    if _is_sealed_path(real):
        return jsonify({"error": _api_t("file_protected_del")}), 403

    # 检查是否为受保护的系统目录
    if os.path.normpath(real).lower() in _PROTECTED_PATHS:
        return jsonify({"error": _api_t("protected_sys_dir")}), 403

    use_stream = data.get("stream", False)
    try:
        if os.path.isfile(real):
            os.remove(real)
            log_access("DELETE", real)
            return jsonify({"ok": True})
        elif os.path.isdir(real):
            if os.listdir(real) and not recursive:
                return jsonify({"error": _api_t("dir_not_empty"), "not_empty": True}), 400
            if recursive:
                if use_stream:
                    def _gen():
                        yield from _rmtree_progress(real)
                        log_access("DELETE_RECURSIVE", real)
                        yield {"ok": True}
                    return _stream_response(_gen())
                else:
                    shutil.rmtree(real)
            else:
                os.rmdir(real)
            log_access("DELETE" + ("_RECURSIVE" if recursive else ""), real)
            return jsonify({"ok": True})
        else:
            return jsonify({"error": _api_t("unknown_type")}), 400
    except PermissionError:
        return jsonify({"error": _api_t("no_permission_del")}), 403
    except Exception as e:
        app.logger.error("Unhandled error: %s", e)
        return jsonify({"error": _api_t("internal_error")}), 500


@app.route("/api/rename", methods=["POST"])
@require_auth
@require_writable
def api_rename():
    """
    重命名文件或文件夹。

    请求体: {"path": "C:/old_name.txt", "name": "new_name.txt"}
    """
    data = request.get_json(silent=True) or {}
    raw = data.get("path", "")
    new_name = data.get("name", "").strip()

    if not new_name:
        return jsonify({"error": _api_t("new_name_empty")}), 400

    invalid_chars = set('\\/:*?"<>|')
    if any(c in invalid_chars for c in new_name):
        return jsonify({"error": _api_t("name_invalid")}), 400

    real = safe_path(raw)
    if real is None:
        return jsonify({"error": _api_t("path_not_found")}), 404

    if _is_sealed_path(real):
        return jsonify({"error": _api_t("file_protected_rename")}), 403

    parent = os.path.dirname(real)
    new_path = os.path.join(parent, new_name)

    if os.path.exists(new_path):
        return jsonify({"error": _api_t("name_exists_rename")}), 409

    try:
        os.rename(real, new_path)
        log_access("RENAME", f"{real} -> {new_path}")
        return jsonify({"ok": True, "path": new_path.replace("\\", "/")})
    except PermissionError:
        return jsonify({"error": _api_t("no_permission_rename")}), 403
    except Exception as e:
        app.logger.error("Unhandled error: %s", e)
        return jsonify({"error": _api_t("internal_error")}), 500


# ════════════════════════════════════════════════════════════
# API 路由 — 剪贴板
# ════════════════════════════════════════════════════════════

@app.route("/api/clipboard", methods=["GET"])
@require_auth
def api_clipboard_get():
    """获取当前用户的剪贴板内容（多用户模式下按用户隔离）。"""
    key = _clipboard_key()
    with _state_lock:
        data = clipboard_data.get(key, {"text": "", "updated": ""})
        return jsonify(dict(data))


@app.route("/api/clipboard", methods=["POST"])
@require_auth
@require_writable
def api_clipboard_set():
    """
    设置当前用户的剪贴板内容（多用户模式下按用户隔离）。

    请求体: {"text": "要共享的文本"}
    """
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    key = _clipboard_key()
    with _state_lock:
        clipboard_data[key] = {
            "text": text,
            "updated": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
    log_access("CLIPBOARD", f"set {len(text)} chars user={key}")
    return jsonify({"ok": True})


# ════════════════════════════════════════════════════════════
# API 路由 — 书签
# ════════════════════════════════════════════════════════════

@app.route("/api/bookmarks", methods=["GET"])
@require_auth
def api_bookmarks_get():
    """获取当前用户的书签（多用户模式下按用户隔离）。"""
    username = _get_current_username() if USERS else None
    return jsonify(load_bookmarks(username))


@app.route("/api/bookmarks", methods=["POST"])
@require_auth
@require_writable
def api_bookmarks_add():
    """
    添加书签（多用户模式下按用户隔离）。

    请求体: {"path": "C:/path", "name": "自定义名称（可选）"}
    """
    data = request.get_json(silent=True) or {}
    path = data.get("path", "").strip()
    name = data.get("name", "").strip() or os.path.basename(path) or path

    if not path:
        return jsonify({"error": _api_t("path_empty")}), 400

    username = _get_current_username() if USERS else None
    bookmarks = load_bookmarks(username)
    # 检查是否已存在
    for b in bookmarks:
        if b["path"] == path:
            return jsonify({"error": _api_t("already_bookmarked")}), 409

    bookmarks.append({
        "path": path,
        "name": name,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    save_bookmarks(bookmarks, username)
    log_access("BOOKMARK_ADD", path)
    return jsonify({"ok": True})


@app.route("/api/bookmarks", methods=["DELETE"])
@require_auth
@require_writable
def api_bookmarks_delete():
    """
    删除书签（多用户模式下按用户隔离）。

    请求体: {"path": "C:/path"}
    """
    data = request.get_json(silent=True) or {}
    path = data.get("path", "")
    username = _get_current_username() if USERS else None
    bookmarks = load_bookmarks(username)
    bookmarks = [b for b in bookmarks if b["path"] != path]
    save_bookmarks(bookmarks, username)
    log_access("BOOKMARK_DEL", path)
    return jsonify({"ok": True})


# ════════════════════════════════════════════════════════════
# API 路由 — 文件复制 / 移动
# ════════════════════════════════════════════════════════════

@app.route("/api/copy", methods=["POST"])
@require_auth
@require_writable
def api_copy():
    """
    复制文件或文件夹到目标目录。

    请求体: {"src": "源路径", "dest_dir": "目标目录", "conflict": "overwrite|rename|skip"}
    conflict 参数:
      - 不传: 同名冲突时返回 409 + {"conflict": true, "name": "..."} 由前端弹窗让用户选择
      - "overwrite": 覆盖已有文件/文件夹
      - "rename": 自动重命名（保留两者）
      - "skip": 跳过，不执行复制
    """
    data = request.get_json(silent=True) or {}
    src_raw = data.get("src", "")
    dest_dir_raw = data.get("dest_dir", "")
    conflict = data.get("conflict", "")

    src = safe_path(src_raw)
    if src is None:
        return jsonify({"error": _api_t("src_not_found")}), 404

    dest_dir = safe_path(dest_dir_raw)
    if dest_dir is None or not os.path.isdir(dest_dir):
        return jsonify({"error": _api_t("dest_dir_not_found")}), 404

    name = os.path.basename(src)
    dest = os.path.join(dest_dir, name)

    # 同名冲突处理
    if os.path.exists(dest):
        # 源和目标是同一路径（复制到自身所在目录）：覆盖无意义，只允许 rename 和 skip
        src_real_path = os.path.realpath(src)
        dest_real_path = os.path.realpath(dest)
        if src_real_path == dest_real_path:
            if conflict == "rename":
                i = 1
                if os.path.isfile(src):
                    base, ext = os.path.splitext(name)
                    while os.path.exists(os.path.join(dest_dir, f"{base}_copy{i}{ext}")):
                        i += 1
                    name = f"{base}_copy{i}{ext}"
                else:
                    while os.path.exists(os.path.join(dest_dir, f"{name}_copy{i}")):
                        i += 1
                    name = f"{name}_copy{i}"
                dest = os.path.join(dest_dir, name)
            elif conflict == "skip" or conflict == "overwrite":
                return jsonify({"ok": True, "skipped": True, "dest": dest.replace("\\", "/")})
            else:
                return jsonify({"error": _api_t("dest_name_conflict"), "conflict": True, "name": name}), 409
        elif conflict == "skip":
            return jsonify({"ok": True, "skipped": True, "dest": dest.replace("\\", "/")})
        elif conflict == "overwrite":
            try:
                if os.path.isdir(dest):
                    shutil.rmtree(dest)
                else:
                    os.remove(dest)
            except PermissionError:
                return jsonify({"error": _api_t("no_permission")}), 403
        elif conflict == "rename":
            i = 1
            if os.path.isfile(src):
                base, ext = os.path.splitext(name)
                while os.path.exists(os.path.join(dest_dir, f"{base}_copy{i}{ext}")):
                    i += 1
                name = f"{base}_copy{i}{ext}"
            else:
                while os.path.exists(os.path.join(dest_dir, f"{name}_copy{i}")):
                    i += 1
                name = f"{name}_copy{i}"
            dest = os.path.join(dest_dir, name)
        else:
            # 未指定冲突处理方式：返回 409 让前端弹窗
            return jsonify({"error": _api_t("dest_name_conflict"), "conflict": True, "name": name}), 409

    use_stream = data.get("stream", False)
    try:
        if use_stream:
            def _gen():
                if os.path.isfile(src):
                    yield from _copy_file_progress(src, dest)
                else:
                    yield from _copytree_progress(src, dest)
                log_access("COPY", f"{src} -> {dest}")
                yield {"ok": True, "dest": dest.replace("\\", "/")}
            return _stream_response(_gen())
        else:
            if os.path.isfile(src):
                shutil.copy2(src, dest)
            else:
                shutil.copytree(src, dest)
            log_access("COPY", f"{src} -> {dest}")
            return jsonify({"ok": True, "dest": dest.replace("\\", "/")})
    except PermissionError:
        return jsonify({"error": _api_t("no_permission")}), 403
    except Exception as e:
        app.logger.error("Unhandled error: %s", e)
        return jsonify({"error": _api_t("internal_error")}), 500


@app.route("/api/move", methods=["POST"])
@require_auth
@require_writable
def api_move():
    """
    移动文件或文件夹到目标目录。

    请求体: {"src": "源路径", "dest_dir": "目标目录", "conflict": "overwrite|rename|skip"}
    conflict 参数:
      - 不传: 同名冲突时返回 409 + {"conflict": true, "name": "..."} 由前端弹窗让用户选择
      - "overwrite": 覆盖已有文件/文件夹
      - "rename": 自动重命名（保留两者）
      - "skip": 跳过，不执行移动
    """
    data = request.get_json(silent=True) or {}
    src_raw = data.get("src", "")
    dest_dir_raw = data.get("dest_dir", "")
    conflict = data.get("conflict", "")

    src = safe_path(src_raw)
    if src is None:
        return jsonify({"error": _api_t("src_not_found")}), 404

    if _is_sealed_path(src):
        return jsonify({"error": _api_t("file_protected_move")}), 403

    dest_dir = safe_path(dest_dir_raw)
    if dest_dir is None or not os.path.isdir(dest_dir):
        return jsonify({"error": _api_t("dest_dir_not_found")}), 404

    # 防止将目录移动到自身或其子目录中
    src_real = os.path.realpath(src)
    dest_real = os.path.realpath(dest_dir)
    src_prefix = src_real.rstrip(os.sep) + os.sep
    if os.path.isdir(src_real) and (dest_real == src_real or dest_real.startswith(src_prefix)):
        return jsonify({"error": _api_t("move_into_self")}), 400

    name = os.path.basename(src)
    dest = os.path.join(dest_dir, name)

    # 同名冲突处理
    if os.path.exists(dest):
        # 源和目标是同一路径（移动到自身所在目录）：无法覆盖自己，只允许 rename 和 skip
        src_real_path = os.path.realpath(src)
        dest_real_path = os.path.realpath(dest)
        if src_real_path == dest_real_path:
            if conflict == "rename":
                i = 1
                if os.path.isfile(src):
                    base, ext = os.path.splitext(name)
                    while os.path.exists(os.path.join(dest_dir, f"{base}_copy{i}{ext}")):
                        i += 1
                    name = f"{base}_copy{i}{ext}"
                else:
                    while os.path.exists(os.path.join(dest_dir, f"{name}_copy{i}")):
                        i += 1
                    name = f"{name}_copy{i}"
                dest = os.path.join(dest_dir, name)
            elif conflict == "skip" or conflict == "overwrite":
                return jsonify({"ok": True, "skipped": True, "dest": dest.replace("\\", "/")})
            else:
                return jsonify({"error": _api_t("dest_name_conflict"), "conflict": True, "name": name}), 409
        elif conflict == "skip":
            return jsonify({"ok": True, "skipped": True, "dest": dest.replace("\\", "/")})
        elif conflict == "overwrite":
            try:
                if os.path.isdir(dest):
                    shutil.rmtree(dest)
                else:
                    os.remove(dest)
            except PermissionError:
                return jsonify({"error": _api_t("no_permission")}), 403
        elif conflict == "rename":
            i = 1
            if os.path.isfile(src):
                base, ext = os.path.splitext(name)
                while os.path.exists(os.path.join(dest_dir, f"{base}_copy{i}{ext}")):
                    i += 1
                name = f"{base}_copy{i}{ext}"
            else:
                while os.path.exists(os.path.join(dest_dir, f"{name}_copy{i}")):
                    i += 1
                name = f"{name}_copy{i}"
            dest = os.path.join(dest_dir, name)
        else:
            # 未指定冲突处理方式：返回 409 让前端弹窗
            return jsonify({"error": _api_t("dest_name_conflict"), "conflict": True, "name": name}), 409

    use_stream = data.get("stream", False)
    try:
        if use_stream:
            # 流式模式：先尝试 rename（同分区瞬时），失败则分块复制+删源
            def _gen():
                try:
                    os.rename(src, dest)
                    log_access("MOVE", f"{src} -> {dest}")
                    yield {"ok": True, "dest": dest.replace("\\", "/")}
                    return
                except OSError:
                    pass
                if os.path.isfile(src):
                    yield from _copy_file_progress(src, dest)
                    os.remove(src)
                else:
                    yield from _copytree_progress(src, dest)
                    shutil.rmtree(src)
                log_access("MOVE", f"{src} -> {dest}")
                yield {"ok": True, "dest": dest.replace("\\", "/")}
            return _stream_response(_gen())
        else:
            shutil.move(src, dest)
            log_access("MOVE", f"{src} -> {dest}")
            return jsonify({"ok": True, "dest": dest.replace("\\", "/")})
    except PermissionError:
        return jsonify({"error": _api_t("no_permission")}), 403
    except Exception as e:
        app.logger.error("Unhandled error: %s", e)
        return jsonify({"error": _api_t("internal_error")}), 500


# ════════════════════════════════════════════════════════════
# API 路由 — 文件夹整体下载
# ════════════════════════════════════════════════════════════

@app.route("/api/download-folder")
@require_auth
def api_download_folder():
    """
    将整个文件夹递归打包为 zip 并下载。

    参数: path — 文件夹路径
    """
    raw = request.args.get("path", "")
    real = safe_path(raw)
    if real is None or not os.path.isdir(real):
        abort(404)

    folder_name = os.path.basename(real)
    log_access("DOWNLOAD_FOLDER", real)

    mem_zip = tempfile.SpooledTemporaryFile(max_size=100 * 1024 * 1024)
    try:
        with zipfile.ZipFile(mem_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
            for root, dirs, files in os.walk(real):
                for file in files:
                    file_path = os.path.join(root, file)
                    try:
                        # 保留文件夹内部相对路径结构，统一使用正斜杠
                        arcname = os.path.join(
                            folder_name,
                            os.path.relpath(file_path, real)
                        ).replace("\\", "/")
                        zf.write(file_path, arcname)
                    except (PermissionError, OSError):
                        continue
    except MemoryError:
        return jsonify({"error": _api_t("memory_pack_error")}), 400

    mem_zip.seek(0)
    return send_file(
        mem_zip,
        mimetype='application/zip',
        as_attachment=True,
        download_name=f"{folder_name}.zip",
    )


# ════════════════════════════════════════════════════════════
# API 路由 — ZIP 内容预览 / 在线解压
# ════════════════════════════════════════════════════════════

@app.route("/api/zip-list")
@require_auth
def api_zip_list():
    """
    列出 ZIP 文件内部的文件结构。

    参数: path — zip 文件路径
    返回: 文件列表，每条包含 name、size、is_dir
    """
    raw = request.args.get("path", "")
    real = safe_path(raw)
    if real is None or not os.path.isfile(real):
        return jsonify({"error": _api_t("file_not_found")}), 404
    log_access("ZIP_LIST", real)

    try:
        items = []
        with zipfile.ZipFile(real, 'r') as zf:
            for info in zf.infolist():
                items.append({
                    "name": info.filename,
                    "size": format_size(info.file_size),
                    "is_dir": info.filename.endswith('/'),
                    "compressed": format_size(info.compress_size),
                })
        return jsonify({"items": items, "count": len(items)})
    except zipfile.BadZipFile:
        return jsonify({"error": _api_t("invalid_zip")}), 400
    except Exception as e:
        app.logger.error("Unhandled error: %s", e)
        return jsonify({"error": _api_t("internal_error")}), 500


@app.route("/api/extract", methods=["POST"])
@require_auth
@require_writable
def api_extract():
    """
    将 ZIP 文件解压到指定目录。

    请求体: {"path": "zip路径", "dest_dir": "解压目标目录", "conflict": "overwrite|rename|skip"}
    conflict 参数:
      - 不传: 有冲突时返回 409 + {"conflict": true, "files": [...]} 由前端弹窗让用户选择
      - "overwrite": 覆盖已有文件（默认 extractall 行为）
      - "rename": 冲突文件自动重命名
      - "skip": 跳过已存在的文件
    """
    data = request.get_json(silent=True) or {}
    raw = data.get("path", "")
    dest_dir_raw = data.get("dest_dir", "")
    conflict = data.get("conflict", "")

    real = safe_path(raw)
    if real is None or not os.path.isfile(real):
        return jsonify({"error": _api_t("zip_not_found")}), 404

    dest_dir = safe_path(dest_dir_raw)
    if dest_dir is None or not os.path.isdir(dest_dir):
        return jsonify({"error": _api_t("target_dir_not_found")}), 404

    try:
        dest_abs = os.path.realpath(dest_dir)
        dest_prefix = dest_abs.rstrip(os.sep) + os.sep
        with zipfile.ZipFile(real, 'r') as zf:
            # 安全检查：防止 Zip Slip
            for member in zf.infolist():
                member_path = os.path.realpath(os.path.join(dest_abs, member.filename))
                if not member_path.startswith(dest_prefix) and member_path != dest_abs:
                    return jsonify({"error": f"{_api_t('zip_illegal_path')}: {member.filename}"}), 400

            # 检测冲突文件
            conflicts = []
            for member in zf.infolist():
                if member.is_dir():
                    continue
                member_path = os.path.join(dest_abs, member.filename)
                if os.path.exists(member_path):
                    conflicts.append(member.filename)

            if conflicts and not conflict:
                # 有冲突且未指定处理方式：返回 409 让前端弹窗
                return jsonify({
                    "error": _api_t("dest_name_conflict"),
                    "conflict": True,
                    "files": conflicts[:20],
                    "total": len(conflicts),
                }), 409

            use_stream = data.get("stream", False)
            members = [m for m in zf.infolist() if not m.is_dir()]
            total_members = len(members)

            if use_stream:
                # 注意：生成器在 with zf 块退出后才被消费，因此需要
                # 在 _gen 内部自行打开 zip 文件，否则 zf 已关闭。
                _zip_path = real
                _dest_abs = dest_abs
                _conflict = conflict
                _total = total_members
                def _gen():
                    with zipfile.ZipFile(_zip_path, 'r') as zf2:
                        extracted = 0
                        last_t = 0
                        for member in zf2.infolist():
                            member_path = os.path.join(_dest_abs, member.filename)
                            if member.is_dir():
                                os.makedirs(member_path, exist_ok=True)
                                continue
                            parent = os.path.dirname(member_path)
                            if not os.path.isdir(parent):
                                os.makedirs(parent, exist_ok=True)
                            if os.path.exists(member_path):
                                if _conflict == "skip":
                                    extracted += 1
                                    continue
                                elif _conflict == "rename":
                                    base, ext = os.path.splitext(member_path)
                                    i = 1
                                    while os.path.exists(f"{base}_{i}{ext}"):
                                        i += 1
                                    member_path = f"{base}_{i}{ext}"
                                # overwrite: 直接覆盖
                            with zf2.open(member) as src_f, open(member_path, 'wb') as dst_f:
                                shutil.copyfileobj(src_f, dst_f)
                            extracted += 1
                            now = time.time()
                            if now - last_t >= _OP_PROGRESS_INTERVAL or extracted == _total:
                                yield {"p": extracted, "t": _total, "f": member.filename}
                                last_t = now
                    log_access("EXTRACT", f"{_zip_path} -> {dest_dir}")
                    yield {"ok": True}
                return _stream_response(_gen())
            else:
                if conflict == "overwrite" or not conflicts:
                    zf.extractall(dest_dir)
                else:
                    for member in zf.infolist():
                        member_path = os.path.join(dest_abs, member.filename)
                        if member.is_dir():
                            os.makedirs(member_path, exist_ok=True)
                            continue
                        parent = os.path.dirname(member_path)
                        if not os.path.isdir(parent):
                            os.makedirs(parent, exist_ok=True)
                        if os.path.exists(member_path):
                            if conflict == "skip":
                                continue
                            elif conflict == "rename":
                                base, ext = os.path.splitext(member_path)
                                i = 1
                                while os.path.exists(f"{base}_{i}{ext}"):
                                    i += 1
                                member_path = f"{base}_{i}{ext}"
                        with zf.open(member) as src_f, open(member_path, 'wb') as dst_f:
                            shutil.copyfileobj(src_f, dst_f)

        log_access("EXTRACT", f"{real} -> {dest_dir}")
        return jsonify({"ok": True})
    except zipfile.BadZipFile:
        return jsonify({"error": _api_t("invalid_zip")}), 400
    except PermissionError:
        return jsonify({"error": _api_t("no_permission_extract")}), 403
    except Exception as e:
        app.logger.error("Unhandled error: %s", e)
        return jsonify({"error": _api_t("internal_error")}), 500


# ════════════════════════════════════════════════════════════
# API 路由 — 临时分享链接
# ════════════════════════════════════════════════════════════

@app.route("/api/share", methods=["POST"])
@require_auth
def api_share_create():
    """
    为单个文件生成临时公开下载链接。

    请求体: {"path": "文件路径", "expires": 3600}（expires 单位秒，默认 1 小时）
    返回: {"token": "...", "url": "/share/<token>", "expires_in": 3600}
    """
    data = request.get_json(silent=True) or {}
    raw = data.get("path", "")
    try:
        expires = int(data.get("expires", 3600))
    except (ValueError, TypeError):
        expires = 3600
    expires = max(60, min(expires, 86400))  # 限制 1 分钟～24 小时

    real = safe_path(raw)
    if real is None or not os.path.isfile(real):
        return jsonify({"error": _api_t("file_not_found")}), 404

    # 清理过期 token（每次创建时顺带清理，避免内存持续增长）
    now_ts = datetime.now().timestamp()
    token = secrets.token_urlsafe(16)
    with _state_lock:
        expired_keys = [k for k, v in share_tokens.items() if now_ts > v["expires_at"]]
        for k in expired_keys:
            share_tokens.pop(k, None)
        share_tokens[token] = {
            "path": real,
            "expires_at": now_ts + expires,
        }
    log_access("SHARE_CREATE", real)
    return jsonify({
        "ok": True,
        "token": token,
        "url": f"/share/{token}",
        "expires_in": expires,
    })


@app.route("/share/<token>")
def share_download(token):
    """
    通过临时 token 下载文件，无需登录。
    token 过期后返回 410 Gone。
    """
    with _state_lock:
        info = share_tokens.get(token)
        if info is None:
            abort(404)
        if datetime.now().timestamp() > info["expires_at"]:
            share_tokens.pop(token, None)
            abort(410)  # Gone

    real = info["path"]
    if not os.path.isfile(real):
        abort(404)

    log_access("SHARE_DOWNLOAD", real)
    return send_file(real, as_attachment=True)


# ════════════════════════════════════════════════════════════
# API 路由 — 文件夹大小
# ════════════════════════════════════════════════════════════

@app.route("/api/folder-size")
@require_auth
def api_folder_size():
    """
    计算文件夹的总大小（递归）。

    参数: path — 文件夹路径
    """
    raw = request.args.get("path", "")
    real = safe_path(raw)
    if real is None or not os.path.isdir(real):
        return jsonify({"error": _api_t("dir_not_found")}), 404
    log_access("FOLDER_SIZE", real)

    total = 0
    start = time.time()
    try:
        for dirpath, _, filenames in os.walk(real):
            if time.time() - start > 30:  # 超时保护 30 秒
                return jsonify({"size_str": _api_t("calc_timeout"), "timeout": True})
            for f in filenames:
                try:
                    total += os.path.getsize(os.path.join(dirpath, f))
                except OSError:
                    continue
    except (PermissionError, OSError):
        pass

    return jsonify({"size": total, "size_str": format_size(total)})


# ════════════════════════════════════════════════════════════
# API 路由 — HTML 模板
# ════════════════════════════════════════════════════════════

HTML_TEMPLATE = r"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, user-scalable=no">
<title>File Browser</title>
<script src="/static/vendor/marked.min.js"></script>
<script src="/static/vendor/highlight.min.js"></script>
<script src="/static/vendor/mermaid.min.js"></script>
<link rel="stylesheet" href="/static/vendor/github-dark.min.css">
<script src="/static/vendor/qrcode.min.js"></script>
<script src="/static/vendor/purify.min.js"></script>
<script src="/static/vendor/mammoth.browser.min.js"></script>
<script src="/static/vendor/xlsx.full.min.js"></script>
<style>
:root {
    --bg:#0f1117;--card:#1a1d27;--border:#2a2d3a;--text:#e4e4e7;--text2:#9ca3af;
    --accent:#6366f1;--accent2:#818cf8;--hover:#22253a;--danger:#ef4444;--success:#22c55e;
    --warn:#f59e0b;--radius:12px;
}
/* ── 亮色主题 ── */
:root[data-theme="light"] {
    --bg:#f5f5f7;--card:#ffffff;--border:#e0e0e5;--text:#1a1a2e;--text2:#6b7280;
    --accent:#6366f1;--accent2:#818cf8;--hover:#eef0ff;--danger:#ef4444;--success:#22c55e;
    --warn:#f59e0b;
}
:root[data-theme="light"] .md-body{color:#374151}
:root[data-theme="light"] .nav{background:rgba(245,245,247,.85)}
/* ── 拖拽上传遮罩 ── */
#dropOverlay{display:none;position:fixed;inset:0;background:rgba(99,102,241,.15);border:3px dashed var(--accent);z-index:800;border-radius:16px;pointer-events:none;align-items:center;justify-content:center;font-size:24px;color:var(--accent)}
#dropOverlay.show{display:flex}
/* ── 上传进度条 ── */
.upload-progress{width:100%;margin-top:8px}
.upload-progress-bar{width:100%;height:6px;background:var(--border);border-radius:3px;overflow:hidden}
.upload-progress-fill{height:100%;background:var(--accent);border-radius:3px;transition:width .2s;width:0%}
.upload-progress-text{font-size:12px;color:var(--text2);margin-top:4px;text-align:center}
#dragUploadToast{display:none;position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:var(--card);border:1px solid var(--border);border-radius:var(--radius);padding:12px 20px;z-index:900;min-width:280px;box-shadow:0 4px 12px rgba(0,0,0,0.3)}
#dragUploadToast .upload-progress-text{margin-top:2px}
/* ── 上传队列 ── */
.uq-wrap{max-height:60vh;display:flex;flex-direction:column}
.uq-list{flex:1;overflow-y:auto;max-height:40vh;margin-top:8px;border:1px solid var(--border);border-radius:var(--radius);padding:4px}
.uq-item{display:flex;align-items:center;gap:6px;padding:4px 8px;font-size:13px;border-radius:4px;flex-wrap:wrap}
.uq-item.uq-active{background:rgba(99,102,241,0.1)}
.uq-item.uq-done{color:var(--text2)}.uq-item.uq-fail{color:#ef4444}
.uq-item.uq-skip{color:var(--text2);opacity:0.6}
.uq-icon{width:16px;text-align:center;flex-shrink:0}
.uq-name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;min-width:0}
.uq-size{flex-shrink:0;color:var(--text2);font-size:12px}
.uq-fbar{width:100%;height:3px;background:var(--border);border-radius:2px;overflow:hidden}
.uq-ffill{height:100%;background:var(--accent);border-radius:2px;transition:width .15s}
/* ── 网格视图 ── */
#content.grid-view{display:grid;grid-template-columns:repeat(auto-fill,minmax(140px,1fr));gap:12px;padding:8px 0}
#content.grid-view .file-item{flex-direction:column;align-items:center;padding:14px 8px;gap:6px;text-align:center;border-radius:12px;height:auto}
#content.grid-view .file-icon{font-size:36px;width:auto;height:auto}
#content.grid-view .file-thumb{width:80px;height:80px;object-fit:cover;border-radius:8px;border:1px solid var(--border)}
#content.grid-view .file-info{width:100%;overflow:hidden}
#content.grid-view .file-name{font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:120px}
#content.grid-view .file-meta,.file-ext-badge{display:none}
#content.grid-view .file-actions{margin-top:4px;justify-content:center}
/* ── 分享链接输入框 ── */
.share-url{width:100%;padding:8px 10px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);color:var(--text);font-size:13px;margin-top:8px;cursor:text}
/* ── 作者页脚 ── */
.app-footer{text-align:center;padding:16px;color:var(--text2);font-size:12px;border-top:1px solid var(--border);margin-top:20px}
.app-footer a{color:var(--accent);text-decoration:none}
.app-footer a:hover{text-decoration:underline}
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",system-ui,sans-serif;background:var(--bg);color:var(--text);min-height:100vh;overflow-x:hidden}

/* ── Login ── */
.login-page{display:flex;flex-direction:column;align-items:center;justify-content:center;min-height:100vh;padding:20px}
.login-card{background:var(--card);border:1px solid var(--border);border-radius:16px;padding:32px;width:100%;max-width:360px;text-align:center}
.login-card h2{margin-bottom:8px;font-size:22px}
.login-card .sub{color:var(--text2);font-size:13px;margin-bottom:24px}
.login-input{width:100%;padding:12px;background:var(--bg);border:1px solid var(--border);border-radius:var(--radius);color:var(--text);font-size:18px;text-align:center;letter-spacing:4px;outline:none;margin-bottom:12px}
.login-input:focus{border-color:var(--accent)}
.login-btn{width:100%;padding:12px;background:var(--accent);color:#fff;border:none;border-radius:var(--radius);font-size:16px;cursor:pointer;transition:background .15s}
.login-btn:hover{background:var(--accent2)}
.login-error{color:var(--danger);font-size:13px;margin-top:8px;min-height:20px}
.qr-box{margin:20px 0;display:flex;justify-content:center}
.qr-box canvas,#qrcode img{border-radius:8px}

/* ── Header ── */
.header{position:sticky;top:0;z-index:100;background:rgba(15,17,23,0.92);backdrop-filter:blur(20px);border-bottom:1px solid var(--border);padding:10px 16px}
:root[data-theme="light"] .header{background:rgba(245,245,247,0.92)}
.header-top{display:flex;align-items:center;gap:10px;margin-bottom:8px}
.logo{font-size:18px;font-weight:700;flex:1}.logo span{color:var(--accent2)}

/* ── Toolbar ── */
.toolbar{display:flex;gap:6px;flex-wrap:wrap;margin-bottom:8px}
.tool-btn{background:var(--card);border:1px solid var(--border);color:var(--text2);padding:6px 10px;border-radius:8px;cursor:pointer;font-size:12px;display:flex;align-items:center;gap:4px;transition:all .15s;white-space:nowrap}
.tool-btn:hover{border-color:var(--accent);color:var(--text)}
.tool-btn.active{background:var(--accent);color:#fff;border-color:var(--accent)}
.tool-btn.danger{color:var(--danger)}
.tool-btn.danger:hover{background:var(--danger);color:#fff;border-color:var(--danger)}

/* ── Breadcrumb ── */
.breadcrumb{display:flex;align-items:center;gap:4px;font-size:13px;overflow-x:auto;white-space:nowrap;padding-bottom:4px;scrollbar-width:none}
.breadcrumb::-webkit-scrollbar{display:none}
.breadcrumb a{color:var(--accent2);text-decoration:none;padding:3px 8px;border-radius:6px;transition:background .15s}
.breadcrumb a:hover{background:var(--hover)}
.breadcrumb .sep{color:var(--text2);user-select:none}

/* ── Search ── */
.search-box{display:flex;align-items:center;gap:6px;margin-bottom:8px}
.search-box .search-inner{position:relative;flex:1;min-width:0}
.search-box input{width:100%;padding:10px 32px 10px 38px;background:var(--card);border:1px solid var(--border);border-radius:var(--radius);color:var(--text);font-size:15px;outline:none;transition:border .2s}
.search-box input:focus{border-color:var(--accent)}
.search-box input::placeholder{color:var(--text2)}
.search-icon{position:absolute;left:12px;top:0;bottom:0;display:flex;align-items:center;color:var(--text2);font-size:15px;pointer-events:none;line-height:1}
.search-clear{position:absolute;right:8px;top:0;bottom:0;display:none;align-items:center;background:none;border:none;color:var(--text2);font-size:18px;cursor:pointer;padding:0 4px}
.search-clear.show{display:flex}
.regex-btn{padding:6px 10px;border-radius:var(--radius);border:1px solid var(--border);background:var(--card);color:var(--text2);font-family:monospace;font-size:13px;cursor:pointer;white-space:nowrap;transition:all .15s;flex-shrink:0}
.regex-btn:hover{border-color:var(--accent);color:var(--text)}
.regex-btn.active{color:var(--accent);border-color:var(--accent)}
.search-mode{display:flex;gap:4px;margin-bottom:6px}
.search-mode button{background:var(--card);border:1px solid var(--border);color:var(--text2);padding:3px 8px;border-radius:6px;cursor:pointer;font-size:11px}
.search-mode button.active{background:var(--accent);color:#fff;border-color:var(--accent)}

/* ── Sort ── */
.sort-bar{display:flex;gap:6px;padding:2px 0;font-size:12px;flex-wrap:wrap;align-items:center}
.sort-btn{background:var(--card);border:1px solid var(--border);color:var(--text2);padding:4px 10px;border-radius:6px;cursor:pointer;font-size:12px;transition:all .15s}
.sort-btn.active{background:var(--accent);color:#fff;border-color:var(--accent)}
/* 筛选栏 */
.filter-bar{display:flex;gap:6px;padding:2px 0;font-size:12px;flex-wrap:wrap;align-items:center}
.filter-select{background:var(--card);border:1px solid var(--border);color:var(--text2);padding:4px 8px;border-radius:6px;font-size:12px;outline:none;cursor:pointer;max-width:120px}
.filter-select:focus{border-color:var(--accent)}
.filter-input{background:var(--card);border:1px solid var(--border);color:var(--text);padding:4px 8px;border-radius:6px;font-size:12px;outline:none;width:110px}
.filter-input:focus{border-color:var(--accent)}
.filter-input::placeholder{color:var(--text2)}
.filter-label{color:var(--text2);font-size:11px;white-space:nowrap}
.filter-clear{background:none;border:none;color:var(--text2);font-size:14px;cursor:pointer;padding:2px 4px}
.filter-clear:hover{color:var(--danger)}

/* ── File list ── */
.file-list{padding:8px 16px 100px}
.file-item{display:flex;align-items:center;gap:10px;padding:10px;margin-bottom:2px;border-radius:var(--radius);cursor:pointer;transition:background .15s;border:1px solid transparent}
.file-item:hover{background:var(--hover)}
.file-item:active{background:var(--card);border-color:var(--border)}
.file-item.selected{background:rgba(99,102,241,0.15);border-color:var(--accent)}
.file-check{width:20px;height:20px;border:2px solid var(--border);border-radius:4px;flex-shrink:0;display:none;cursor:pointer;position:relative}
.file-check.checked{background:var(--accent);border-color:var(--accent)}
.file-check.checked::after{content:"";position:absolute;left:5px;top:2px;width:5px;height:9px;border:solid #fff;border-width:0 2px 2px 0;transform:rotate(45deg)}
.select-mode .file-check{display:block}
.file-icon{font-size:26px;flex-shrink:0;width:32px;text-align:center}
.file-info{flex:1;min-width:0}
.file-name{font-size:14px;font-weight:500;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.file-meta{font-size:12px;color:var(--text2);margin-top:2px;display:flex;gap:12px}
.file-dir{font-size:11px;color:var(--text2);margin-top:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.file-actions{display:flex;gap:2px;flex-shrink:0}
.file-act{width:32px;height:32px;display:flex;align-items:center;justify-content:center;border-radius:6px;border:none;background:none;color:var(--text2);font-size:14px;cursor:pointer;transition:all .15s}
.file-act:hover{background:var(--border);color:var(--text)}

/* ── Content search results ── */
.match-lines{margin-top:4px;font-size:11px;color:var(--text2)}
.match-line{padding:2px 0;font-family:monospace}
.match-line .ln{color:var(--accent2);margin-right:6px}

/* ── Status ── */
.status{padding:6px 16px;font-size:12px;color:var(--text2);display:flex;align-items:center;gap:6px}
.status-dot{width:6px;height:6px;border-radius:50%;background:var(--success);display:inline-block}

/* ── Loading & Empty ── */
.loading{display:none;justify-content:center;padding:40px}
.loading.show{display:flex}
.spinner{width:32px;height:32px;border:3px solid var(--border);border-top-color:var(--accent);border-radius:50%;animation:spin .8s linear infinite}
@keyframes spin{to{transform:rotate(360deg)}}
.empty{text-align:center;padding:60px 20px;color:var(--text2)}
.empty-icon{font-size:48px;margin-bottom:12px}

/* ── Modal (shared) ── */
.modal-overlay{display:none;position:fixed;inset:0;background:rgba(0,0,0,0.8);z-index:200;justify-content:center;align-items:center}
.modal-overlay.show{display:flex}
.modal{background:var(--card);border-radius:16px;width:95vw;max-width:900px;max-height:90vh;display:flex;flex-direction:column;overflow:hidden;border:1px solid var(--border)}
.modal-sm{max-width:420px}
.modal-header{display:flex;align-items:center;justify-content:space-between;padding:14px 16px;border-bottom:1px solid var(--border);flex-shrink:0}
.modal-title{font-size:14px;font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1}
.modal-actions{display:flex;gap:8px}
.modal-btn{padding:6px 14px;border-radius:8px;border:none;font-size:13px;cursor:pointer;transition:all .15s}
.modal-btn-primary{background:var(--accent);color:#fff}
.modal-btn-primary:hover{background:var(--accent2)}
.modal-btn-danger{background:var(--danger);color:#fff}
.modal-btn-close{background:var(--border);color:var(--text)}
.modal-btn-close:hover{background:#3a3d4a}

.modal-body{flex:1;overflow:auto;padding:0;display:flex;justify-content:center;align-items:flex-start}
.modal-body img{max-width:100%;max-height:80vh;object-fit:contain}
.modal-body video,.modal-body audio{max-width:100%;outline:none}
.modal-body video{max-height:75vh;background:#000}
.modal-body audio{margin:40px 20px;width:calc(100% - 40px)}
.modal-body:has(iframe){overflow:hidden;display:block}
.modal-body iframe{width:100%;height:calc(90vh - 60px);border:none}
.modal-body pre{width:100%;padding:16px;margin:0;font-family:"Cascadia Code","Fira Code","JetBrains Mono",monospace;font-size:13px;line-height:1.6;white-space:pre-wrap;word-break:break-all;overflow:auto;background:#12141c;color:#d4d4d8;tab-size:4}
.modal-form{padding:20px;width:100%;display:flex;flex-direction:column;gap:12px}
.modal-form label{font-size:13px;color:var(--text2)}
.modal-form input,.modal-form textarea{width:100%;padding:10px 12px;background:var(--bg);border:1px solid var(--border);border-radius:8px;color:var(--text);font-size:14px;outline:none}
.modal-form input:focus,.modal-form textarea:focus{border-color:var(--accent)}
.modal-form textarea{min-height:120px;resize:vertical;font-family:inherit}
.modal-form .hint{font-size:12px;color:var(--text2)}

/* ── File detail bar ── */
.file-detail{padding:10px 16px;border-top:1px solid var(--border);font-size:12px;color:var(--text2);display:flex;flex-wrap:wrap;gap:8px 20px;flex-shrink:0}
.file-detail-item{display:flex;gap:4px}
.file-detail-label{opacity:.7}

/* ── Markdown ── */
.md-body{padding:20px 24px;width:100%;line-height:1.7;color:#d4d4d8;font-size:15px;overflow-wrap:break-word}
.md-body h1{font-size:1.8em;margin:24px 0 12px;padding-bottom:6px;border-bottom:1px solid var(--border)}
.md-body h2{font-size:1.5em;margin:20px 0 10px;padding-bottom:4px;border-bottom:1px solid var(--border)}
.md-body h3{font-size:1.25em;margin:16px 0 8px}
.md-body h4,.md-body h5,.md-body h6{font-size:1.1em;margin:14px 0 6px}
.md-body p{margin:10px 0}
.md-body a{color:var(--accent2);text-decoration:none}
.md-body a:hover{text-decoration:underline}
.md-body img{max-width:100%;border-radius:8px;margin:8px 0}
.md-body blockquote{border-left:3px solid var(--accent);padding:4px 16px;margin:12px 0;color:var(--text2);background:rgba(99,102,241,.06);border-radius:0 8px 8px 0}
.md-body pre{background:#12141c;border-radius:8px;padding:14px;overflow-x:auto;margin:12px 0;border:1px solid var(--border)}
.md-body code{font-family:"Cascadia Code","Fira Code","JetBrains Mono",monospace;font-size:.9em}
.md-body :not(pre)>code{background:rgba(99,102,241,.15);padding:2px 6px;border-radius:4px;color:var(--accent2)}
.md-body ul,.md-body ol{padding-left:24px;margin:8px 0}
.md-body li{margin:4px 0}
.md-body li input[type="checkbox"]{margin-right:6px}
.md-body table{width:100%;border-collapse:collapse;margin:12px 0;font-size:14px}
.md-body th,.md-body td{border:1px solid var(--border);padding:8px 12px;text-align:left}
.md-body th{background:rgba(99,102,241,.1);font-weight:600}
.md-body tr:nth-child(even){background:rgba(255,255,255,.02)}
.md-body hr{border:none;border-top:1px solid var(--border);margin:20px 0}
/* Mermaid 渲染结果容器 */
.mermaid-rendered{margin:16px 0;text-align:center;overflow-x:auto}
.mermaid-rendered svg{max-width:100%;height:auto}

.preview-error{padding:40px;text-align:center;color:var(--text2)}
.preview-error .icon{font-size:48px;margin-bottom:12px}

/* ── Bookmark panel ── */
.bookmark-list{padding:12px;width:100%;max-height:400px;overflow-y:auto}
.bm-item{display:flex;align-items:center;gap:10px;padding:10px;border-radius:8px;cursor:pointer;transition:background .15s}
.bm-item:hover{background:var(--hover)}
.bm-name{font-size:14px;font-weight:500;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.bm-path{font-size:11px;color:var(--text2)}
.bm-del{width:28px;height:28px;display:flex;align-items:center;justify-content:center;border-radius:6px;border:none;background:none;color:var(--text2);font-size:14px;cursor:pointer}
.bm-del:hover{background:rgba(239,68,68,.2);color:var(--danger)}
.bm-empty{text-align:center;padding:30px;color:var(--text2);font-size:14px}

/* ── Drives ── */
.drive-item{display:flex;align-items:center;gap:14px;padding:16px;margin:6px 16px;background:var(--card);border-radius:var(--radius);border:1px solid var(--border);cursor:pointer;transition:all .15s}
.drive-item:hover{border-color:var(--accent);background:var(--hover)}
.drive-icon{font-size:32px}
.drive-name{font-size:16px;font-weight:600}

/* ── Toast ── */
.toast{position:fixed;bottom:80px;left:50%;transform:translateX(-50%);background:var(--card);border:1px solid var(--border);color:var(--text);padding:10px 20px;border-radius:var(--radius);font-size:14px;z-index:999;opacity:0;transition:opacity .3s;pointer-events:none}
.toast.show{opacity:1}

/* ── File Editor ── */
.editor-wrap{width:100%;height:100%;display:flex;flex-direction:column}
.editor-textarea{width:100%;flex:1;padding:16px;margin:0;border:none;outline:none;resize:none;background:#12141c;color:#d4d4d8;font-family:"Cascadia Code","Fira Code","JetBrains Mono",monospace;font-size:13px;line-height:1.6;tab-size:4;white-space:pre-wrap}
.editor-status{padding:6px 16px;background:var(--card);border-top:1px solid var(--border);font-size:12px;color:var(--text2);display:flex;justify-content:space-between;flex-shrink:0}
.editor-status .modified{color:var(--warn)}

::-webkit-scrollbar{width:6px;height:6px}
::-webkit-scrollbar-track{background:transparent}
::-webkit-scrollbar-thumb{background:var(--border);border-radius:3px}
</style>
</head>
<body>

<!-- ═══ Login Page ═══ -->
<div id="loginPage" class="login-page" style="display:none">
  <div class="login-card">
    <h2>&#x1f512; File Browser</h2>
    <p class="sub" data-i18n="loginHint">请输入访问密码</p>
    <div id="qrcode" class="qr-box"></div>
    <input type="password" class="login-input" id="loginPwd" placeholder="&#x2022;&#x2022;&#x2022;&#x2022;&#x2022;&#x2022;" maxlength="32" autofocus>
    <button class="login-btn" onclick="doLogin()" data-i18n="loginBtn">登录</button>
    <div class="login-error" id="loginError"></div>
  </div>
</div>

<!-- ═══ Main App ═══ -->
<div id="mainApp" style="display:none">
  <div class="header">
    <div class="header-top">
      <div class="logo">&#x1f4c2; <span>File Browser</span></div>
      <button class="tool-btn" id="logoutBtn" onclick="doLogout()" style="display:none" data-i18n="logout">&#x1f6aa; 登出</button>
    </div>
    <!-- Toolbar -->
    <div class="toolbar" id="toolbar">
      <button class="tool-btn" onclick="showUpload()" title="上传文件" data-i18n="upload" data-i18n-title="uploadTitleTip">&#x2b06; 上传</button>
      <button class="tool-btn" onclick="showMkdir()" title="新建文件夹" data-i18n="mkdir" data-i18n-title="mkdirTitleTip">&#x1f4c1;+ 文件夹</button>
      <button class="tool-btn" onclick="showMkfile()" title="新建文件" data-i18n="mkfile" data-i18n-title="mkfileTitleTip">&#x1f4c4;+ 文件</button>
      <button class="tool-btn" id="selectBtn" onclick="toggleSelectMode()" title="多选模式" data-i18n="select" data-i18n-title="selectTitleTip">&#x2610; 多选</button>
      <button class="tool-btn" id="selectAllBtn" onclick="toggleSelectAll()" style="display:none" title="全选/取消全选" data-i18n="selectAll" data-i18n-title="selectAllTitleTip">&#x2611; 全选</button>
      <button class="tool-btn" id="batchDlBtn" onclick="batchDownload()" style="display:none" title="批量下载" data-i18n="batchDl" data-i18n-title="batchDlTitleTip">&#x1f4e6; 打包下载</button>
      <button class="tool-btn" id="batchDelBtn" onclick="batchDelete()" style="display:none" title="批量删除" data-i18n="batchDel2" data-i18n-title="batchDelTitleTip">&#x1f5d1; 批量删除</button>
      <button class="tool-btn" id="batchMoveBtn" onclick="batchMove()" style="display:none" title="批量移动" data-i18n="batchMove" data-i18n-title="batchMoveTitleTip">&#x2702; 批量移动</button>
      <button class="tool-btn" id="batchCopyBtn" onclick="batchCopy()" style="display:none" title="批量复制" data-i18n="batchCopy" data-i18n-title="batchCopyTitleTip">&#x1f4cb; 批量复制</button>
      <button class="tool-btn" onclick="showClipboard()" title="共享剪贴板" data-i18n="clipboard" data-i18n-title="clipboardTitleTip">&#x1f4cb; 剪贴板</button>
      <button class="tool-btn" onclick="showBookmarks()" title="收藏夹" data-i18n="bookmarks" data-i18n-title="bookmarksTitleTip">&#x2b50; 收藏</button>
      <button class="tool-btn" id="bmAddBtn" onclick="addBookmark()" title="收藏当前目录" data-i18n-title="bmAddTitle" style="display:none">&#x2795;&#x2b50;</button>
      <button class="tool-btn" id="gridViewBtn" onclick="toggleGridView()" title="切换网格/列表视图" data-i18n-title="gridToggleTitle">&#x2756;</button>
      <button class="tool-btn" id="themeBtn" onclick="toggleTheme()" title="切换亮/暗主题" data-i18n-title="themeToggleTitle">&#x1f319;</button>
      <button class="tool-btn" id="langBtn" onclick="toggleLang()" title="切换语言" data-i18n-title="langToggleTitle">中</button>
    </div>
    <div class="search-box">
      <div class="search-inner">
        <span class="search-icon">&#x1f50d;</span>
        <input type="text" id="searchInput" data-i18n-ph="searchPh" placeholder="搜索文件名或内容...">
        <button class="search-clear" id="searchClear" onclick="clearSearch()">&#x2715;</button>
      </div>
    </div>
    <div class="search-mode" id="searchModeBar" style="display:none">
      <button class="active" id="searchModeName" onclick="setSearchMode('name')" data-i18n="searchName">文件名搜索</button>
      <button id="searchModeContent" onclick="setSearchMode('content')" data-i18n="searchContent">内容搜索</button>
    </div>
    <div id="breadcrumb" class="breadcrumb"></div>
    <div class="sort-bar">
      <span class="filter-label" data-i18n="sortLabel">排序:</span>
      <button class="sort-btn active" data-sort="name" onclick="setSort('name')" data-i18n="sortName">名称</button>
      <button class="sort-btn" data-sort="size" onclick="setSort('size')" data-i18n="sortSize">大小</button>
      <button class="sort-btn" data-sort="ctime" onclick="setSort('ctime')" data-i18n="sortCtime">创建时间</button>
      <button class="sort-btn" data-sort="mtime" onclick="setSort('mtime')" data-i18n="sortMtime">修改时间</button>
    </div>
    <div class="filter-bar" id="filterBar">
      <span class="filter-label" data-i18n="filterLabel">筛选:</span>
      <select class="filter-select" id="filterType" onchange="applyFilter()">
        <option value="" data-i18n-opt="filterAll">全部类型</option>
        <option value="image" data-i18n-opt="filterImage">&#x1f5bc; 图片</option>
        <option value="video" data-i18n-opt="filterVideo">&#x1f3ac; 视频</option>
        <option value="audio" data-i18n-opt="filterAudio">&#x1f3b5; 音频</option>
        <option value="markdown">&#x1f4d8; Markdown</option>
        <option value="text" data-i18n-opt="filterText">&#x1f4dd; 文本/代码</option>
        <option value="pdf">&#x1f4d5; PDF</option>
        <option value="archive" data-i18n-opt="filterArchive">&#x1f4e6; 压缩包</option>
        <option value="office">&#x1f4ca; Office</option>
        <option value="font" data-i18n-opt="filterFont">&#x1f524; 字体</option>
        <option value="other" data-i18n-opt="filterOther">&#x1f4c4; 其他</option>
      </select>
      <input class="filter-input" id="filterExt" type="text" data-i18n-ph="filterExtPh" placeholder="后缀 如 .py,.md" onchange="applyFilter()" onkeydown="if(event.key==='Enter')applyFilter()">
      <button class="filter-clear" onclick="clearFilter()" data-i18n-title="filterClear" title="清除筛选">&#x2715;</button>
    </div>
  </div>
  <div class="status"><span class="status-dot"></span><span id="statusText" data-i18n="statusReady">就绪</span></div>
  <div class="loading" id="loading"><div class="spinner"></div></div>
  <div id="dropOverlay" data-i18n="dropHint">&#x1f4e4; 松开鼠标上传文件</div>
  <div id="dragUploadToast"><div class="upload-progress-text" id="dragUploadText"></div><div class="upload-progress"><div class="upload-progress-bar"><div class="upload-progress-fill" id="dragUploadBar"></div></div></div></div>
  <div id="content" class="file-list"></div>
</div>

<!-- ═══ Preview Modal ═══ -->
<div class="modal-overlay" id="modal" onclick="if(event.target===this)closeModal()">
  <div class="modal">
    <div class="modal-header">
      <span class="modal-title" id="modalTitle"></span>
      <div class="modal-actions">
        <button class="modal-btn modal-btn-close" id="modalBack" style="display:none" onclick="mdGoBack()" data-i18n="modalBack">&#x2190; 返回</button>
        <button class="modal-btn modal-btn-primary" id="modalEdit" style="display:none" onclick="toggleEdit()" data-i18n="modalEdit">&#x270f; 编辑</button>
        <button class="modal-btn modal-btn-primary" id="modalSave" style="display:none" onclick="saveFile()" data-i18n="modalSave">&#x1f4be; 保存</button>
        <button class="modal-btn modal-btn-close" id="modalCancelEdit" style="display:none" onclick="cancelEdit()" data-i18n="modalCancelEdit">取消编辑</button>
        <button class="modal-btn modal-btn-primary" id="modalDownload" data-i18n="modalDownload">下载</button>
        <button class="modal-btn modal-btn-close" id="modalShare" style="display:none" onclick="showShareDialog()" data-i18n="modalShare">&#x1f517; 分享</button>
        <button class="modal-btn modal-btn-close" onclick="closeModal()" data-i18n="modalClose">关闭</button>
      </div>
    </div>
    <div class="modal-body" id="modalBody"></div>
    <div class="file-detail" id="modalDetail" style="display:none"></div>
  </div>
</div>

<!-- ═══ Generic Dialog ═══ -->
<div class="modal-overlay" id="dialog" onclick="if(event.target===this)closeDialog()">
  <div class="modal modal-sm">
    <div class="modal-header">
      <span class="modal-title" id="dialogTitle"></span>
      <button class="modal-btn modal-btn-close" onclick="closeDialog()">&#x2715;</button>
    </div>
    <div class="modal-body" id="dialogBody" style="display:block"></div>
  </div>
</div>

<!-- Author Footer -->
<div class="app-footer" id="authorFooter" data-sig="LFB-bbloveyy-2026">
  Made by <b>白白LOVE尹尹</b>
  <br><span style="margin-top:4px;display:inline-block">
    <a href="#" onclick="event.preventDefault();showDonate()">Support / 打赏作者</a>
  </span>
</div>

<!-- Toast -->
<div class="toast" id="toast"></div>

<script>
// ═══ Markdown Setup ═══
if(typeof marked!=='undefined'){marked.setOptions({breaks:true,gfm:true,highlight:function(code,lang){if(typeof hljs!=='undefined'&&lang&&hljs.getLanguage(lang)){try{return hljs.highlight(code,{language:lang}).value}catch(e){}}if(typeof hljs!=='undefined'){try{return hljs.highlightAuto(code).value}catch(e){}}return code}})}

// ═══ Mermaid Setup ═══
// 初始化 mermaid：深色主题，不自动渲染（我们手动控制渲染时机）
if(typeof mermaid!=='undefined'){
    mermaid.initialize({startOnLoad:false,theme:'dark',securityLevel:'strict',
        themeVariables:{primaryColor:'#6366f1',primaryTextColor:'#e4e4e7',lineColor:'#818cf8',secondaryColor:'#1a1d27'}});
}

/**
 * 在 Markdown 渲染后，将 mermaid 代码块转换为 SVG 图形。
 * marked.js 会将 ```mermaid 渲染为 <pre><code class="language-mermaid">...</code></pre>
 * 此函数找到这些元素，用 mermaid.render() 替换为实际图形。
 */
async function renderMermaidBlocks(container){
    if(typeof mermaid==='undefined') return;
    // 找到所有 mermaid 代码块
    const blocks=container.querySelectorAll('pre code.language-mermaid, pre code.hljs.language-mermaid');
    for(let i=0;i<blocks.length;i++){
        const codeEl=blocks[i];
        const preEl=codeEl.parentElement;
        const graphDef=codeEl.textContent;
        try{
            const id='mermaid-'+Date.now()+'-'+i;
            const {svg}=await mermaid.render(id, graphDef);
            // 用渲染结果替换原来的代码块
            // 注意：Mermaid 在 securityLevel:'strict' 模式下生成的 SVG 是安全的，
            // 不能用 DOMPurify 过滤，否则会剥离 <foreignObject> 导致文字消失
            const div=document.createElement('div');
            div.className='mermaid-rendered';
            div.innerHTML=svg;
            preEl.replaceWith(div);
        }catch(e){
            // 渲染失败时保留原始代码块，加一个错误提示
            preEl.style.borderColor='var(--warn)';
            const hint=document.createElement('div');
            hint.style.cssText='color:var(--warn);font-size:12px;padding:4px 14px';
            hint.textContent=t('mermaidFail')+e.message;
            preEl.parentElement.insertBefore(hint,preEl);
        }
    }
}

// ═══ State ═══
let currentPath="";
let sortBy="name";
let sortOrder="asc";
let filterType="";    // 文件类型筛选
let filterExt="";     // 扩展名筛选
let searchTimeout=null;
let isSearching=false;
let selectMode=false;
let selectedPaths=new Set();
let searchMode="name"; // "name" or "content"

// ═══ Init ═══
window.addEventListener("load",async()=>{
    const _af=document.getElementById("authorFooter");
    if(!_af||!_af.innerHTML.includes("\u767d\u767dLOVE\u5c39\u5c39")||!_af.dataset.sig){
        document.body.innerHTML='<div style="padding:60px;text-align:center;color:#ef4444;font-size:18px"><b>Author attribution has been tampered with.</b><br>Original author: \u767d\u767dLOVE\u5c39\u5c39<br>Please restore the original author information.</div>';
        return;
    }
    const _sd=showDonate.toString();
    if(!_sd.includes("bbyybb")||!_sd.includes("buymeacoffee")||!_sd.includes("sponsors/bbyybb")){
        document.body.innerHTML='<div style="padding:60px;text-align:center;color:#ef4444;font-size:18px"><b>Donation information has been tampered with.</b><br>Original author: \u767d\u767dLOVE\u5c39\u5c39<br>Please restore the original donation information.</div>';
        return;
    }
    const r=await fetch("/api/check-auth").then(r=>r.json());
    // 只读模式：隐藏所有写操作按钮
    if(r.read_only) applyReadOnly();
    if(r.need_auth&&!r.logged_in){
        showLoginPage();
    }else{
        showMainApp();
        // 需要认证时显示登出按钮
        if(r.need_auth){const lb=document.getElementById("logoutBtn");if(lb)lb.style.display=""}
    }
});
window.addEventListener("popstate",(e)=>{if(e.state&&e.state.path!==undefined)loadPath(e.state.path,false)});
setInterval(()=>{if(!_vrf()){document.body.innerHTML='<div style="padding:60px;text-align:center;color:#ef4444;font-size:18px"><b>Author attribution has been tampered with.</b><br>Original author: \u767d\u767dLOVE\u5c39\u5c39</div>'}},45000);

let isReadOnly=false;
function applyReadOnly(){
    isReadOnly=true;
    // 隐藏工具栏中的写操作按钮
    const hideIds=["toolbar"];
    const toolbar=document.getElementById("toolbar");
    if(toolbar){
        // 上传、新建文件夹、新建文件按钮隐藏
        toolbar.querySelectorAll(".tool-btn").forEach(btn=>{
            const key=btn.getAttribute("data-i18n")||"";
            if(key==="upload"||key==="mkdir"||key==="mkfile")btn.style.display="none";
        });
    }
}

// ═══ Auth ═══
function showLoginPage(){
    document.getElementById("loginPage").style.display="flex";
    document.getElementById("mainApp").style.display="none";
    applyLang(currentLang);
    // 生成二维码
    try{
        const url=location.href;
        if(typeof qrcode!=='undefined'){
            const qr=qrcode(0,'M');
            qr.addData(url);
            qr.make();
            document.getElementById("qrcode").innerHTML=qr.createImgTag(4,8);
        }
    }catch(e){}
    document.getElementById("loginPwd").focus();
    document.getElementById("loginPwd").addEventListener("keydown",(e)=>{if(e.key==="Enter")doLogin()});
}
function showMainApp(){
    document.getElementById("loginPage").style.display="none";
    document.getElementById("mainApp").style.display="block";
    // 恢复上次位置
    const last=localStorage.getItem("fb_last_path")||"";
    loadPath(last);
    document.getElementById("searchInput").addEventListener("input",onSearchInput);
}
const _loginErrMap={"密码错误":"errWrongPwd","尝试次数过多，请稍后再试":"errRateLimit","请求无效":"errInvalidReq"};
async function doLogin(){
    const pwd=document.getElementById("loginPwd").value;
    const r=await fetch("/api/login",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({password:pwd})}).then(r=>r.json());
    if(r.ok){
        // 多用户模式下根据角色应用只读
        if(r.role==="readonly") applyReadOnly();
        showMainApp();
        // 登录成功后显示登出按钮
        const lb=document.getElementById("logoutBtn");if(lb)lb.style.display="";
    }
    else{const k=_loginErrMap[r.error];const tr=k?t(k):null;document.getElementById("loginError").textContent=tr||r.error||t("loginFail")}
}

// ═══ Navigation ═══
let _vc=0;
function _vrf(){const _a=document.getElementById("authorFooter");if(!_a||!_a.innerHTML.includes("\u767d\u767dLOVE\u5c39\u5c39"))return false;const _s=typeof showDonate==='function'?showDonate.toString():'';return _s.includes("bbyybb")&&_s.includes("buymeacoffee")}
function loadPath(path,pushState=true){
    isSearching=false;
    currentPath=path;
    if(pushState)history.pushState({path},"","#"+encodeURIComponent(path));
    // 保存到 localStorage
    localStorage.setItem("fb_last_path",path);
    if(++_vc%5===0&&!_vrf()){document.body.innerHTML='<div style="padding:60px;text-align:center;color:#ef4444;font-size:18px"><b>Author attribution has been tampered with.</b><br>Original author: \u767d\u767dLOVE\u5c39\u5c39</div>';return}
    updateBreadcrumb(path);
    fetchList(path);
    // 显示/隐藏收藏按钮
    document.getElementById("bmAddBtn").style.display=path?"":"none";
    // 退出选择模式
    if(selectMode)toggleSelectMode();
}
function fetchList(path){
    const content=document.getElementById("content");
    const loading=document.getElementById("loading");
    loading.classList.add("show");
    content.innerHTML="";
    let url=`/api/list?path=${encodeURIComponent(path)}&sort=${sortBy}&order=${sortOrder}`;
    if(filterType) url+=`&filter_type=${encodeURIComponent(filterType)}`;
    if(filterExt) url+=`&filter_ext=${encodeURIComponent(filterExt)}`;
    fetch(url)
    .then(r=>{if(r.status===401){showLoginPage();throw"auth"}return r.json()})
    .then(data=>{
        loading.classList.remove("show");
        if(data.error){content.innerHTML=`<div class="empty"><div class="empty-icon">&#x26a0;&#xfe0f;</div><div>${eh(data.error)}</div></div>`;return}
        if(Array.isArray(data)){renderDrives(data)}
        else{
            renderFileList(data.items);
            let status=`${data.items.length}${t("statusItems")}${data.path}`;
            if(filterType||filterExt) status+=` ${t("statusFiltered")}`;
            document.getElementById("statusText").textContent=status;
        }
    }).catch(e=>{if(e==="auth")return;loading.classList.remove("show");content.innerHTML=`<div class="empty"><div class="empty-icon">&#x274c;</div><div>${t("loadFail")}</div></div>`});
}
function renderDrives(drives){
    const content=document.getElementById("content");
    content.innerHTML=drives.map(d=>`<div class="drive-item" onclick="loadPath('${esc(d.path)}')"><span class="drive-icon">&#x1f4be;</span><span class="drive-name">${eh(d.name)}</span></div>`).join("");
    document.getElementById("statusText").textContent=`${drives.length}${t("statusDrives")}`;
}
function renderFileList(items){
    lastItems=items; // 保存用于网格切换重渲染
    const content=document.getElementById("content");
    if(!items.length){content.innerHTML=`<div class="empty"><div class="empty-icon">&#x1f4ed;</div><div>${t("emptyFolder")}</div></div>`;return}
    content.innerHTML=items.map(item=>{
        const isSelected=selectedPaths.has(item.path);
        const matchHtml=item.matches?`<div class="match-lines">${item.matches.map(m=>`<div class="match-line"><span class="ln">L${m.line}</span>${eh(m.text)}</div>`).join("")}</div>`:"";
        // 网格模式下图片显示缩略图（icon 用 eh() 转义后存入 data 属性，避免内联 JS 注入）
        const iconHtml=(isGridView&&item.type==="image"&&!item.is_dir)
            ?`<img class="file-thumb" src="/api/raw?path=${encodeURIComponent(item.path)}" loading="lazy" data-fallback="${eh(item.icon)}" onerror="const s=document.createElement('span');s.className='file-icon';s.textContent=this.dataset.fallback;this.replaceWith(s)">`
            :`<span class="file-icon">${item.icon}</span>`;
        return `<div class="file-item${isSelected?" selected":""}" data-path="${esc(item.path)}" data-isdir="${item.is_dir}" onclick="onItemClick(event,'${esc(item.path)}',${item.is_dir},'${esc(item.name)}','${item.type}')">
            <div class="file-check${isSelected?" checked":""}" onclick="event.stopPropagation();toggleSelect('${esc(item.path)}',this.parentElement)"></div>
            ${iconHtml}
            <div class="file-info">
                <div class="file-name">${eh(item.name)}</div>
                <div class="file-meta"><span>${item.size_str||""}</span><span>${item.ext||""}</span><span>${sortBy==="ctime"&&item.created?t("createdPrefix")+item.created:item.modified||""}</span></div>
                ${item.dir?`<div class="file-dir">${eh(item.dir)}</div>`:""}
                ${matchHtml}
            </div>
            ${!item.is_dir?`<div class="file-actions">
                ${isReadOnly?"":`<button class="file-act" onclick="event.stopPropagation();renamePrompt('${esc(item.path)}','${esc(item.name)}')" title="${t('actRename')}">&#x270f;</button>
                <button class="file-act" onclick="event.stopPropagation();deleteConfirm('${esc(item.path)}','${esc(item.name)}')" title="${t('actDelete')}">&#x1f5d1;</button>`}
                <button class="file-act" onclick="event.stopPropagation();downloadFile('${esc(item.path)}')" title="${t('actDownload')}">&#x2b07;</button>
                ${isReadOnly?"":`<button class="file-act" onclick="event.stopPropagation();copyPrompt('${esc(item.path)}','${esc(item.name)}')" title="${t('actCopy')}">&#x1f4cb;</button>
                <button class="file-act" onclick="event.stopPropagation();movePrompt('${esc(item.path)}','${esc(item.name)}')" title="${t('actMove')}">&#x2702;</button>`}
            </div>`:`<div class="file-actions">
                ${isReadOnly?"":`<button class="file-act" onclick="event.stopPropagation();renamePrompt('${esc(item.path)}','${esc(item.name)}')" title="${t('actRename')}">&#x270f;</button>
                <button class="file-act" onclick="event.stopPropagation();deleteConfirm('${esc(item.path)}','${esc(item.name)}')" title="${t('actDelete')}">&#x1f5d1;</button>`}
                <button class="file-act" onclick="event.stopPropagation();downloadFolder('${esc(item.path)}','${esc(item.name)}')" title="${t('actDownloadFolder')}">&#x2b07;</button>
                ${isReadOnly?"":`<button class="file-act" onclick="event.stopPropagation();copyPrompt('${esc(item.path)}','${esc(item.name)}')" title="${t('actCopy')}">&#x1f4cb;</button>
                <button class="file-act" onclick="event.stopPropagation();movePrompt('${esc(item.path)}','${esc(item.name)}')" title="${t('actMove')}">&#x2702;</button>`}
            </div>`}
        </div>`;
    }).join("");
}
function onItemClick(e,path,isDir,name,type){
    if(selectMode){toggleSelect(path,e.currentTarget);return}
    if(isDir)loadPath(path);
    else previewFile(path,name,type);
}

// ═══ Breadcrumb ═══
function updateBreadcrumb(path){
    const el=document.getElementById("breadcrumb");
    const rootText=(I18N[currentLang]&&I18N[currentLang].breadcrumbRoot)||"🏠 根";
    let html=`<a href="#" onclick="event.preventDefault();loadPath('')">${rootText}</a>`;
    if(path){
        const normalized=path.replace(/\\/g,"/");
        const parts=normalized.split("/").filter(Boolean);
        let acc=normalized.startsWith("/")?"/":"";
        for(let i=0;i<parts.length;i++){
            acc+=parts[i]+"/";
            // Windows 盘符(如 "D:")点击时保留尾部斜杠，确保传入 "D:/" 而非 "D:"
            const linkPath=(i===0&&parts[i].endsWith(":"))?acc:acc.slice(0,-1);
            html+=`<span class="sep">&#x203a;</span><a href="#" onclick="event.preventDefault();loadPath('${esc(linkPath)}')">${eh(parts[i])}</a>`;
        }
    }
    el.innerHTML=html;el.scrollLeft=el.scrollWidth;
}

// ═══ Sort ═══
function setSort(field){
    if(sortBy===field)sortOrder=sortOrder==="asc"?"desc":"asc";
    // 创建时间默认升序（最早在前），修改时间默认降序（最新在前），其余默认升序
    else{sortBy=field;sortOrder=field==="mtime"?"desc":"asc"}
    document.querySelectorAll(".sort-btn").forEach(b=>b.classList.toggle("active",b.dataset.sort===field));
    if(!isSearching)fetchList(currentPath);
}

// ═══ Filter ═══
/**
 * 读取筛选控件的值并刷新列表。
 */
function applyFilter(){
    filterType=document.getElementById("filterType").value;
    filterExt=document.getElementById("filterExt").value.trim();
    if(!isSearching)fetchList(currentPath);
}
/**
 * 清除所有筛选条件。
 */
function clearFilter(){
    filterType="";filterExt="";
    document.getElementById("filterType").value="";
    document.getElementById("filterExt").value="";
    if(!isSearching)fetchList(currentPath);
}

// ═══ Search ═══
function setSearchMode(mode){
    searchMode=mode;
    document.getElementById("searchModeName").classList.toggle("active",mode==="name");
    document.getElementById("searchModeContent").classList.toggle("active",mode==="content");
    const q=document.getElementById("searchInput").value.trim();
    if(q)doSearch(q);
}
function clearSearch(){
    const input=document.getElementById("searchInput");
    input.value="";document.getElementById("searchClear").classList.remove("show");
    document.getElementById("searchModeBar").style.display="none";
    isSearching=false;fetchList(currentPath);input.focus();
}

// ═══ Select Mode & Batch Download ═══
function updateBatchBtnCount(){
    const n=selectedPaths.size;
    const L=I18N[currentLang]||I18N.zh;
    document.getElementById("batchDlBtn").textContent=`${L.batchDl} (${n})`;
    document.getElementById("batchDelBtn").textContent=`${L.batchDel2} (${n})`;
    document.getElementById("batchMoveBtn").textContent=`${L.batchMove} (${n})`;
    document.getElementById("batchCopyBtn").textContent=`${L.batchCopy} (${n})`;
}
function toggleSelectMode(){
    selectMode=!selectMode;
    selectedPaths.clear();
    document.getElementById("selectBtn").classList.toggle("active",selectMode);
    document.getElementById("selectAllBtn").style.display=selectMode?"":"none";
    document.getElementById("batchDlBtn").style.display=selectMode?"":"none";
    // 只读模式下不显示批量修改按钮
    document.getElementById("batchDelBtn").style.display=(selectMode&&!isReadOnly)?"":"none";
    document.getElementById("batchMoveBtn").style.display=(selectMode&&!isReadOnly)?"":"none";
    document.getElementById("batchCopyBtn").style.display=(selectMode&&!isReadOnly)?"":"none";
    document.getElementById("content").classList.toggle("select-mode",selectMode);
    updateBatchBtnCount();
    // 刷新列表以显示/隐藏复选框
    if(!isSearching)fetchList(currentPath);
}
function toggleSelect(path,el){
    if(selectedPaths.has(path)){selectedPaths.delete(path);el.classList.remove("selected");el.querySelector(".file-check").classList.remove("checked")}
    else{selectedPaths.add(path);el.classList.add("selected");el.querySelector(".file-check").classList.add("checked")}
    updateBatchBtnCount();
}
function toggleSelectAll(){
    const items=document.querySelectorAll("#content .file-item");
    // 收集所有可选项（文件和文件夹）
    const allItems=[];
    items.forEach(el=>{
        const path=el.getAttribute("data-path");
        if(path)allItems.push({path,el});
    });
    if(!allItems.length)return;
    // 判断当前是全选还是取消全选：如果所有项都已选中则取消
    const allSelected=allItems.every(f=>selectedPaths.has(f.path));
    allItems.forEach(f=>{
        if(allSelected){
            selectedPaths.delete(f.path);f.el.classList.remove("selected");
            const chk=f.el.querySelector(".file-check");if(chk)chk.classList.remove("checked");
        }else{
            selectedPaths.add(f.path);f.el.classList.add("selected");
            const chk=f.el.querySelector(".file-check");if(chk)chk.classList.add("checked");
        }
    });
    updateBatchBtnCount();
}
async function batchDownload(){
    if(!selectedPaths.size){toast(t("selectFirst"));return}
    showOpProgress(t("packingDl"),true);
    try{
        const r=await fetch("/api/batch-download",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({paths:[...selectedPaths]})});
        if(!r.ok){closeDialog();const d=await r.json();toast(d.error||t("packFail"));return}
        const total=parseInt(r.headers.get("Content-Length")||"0",10);
        const reader=r.body.getReader();const chunks=[];let loaded=0;
        while(true){
            const{done,value}=await reader.read();if(done)break;
            chunks.push(value);loaded+=value.length;
            if(total>0)updateOpProgress({p:loaded,t:total});
        }
        closeDialog();
        const blob=new Blob(chunks,{type:"application/zip"});
        const a=document.createElement("a");
        a.href=URL.createObjectURL(blob);
        a.download=r.headers.get("Content-Disposition")?.match(/filename="?(.+)"?/)?.[1]||"files.zip";
        a.click();URL.revokeObjectURL(a.href);
        toast(t("dlStarted"));
    }catch(e){closeDialog();toast(t("packDlFail"))}
}

// ═══ Batch Delete ═══
function batchDelete(){
    if(!selectedPaths.size){toast(t("selectFirst"));return}
    const n=selectedPaths.size;
    openDialog(t("batchDelTitle"),`<div class="modal-form">
        <div style="text-align:center;padding:10px 0">
            <div style="font-size:32px;margin-bottom:8px">&#x26a0;&#xfe0f;</div>
            <div>${t("batchDelConfirm")} <b>${n}</b> ${t("batchDelUnit")}</div>
            <div class="hint" style="margin-top:4px">${t("batchDelIrreversible")}</div>
        </div>
        <button class="modal-btn modal-btn-danger" onclick="doBatchDelete()" style="width:100%">${t("batchDelBtn")} ${n} ${t("batchMoveUnit")}</button>
    </div>`);
}
async function doBatchDelete(){
    const paths=[...selectedPaths];const total=paths.length;let ok=0,fail=0;
    showOpProgress(t("opDeleting"),false);
    for(let i=0;i<paths.length;i++){
        try{
            const d=await streamOp("/api/delete",{path:paths[i],recursive:true},(prog)=>{
                updateOpProgress({p:prog.p,t:prog.t,f:`[${i+1}/${total}] ${prog.f||""}`});
            });
            if(d.ok)ok++;else fail++;
        }catch(e){fail++}
        updateOpProgress({p:i+1,t:total,f:""});
    }
    closeDialog();
    toast(`${t("batchDelDone")} ${ok}${fail?`, ${fail} ${t("batchFail")}`:""}`);
    selectedPaths.clear();
    updateBatchBtnCount();
    fetchList(currentPath);
}

// ═══ Batch Move ═══
function batchMove(){
    if(!selectedPaths.size){toast(t("selectFirst"));return}
    openDirPicker(`${t("batchMoveTitle")} ${selectedPaths.size} ${t("batchMoveUnit")}`,currentPath,async(destDir)=>{
        let ok=0,fail=0,skipped=0,batchMode=null;
        const paths=[...selectedPaths];const total=paths.length;
        showOpProgress(t("opMoving"),true);
        for(let i=0;i<paths.length;i++){
            const name=paths[i].split("/").pop();
            try{
                const body={src:paths[i],dest_dir:destDir};
                let d=await streamOp("/api/move",body,(prog)=>{updateOpProgress({p:prog.p,t:prog.t,f:`[${i+1}/${total}] ${prog.f||name}`})});
                if(d.ok){if(d.skipped)skipped++;else ok++;continue}
                if(d.conflict){
                    const mode=batchMode||await new Promise(resolve=>{
                        showConflictDialog(d.name,true,(choice,applyAll)=>{if(applyAll)batchMode=choice;resolve(choice)});
                    });
                    body.conflict=mode;
                    showOpProgress(t("opMoving"),true);
                    d=await streamOp("/api/move",body,(prog)=>{updateOpProgress({p:prog.p,t:prog.t,f:`[${i+1}/${total}] ${prog.f||name}`})});
                    if(d.ok){if(d.skipped)skipped++;else ok++}else fail++;
                }else fail++;
            }catch(e){fail++}
        }
        closeDialog();
        toast(`${t("batchMoveDone")} ${ok}${skipped?`, ${skipped} ${t("conflictSkip")}`:""} ${fail?`, ${fail} ${t("batchFail")}`:""}`);
        selectedPaths.clear();
        updateBatchBtnCount();
        fetchList(currentPath);
    });
}

// ═══ Batch Copy ═══
function batchCopy(){
    if(!selectedPaths.size){toast(t("selectFirst"));return}
    openDirPicker(`${t("batchCopyTitle")} ${selectedPaths.size} ${t("batchMoveUnit")}`,currentPath,async(destDir)=>{
        let ok=0,fail=0,skipped=0,batchMode=null;
        const paths=[...selectedPaths];const total=paths.length;
        showOpProgress(t("opCopying"),true);
        for(let i=0;i<paths.length;i++){
            const name=paths[i].split("/").pop();
            try{
                const body={src:paths[i],dest_dir:destDir};
                let d=await streamOp("/api/copy",body,(prog)=>{updateOpProgress({p:prog.p,t:prog.t,f:`[${i+1}/${total}] ${prog.f||name}`})});
                if(d.ok){if(d.skipped)skipped++;else ok++;continue}
                if(d.conflict){
                    const mode=batchMode||await new Promise(resolve=>{
                        showConflictDialog(d.name,true,(choice,applyAll)=>{if(applyAll)batchMode=choice;resolve(choice)});
                    });
                    body.conflict=mode;
                    showOpProgress(t("opCopying"),true);
                    d=await streamOp("/api/copy",body,(prog)=>{updateOpProgress({p:prog.p,t:prog.t,f:`[${i+1}/${total}] ${prog.f||name}`})});
                    if(d.ok){if(d.skipped)skipped++;else ok++}else fail++;
                }else fail++;
            }catch(e){fail++}
        }
        closeDialog();
        toast(`${t("batchCopyDone")} ${ok}${skipped?`, ${skipped} ${t("conflictSkip")}`:""} ${fail?`, ${fail} ${t("batchFail")}`:""}`);
        selectedPaths.clear();
        updateBatchBtnCount();
        fetchList(currentPath);
    });
}

// ═══ Upload (分片断点续传) ═══
let _uploadMode="files";
const _CHUNK_THRESHOLD=5*1024*1024;
let _uq={active:false,paused:false,cancelled:false,abortCtrl:null,files:[],current:-1,totalBytes:0,doneBytes:0,curLoaded:0,mode:"dialog",path:"",conflict:"rename"};
function _uqReset(){_uq={active:false,paused:false,cancelled:false,abortCtrl:null,files:[],current:-1,totalBytes:0,doneBytes:0,curLoaded:0,mode:"dialog",path:"",conflict:"rename"}}
function _uqWaitIfPaused(){if(!_uq.paused)return Promise.resolve();return new Promise(r=>{const iv=setInterval(()=>{if(!_uq.paused||_uq.cancelled){clearInterval(iv);r()}},200)})}
function _uqUpdateUI(){
    const done=_uq.files.filter(f=>f.status==="done").length;
    const total=_uq.files.length;
    const bytesNow=_uq.doneBytes+_uq.curLoaded;
    const pct=_uq.totalBytes>0?Math.round(bytesNow*100/_uq.totalBytes):0;
    if(_uq.mode==="dialog"){
        const bar=document.getElementById("uqBar");
        const pctEl=document.getElementById("uqPct");
        const listEl=document.getElementById("uqList");
        const pauseBtn=document.getElementById("uqPauseBtn");
        if(bar)bar.style.width=pct+"%";
        if(pctEl)pctEl.textContent=`${pct}% \u2014 ${done}/${total} ${t("uploadDoneUnit")} (${formatBytes(bytesNow)} / ${formatBytes(_uq.totalBytes)})`;
        if(pauseBtn)pauseBtn.textContent=_uq.paused?t("uploadResumeBtn"):t("uploadPauseBtn");
        if(listEl){
            let html="";
            for(let i=0;i<_uq.files.length;i++){
                const f=_uq.files[i];
                const icon=f.status==="done"?"\u2713":f.status==="uploading"?"\u25b6":f.status==="failed"?"\u2717":f.status==="skipped"?"\u2298":"\u25cb";
                const cls=f.status==="done"?"uq-done":f.status==="uploading"?"uq-active":f.status==="failed"?"uq-fail":f.status==="skipped"?"uq-skip":"";
                const name=f.relPath||f.file.name;
                const size=formatBytes(f.file.size);
                html+=`<div class="uq-item ${cls}"><span class="uq-icon">${icon}</span><span class="uq-name" title="${eh(name)}">${eh(name)}</span><span class="uq-size">${size}</span>`;
                if(f.status==="uploading"&&f.file.size>=_CHUNK_THRESHOLD){
                    const fp=f.file.size>0?Math.round((f.progress||0)*100/f.file.size):0;
                    html+=`<div class="uq-fbar" style="width:100%"><div class="uq-ffill" style="width:${fp}%"></div></div>`;
                }
                html+=`</div>`;
            }
            listEl.innerHTML=html;
            const ac=listEl.querySelector(".uq-active");if(ac)ac.scrollIntoView({block:"nearest"});
        }
    }else{
        const dBar=document.getElementById("dragUploadBar");
        const dText=document.getElementById("dragUploadText");
        if(dBar)dBar.style.width=pct+"%";
        const cn=_uq.current>=0&&_uq.current<_uq.files.length?(_uq.files[_uq.current].relPath||_uq.files[_uq.current].file.name):"";
        if(dText)dText.textContent=`${t("uploadUploading")} ${done}/${total} \u2014 ${pct}%${cn?" | "+cn:""}`;
    }
}
async function startUploadQueue(fileItems,path,conflict,mode){
    _uqReset();_uq.active=true;_uq.mode=mode;_uq.path=path;_uq.conflict=conflict;
    _uq.files=fileItems.map(item=>({file:item.file,relPath:item.relativePath,status:"pending",progress:0}));
    _uq.totalBytes=fileItems.reduce((s,it)=>s+it.file.size,0);
    _uq.abortCtrl=new AbortController();
    if(mode==="dialog"){
        const el=document.getElementById("dialogBody");
        if(el)el.innerHTML=`<div class="uq-wrap">
            <div class="upload-progress-bar"><div class="upload-progress-fill" id="uqBar" style="width:0%"></div></div>
            <div class="upload-progress-text" id="uqPct">0%</div>
            <div class="uq-list" id="uqList"></div>
            <div style="display:flex;gap:8px;margin-top:8px">
                <button class="modal-btn modal-btn-close" id="uqPauseBtn" onclick="toggleUploadPause()" style="flex:1">${t("uploadPauseBtn")}</button>
                <button class="modal-btn modal-btn-danger" onclick="cancelUploadQueue()" style="flex:1">${t("uploadCancelBtn")}</button>
            </div></div>`;
    }else{
        const dToast=document.getElementById("dragUploadToast");
        if(dToast)dToast.style.display="block";
    }
    _uqUpdateUI();
    for(let i=0;i<_uq.files.length;i++){
        if(_uq.cancelled)break;
        await _uqWaitIfPaused();if(_uq.cancelled)break;
        _uq.current=i;_uq.files[i].status="uploading";_uq.curLoaded=0;_uqUpdateUI();
        try{
            const item=_uq.files[i];
            if(item.file.size>=_CHUNK_THRESHOLD){await _uqChunked(item)}else{await _uqSimple(item)}
            if(_uq.files[i].status!=="skipped"){_uq.files[i].status="done";_uq.doneBytes+=item.file.size;_uq.curLoaded=0}
        }catch(e){
            if(e.name==="AbortError"||_uq.cancelled)break;
            _uq.files[i].status="failed";
        }
        _uqUpdateUI();
    }
    _uq.active=false;
    const doneN=_uq.files.filter(f=>f.status==="done").length;
    const failN=_uq.files.filter(f=>f.status==="failed").length;
    const skipN=_uq.files.filter(f=>f.status==="skipped").length;
    let msg=`${t("uploadDone")} ${doneN} ${t("uploadDoneUnit")}`;
    if(skipN>0)msg+=`, ${t("uploadSkippedN")} ${skipN}`;
    if(failN>0)msg+=`, ${t("uploadFailCount")}${failN}`;
    if(_uq.cancelled)msg=t("uploadCancelled");
    if(mode==="dialog"){
        const el=document.getElementById("dialogBody");
        if(el)el.innerHTML=`<div class="modal-form" style="text-align:center;padding:20px 0">
            <div style="font-size:24px;margin-bottom:8px">${_uq.cancelled?"\u26a0":"\u2705"}</div>
            <div>${msg}</div>
            <button class="modal-btn modal-btn-primary" onclick="closeDialog()" style="width:100%;margin-top:12px">${t("uploadCloseBtn")}</button></div>`;
        toast(msg);
    }else{
        const dToast=document.getElementById("dragUploadToast");
        if(dToast)setTimeout(()=>{dToast.style.display="none"},2000);
        if(doneN>0)toast(`${t("dragUpload")} ${doneN} ${t("uploadDoneUnit")}`);
        if(failN>0)toast(t("dragUploadFail")+failN);
    }
    fetchList(currentPath);
}
async function _uqSimple(item){
    const fd=new FormData();fd.append("path",_uq.path);fd.append("conflict",_uq.conflict);fd.append("files",item.file);
    if(item.relPath)fd.append("relativePaths",JSON.stringify([item.relPath]));
    const r=await xhrUpload(fd,(pct,loaded)=>{_uq.curLoaded=loaded;_uqUpdateUI()},_uq.abortCtrl.signal);
    if(r.skipped&&r.skipped.length>0)_uq.files[_uq.current].status="skipped";
    if(r.errors&&r.errors.length>0)throw new Error(r.errors[0]);
}
async function _uqChunked(item){
    const signal=_uq.abortCtrl.signal;
    const initR=await fetch("/api/upload-init",{method:"POST",headers:{"Content-Type":"application/json","X-Requested-With":"XMLHttpRequest"},body:JSON.stringify({path:_uq.path,filename:item.file.name,size:item.file.size,relativePath:item.relPath||"",conflict:_uq.conflict}),signal}).then(r=>r.json());
    if(initR.error)throw new Error(initR.error);
    if(initR.skipped){_uq.files[_uq.current].status="skipped";return}
    const{upload_id,chunk_size}=initR;let offset=initR.uploaded_bytes||0;
    item.progress=offset;_uq.curLoaded=offset;_uqUpdateUI();
    while(offset<item.file.size){
        await _uqWaitIfPaused();
        if(_uq.cancelled){fetch("/api/upload-cancel",{method:"POST",headers:{"Content-Type":"application/json","X-Requested-With":"XMLHttpRequest"},body:JSON.stringify({upload_id})}).catch(()=>{});throw new DOMException("Cancelled","AbortError")}
        if(signal.aborted)throw new DOMException("Aborted","AbortError");
        const end=Math.min(offset+chunk_size,item.file.size);
        const chunk=item.file.slice(offset,end);
        const fd=new FormData();fd.append("upload_id",upload_id);fd.append("offset",String(offset));fd.append("chunk",chunk,"chunk.bin");
        const cR=await xhrPost("/api/upload-chunk",fd,(loaded)=>{item.progress=offset+loaded;_uq.curLoaded=offset+loaded;_uqUpdateUI()},signal);
        if(cR.error)throw new Error(cR.error);
        offset=cR.uploaded_bytes;item.progress=offset;_uq.curLoaded=offset;
    }
    const compR=await fetch("/api/upload-complete",{method:"POST",headers:{"Content-Type":"application/json","X-Requested-With":"XMLHttpRequest"},body:JSON.stringify({upload_id}),signal}).then(r=>r.json());
    if(compR.error)throw new Error(compR.error);
}
function toggleUploadPause(){_uq.paused=!_uq.paused;_uqUpdateUI()}
function cancelUploadQueue(){_uq.cancelled=true;_uq.paused=false;if(_uq.abortCtrl)_uq.abortCtrl.abort()}
function showUpload(){
    if(!currentPath){toast(t("enterDirFirst"));return}
    _uploadMode="files";
    openDialog(t("uploadTitle"),`<div class="modal-form">
        <label>${t("uploadTarget")}${eh(currentPath)}</label>
        <input type="file" id="uploadFiles" multiple style="display:none">
        <input type="file" id="uploadFolder" webkitdirectory style="display:none">
        <div style="display:flex;align-items:center;gap:10px;padding:8px 0;flex-wrap:wrap">
            <button class="modal-btn modal-btn-close" onclick="document.getElementById('uploadFiles').click()" type="button">&#x1f4c2; ${t("uploadChoose")}</button>
            <button class="modal-btn modal-btn-close" onclick="document.getElementById('uploadFolder').click()" type="button">&#x1f4c1; ${t("uploadChooseFolder")}</button>
            <span id="uploadFileLabel" style="font-size:13px;color:var(--text2)">${t("uploadNoFile")}</span>
        </div>
        <div class="hint">${t("uploadHint")} | ${t("uploadFolderHint")}</div>
        <div style="display:flex;align-items:center;gap:8px;padding:6px 0;font-size:13px;flex-wrap:wrap">
            <span style="color:var(--text2)">${t("uploadConflictLabel")}</span>
            <label style="cursor:pointer"><input type="radio" name="uploadConflict" value="rename" checked> ${t("conflictRename")}</label>
            <label style="cursor:pointer"><input type="radio" name="uploadConflict" value="overwrite"> ${t("conflictOverwrite")}</label>
            <label style="cursor:pointer"><input type="radio" name="uploadConflict" value="skip"> ${t("conflictSkip")}</label>
        </div>
        <button class="modal-btn modal-btn-primary" onclick="doUpload()" style="width:100%">${t("uploadBtn")}</button>
    </div>`);
    document.getElementById("uploadFiles").addEventListener("change",function(){
        _uploadMode="files";const n=this.files.length;
        document.getElementById("uploadFileLabel").textContent=n?t("uploadFileCount").replace("{n}",n):t("uploadNoFile");
    });
    document.getElementById("uploadFolder").addEventListener("change",function(){
        _uploadMode="folder";const n=this.files.length;
        document.getElementById("uploadFileLabel").textContent=n?t("uploadFolderCount").replace("{n}",n):t("uploadNoFile");
    });
}
async function doUpload(){
    const isFolder=(_uploadMode==="folder");
    const input=document.getElementById(isFolder?"uploadFolder":"uploadFiles");
    const files=input.files;if(!files.length){toast(t("selectFiles"));return}
    const conflictRadio=document.querySelector('input[name="uploadConflict"]:checked');
    const conflict=conflictRadio?conflictRadio.value:"rename";
    const items=[];for(const f of files)items.push({file:f,relativePath:isFolder?f.webkitRelativePath:""});
    await startUploadQueue(items,currentPath,conflict,"dialog");
}

// ═══ Mkdir ═══
function showMkdir(){
    if(!currentPath){toast(t("enterDirFirst"));return}
    openDialog(t("mkdirTitle"),`<div class="modal-form">
        <label>${t("mkdirIn")} ${eh(currentPath)} ${t("mkdirCreate")}</label>
        <input type="text" id="mkdirName" placeholder="${t("mkdirPlaceholder")}" autofocus>
        <button class="modal-btn modal-btn-primary" onclick="doMkdir()" style="width:100%">${t("mkdirBtn")}</button>
    </div>`);
    setTimeout(()=>{const el=document.getElementById("mkdirName");el.focus();el.addEventListener("keydown",e=>{if(e.key==="Enter")doMkdir()})},100);
}
async function doMkdir(){
    const name=document.getElementById("mkdirName").value.trim();
    if(!name){toast(t("enterName"));return}
    const r=await fetch("/api/mkdir",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({path:currentPath,name})}).then(r=>r.json());
    if(r.ok){closeDialog();toast(t("createOk"));fetchList(currentPath)}
    else toast(r.error||t("createFail"));
}

// ═══ Mkfile ═══
function showMkfile(){
    if(!currentPath){toast(t("enterDirFirst"));return}
    openDialog(t("mkfileTitle"),`<div class="modal-form">
        <label>${t("mkdirIn")} ${eh(currentPath)} ${t("mkdirCreate")}</label>
        <input type="text" id="mkfileName" placeholder="${t("mkfilePlaceholder")}" autofocus>
        <div class="hint">${t("mkfileHint")}</div>
        <label>${t("mkfileContentLabel")}</label>
        <textarea id="mkfileContent" placeholder="${t("mkfileContentPh")}" rows="6"></textarea>
        <button class="modal-btn modal-btn-primary" onclick="doMkfile()" style="width:100%">${t("mkfileBtn")}</button>
    </div>`);
    setTimeout(()=>{const el=document.getElementById("mkfileName");el.focus();el.addEventListener("keydown",e=>{if(e.key==="Enter"&&!e.shiftKey){e.preventDefault();doMkfile()}})},100);
}
async function doMkfile(){
    const name=document.getElementById("mkfileName").value.trim();
    const content=document.getElementById("mkfileContent").value;
    if(!name){toast(t("enterFilename"));return}
    if(!name.includes(".")){toast(t("extHint"));return}
    const r=await fetch("/api/mkfile",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({path:currentPath,name,content})}).then(r=>r.json());
    if(r.ok){closeDialog();toast(t("fileCreated")+name);fetchList(currentPath)}
    else toast(r.error||t("createFail"));
}

// ═══ Delete ═══
function deleteConfirm(path,name){
    openDialog(t("deleteTitle"),`<div class="modal-form">
        <div style="text-align:center;padding:10px 0">
            <div style="font-size:32px;margin-bottom:8px">&#x26a0;&#xfe0f;</div>
            <div>${t("deleteMsg")} <b>${eh(name)}</b>${t("deleteAsk")}</div>
            <div class="hint" style="margin-top:4px">${t("deleteIrreversible")}</div>
        </div>
        <button class="modal-btn modal-btn-danger" onclick="doDelete('${esc(path)}',false)" style="width:100%">${t("deleteBtn")}</button>
    </div>`);
}
async function doDelete(path, recursive=false){
    if(recursive){
        showOpProgress(t("opDeleting"),false);
        const d=await streamOp("/api/delete",{path,recursive:true},updateOpProgress);
        closeDialog();
        if(d.ok){toast(t("deleted"));fetchList(currentPath)}
        else toast(d.error||t("deleteFail"));
        return;
    }
    const r=await fetch("/api/delete",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({path, recursive})}).then(r=>r.json());
    if(r.ok){closeDialog();toast(t("deleted"));fetchList(currentPath)}
    else if(r.not_empty){
        const name=path.split("/").pop();
        openDialog(t("deleteRecTitle"),`<div class="modal-form">
            <div style="text-align:center;padding:10px 0">
                <div style="font-size:32px;margin-bottom:8px">&#x1f6a8;</div>
                <div><b>${eh(name)}</b> ${t("deleteNotEmpty")}</div>
                <div style="color:var(--danger);margin-top:8px;font-size:13px">${t("deleteRecWarn")}</div>
            </div>
            <button class="modal-btn modal-btn-danger" onclick="doDelete('${esc(path)}',true)" style="width:100%">${t("deleteRecBtn")}</button>
        </div>`);
    } else toast(r.error||t("deleteFail"));
}

// ═══ Rename ═══
function renamePrompt(path,oldName){
    openDialog(t("renameTitle"),`<div class="modal-form">
        <label>${t("renameCurrent")}${eh(oldName)}</label>
        <input type="text" id="renameName" value="${eh(oldName)}" autofocus>
        <button class="modal-btn modal-btn-primary" onclick="doRename('${esc(path)}')" style="width:100%">${t("renameBtn")}</button>
    </div>`);
    setTimeout(()=>{const el=document.getElementById("renameName");el.focus();el.select();el.addEventListener("keydown",e=>{if(e.key==="Enter")doRename(path.replace(/\\/g,"/").replace(/'/g,"\\'"))})},100);
}
async function doRename(path){
    const name=document.getElementById("renameName").value.trim();
    if(!name){toast(t("nameEmpty"));return}
    const r=await fetch("/api/rename",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({path,name})}).then(r=>r.json());
    if(r.ok){closeDialog();toast(t("renameOk"));fetchList(currentPath)}
    else toast(r.error||t("renameFail"));
}

// ═══ Clipboard ═══
async function showClipboard(){
    const data=await fetch("/api/clipboard").then(r=>r.json());
    openDialog(t("clipTitle"),`<div class="modal-form">
        <div class="hint">${t("clipHint")}</div>
        <textarea id="clipText" placeholder="${t("clipPlaceholder")}">${eh(data.text||"")}</textarea>
        ${data.updated?`<div class="hint">${t("clipLastUpdate")}${data.updated}</div>`:""}
        <button class="modal-btn modal-btn-primary" onclick="saveClipboard()" style="width:100%">${t("clipSaveBtn")}</button>
    </div>`);
    setTimeout(()=>document.getElementById("clipText").focus(),100);
}
async function saveClipboard(){
    const text=document.getElementById("clipText").value;
    await fetch("/api/clipboard",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({text})});
    toast(t("clipUpdated"));closeDialog();
}

// ═══ Bookmarks ═══
async function showBookmarks(){
    const bms=await fetch("/api/bookmarks").then(r=>r.json());
    let html;
    if(!bms.length){html=`<div class="bm-empty">&#x2b50; ${t("bmEmpty")}<br><span style="font-size:12px;margin-top:4px;display:block">${t("bmHint")}</span></div>`}
    else{html=`<div class="bookmark-list">${bms.map(b=>`<div class="bm-item" onclick="closeDialog();loadPath('${esc(b.path)}')">
        <div style="flex:1;overflow:hidden"><div class="bm-name">${eh(b.name)}</div><div class="bm-path">${eh(b.path)}</div></div>
        <button class="bm-del" onclick="event.stopPropagation();removeBookmark('${esc(b.path)}')" title="${t('unbookmarked')}">&#x2715;</button>
    </div>`).join("")}</div>`}
    openDialog(t("bmTitle"),html);
}
async function addBookmark(){
    if(!currentPath){toast(t("enterDirFirst"));return}
    const r=await fetch("/api/bookmarks",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({path:currentPath})}).then(r=>r.json());
    if(r.ok)toast(t("bookmarked"));
    else toast(r.error||t("bookmarkFail"));
}
async function removeBookmark(path){
    await fetch("/api/bookmarks",{method:"DELETE",headers:{"Content-Type":"application/json"},body:JSON.stringify({path})});
    toast(t("unbookmarked"));showBookmarks(); // 刷新列表
}

// ═══ Preview & Edit ═══
// 编辑状态变量
let currentPreviewPath="";    // 当前预览的文件路径
let currentPreviewType="";    // 当前预览的文件类型
let currentPreviewContent=""; // 原始文件内容（用于检测是否修改）
let isEditing=false;          // 是否处于编辑模式
let mdNavHistory=[];          // Markdown 文档导航历史栈 [{path, name, type}, ...]

function previewFile(path,name,type){
    const modal=document.getElementById("modal");
    const body=document.getElementById("modalBody");
    const title=document.getElementById("modalTitle");
    const dlBtn=document.getElementById("modalDownload");
    const detail=document.getElementById("modalDetail");
    // 重置编辑状态
    currentPreviewPath=path;currentPreviewType=type;currentPreviewContent="";isEditing=false;
    // 重置按钮显示
    document.getElementById("modalBack").style.display=mdNavHistory.length>0?"":"none";
    document.getElementById("modalEdit").style.display="none";
    document.getElementById("modalSave").style.display="none";
    document.getElementById("modalCancelEdit").style.display="none";
    document.getElementById("modalShare").style.display="none";
    title.textContent=name;dlBtn.onclick=()=>downloadFile(path);
    body.innerHTML='<div class="loading show"><div class="spinner"></div></div>';
    detail.style.display="none";modal.classList.add("show");document.body.style.overflow="hidden";
    const rawUrl=`/api/raw?path=${encodeURIComponent(path)}`;
    // 获取文件详情
    fetch(`/api/info?path=${encodeURIComponent(path)}`).then(r=>r.json()).then(info=>{
        if(!info.error){detail.style.display="flex";detail.innerHTML=`<span class="file-detail-item"><span class="file-detail-label">${t("detailSize")}</span> ${eh(info.size)}</span><span class="file-detail-item"><span class="file-detail-label">${t("detailType")}</span> ${eh(info.ext||info.type)}</span><span class="file-detail-item"><span class="file-detail-label">${t("detailModified")}</span> ${eh(info.modified)}</span>`}
    }).catch(()=>{});
    // 所有文件类型均显示分享按钮
    document.getElementById("modalShare").style.display="";
    switch(type){
        case 'image':body.innerHTML=`<img src="${rawUrl}"/>`;break;
        case 'video':{
            // 检测同目录下是否有同名 .vtt / .srt 字幕文件
            const videoBase=path.replace(/\.[^.]+$/,"");
            const subtitleExts=[".vtt",".srt",".ass"];
            let trackHtml="";
            let trackCount=0;
            const checkSubs=subtitleExts.map(ext=>{
                const subPath=videoBase+ext;
                return fetch(`/api/info?path=${encodeURIComponent(subPath)}`).then(r=>r.json()).then(d=>{
                    if(!d.error){
                        const subUrl=`/api/raw?path=${encodeURIComponent(subPath)}`;
                        // 只给第一个找到的字幕加 default 属性
                        const defAttr=trackCount===0?" default":"";
                        trackCount++;
                        trackHtml+=`<track src="${subUrl}" kind="subtitles" label="${ext.slice(1).toUpperCase()}"${defAttr}>`;
                    }
                }).catch(()=>{});
            });
            Promise.all(checkSubs).then(()=>{
                body.innerHTML=`<video controls autoplay><source src="${rawUrl}">${trackHtml}</video>`;
            });
            break;
        }
        case 'audio':body.innerHTML=`<audio controls autoplay><source src="${rawUrl}"></audio>`;break;
        case 'pdf':
            if(/Mobi|Android|iPhone|iPad|iPod/i.test(navigator.userAgent)){
                body.innerHTML=`<div class="preview-error" style="padding:40px"><div class="icon">&#x1f4d5;</div><div style="margin-bottom:16px">${t("pdfMobileHint")}</div><div style="display:flex;gap:12px;justify-content:center;flex-wrap:wrap"><button class="modal-btn modal-btn-primary" onclick="window.open('${rawUrl}','_blank')">&#x1f4c4; ${t("openInBrowser")}</button><button class="modal-btn modal-btn-close" onclick="downloadFile('${esc(path)}')">&#x2b07; ${t("downloadFileBtn")}</button></div></div>`;
            }else{
                body.innerHTML=`<iframe src="${rawUrl}"></iframe>`;
            }
            break;
        case 'markdown':fetch(`/api/file?path=${encodeURIComponent(path)}`).then(r=>r.json()).then(d=>{
            if(d.error){body.innerHTML=`<div class="preview-error"><div class="icon">&#x26a0;&#xfe0f;</div><div>${eh(d.error)}</div></div>`}
            else{
                currentPreviewContent=d.content;
                document.getElementById("modalEdit").style.display=isReadOnly?"none":"";
                try{
                    if(typeof marked!=='undefined'){
                        body.innerHTML=`<div class="md-body">${sanitizeHTML(marked.parse(d.content))}</div>`;
                        bindMdLinks(body, path);
                        try{renderMermaidBlocks(body)}catch(me){}
                    }
                    else body.innerHTML=`<pre>${eh(d.content)}</pre>`;
                }catch(e){body.innerHTML=`<pre>${eh(d.content)}</pre>`}
            }
        }).catch(()=>{body.innerHTML=`<div class="preview-error"><div class="icon">&#x274c;</div><div>${t("previewFail")}</div></div>`});break;
        case 'text':fetch(`/api/file?path=${encodeURIComponent(path)}`).then(r=>r.json()).then(d=>{
            if(d.error){body.innerHTML=`<div class="preview-error"><div class="icon">&#x26a0;&#xfe0f;</div><div>${eh(d.error)}</div></div>`}
            else{
                currentPreviewContent=d.content;
                document.getElementById("modalEdit").style.display=isReadOnly?"none":"";
                body.innerHTML=`<pre>${eh(d.content)}</pre>`;
            }
        }).catch(()=>{body.innerHTML=`<div class="preview-error"><div class="icon">&#x274c;</div><div>${t("previewFail")}</div></div>`});break;
        case 'archive':
            // ZIP 文件：显示内容列表（仅 .zip 支持预览）
            if(path.toLowerCase().endsWith('.zip')){
                fetch(`/api/zip-list?path=${encodeURIComponent(path)}`).then(r=>r.json()).then(d=>{
                    if(d.error){body.innerHTML=`<div class="preview-error"><div class="icon">&#x26a0;&#xfe0f;</div><div>${eh(d.error)}</div></div>`}
                    else{
                        const rows=d.items.map(it=>`<tr><td style="padding:4px 8px">${eh(it.name)}</td><td style="padding:4px 8px;color:var(--text2);text-align:right">${it.is_dir?"--":it.size}</td></tr>`).join("");
                        body.innerHTML=`<div style="padding:16px"><div style="margin-bottom:12px;display:flex;align-items:center;justify-content:space-between"><span style="color:var(--text2);font-size:13px">${d.count} ${t("zipEntries")}</span><button class="modal-btn modal-btn-primary" onclick="extractZip('${esc(path)}')">&#x1f4e6; ${t("zipExtractHere")}</button></div><table style="width:100%;border-collapse:collapse;font-size:13px"><thead><tr style="border-bottom:1px solid var(--border)"><th style="padding:4px 8px;text-align:left">${t("zipFilename")}</th><th style="padding:4px 8px;text-align:right">${t("detailSize")}</th></tr></thead><tbody>${rows}</tbody></table></div>`;
                    }
                }).catch(()=>{body.innerHTML=`<div class="preview-error"><div class="icon">&#x274c;</div><div>${t("previewFail")}</div></div>`});
            } else {
                body.innerHTML=`<div class="preview-error"><div class="icon">&#x1f4c4;</div><div>${t("previewArchiveUnsupported")}</div><div style="margin-top:12px"><button class="modal-btn modal-btn-primary" onclick="downloadFile('${esc(path)}')">${t("downloadFileBtn")}</button></div></div>`;
            }
            break;
        case 'office':
            (async()=>{
                const ext=path.split(".").pop().toLowerCase();
                // DOCX：使用 mammoth.js 转为 HTML
                if(ext==="docx"&&typeof mammoth!=="undefined"){
                    try{
                        const resp=await fetch(rawUrl);
                        const buf=await resp.arrayBuffer();
                        const result=await mammoth.convertToHtml({arrayBuffer:buf});
                        body.innerHTML=`<div class="md-body" style="padding:20px">${sanitizeHTML(result.value)}</div>`;
                    }catch(e){body.innerHTML=`<div class="preview-error"><div class="icon">&#x26a0;&#xfe0f;</div><div>${t("previewDocxFail")}${eh(e.message)}</div><div style="margin-top:12px"><button class="modal-btn modal-btn-primary" onclick="downloadFile('${esc(path)}')">${t("downloadFileBtn")}</button></div></div>`}
                // XLSX / XLS：使用 SheetJS 渲染为表格
                }else if((ext==="xlsx"||ext==="xls")&&typeof XLSX!=="undefined"){
                    try{
                        const resp=await fetch(rawUrl);
                        const buf=await resp.arrayBuffer();
                        const wb=XLSX.read(new Uint8Array(buf),{type:"array"});
                        let html='<div style="padding:12px;overflow-x:auto">';
                        for(const name of wb.SheetNames){
                            const ws=wb.Sheets[name];
                            const tbl=XLSX.utils.sheet_to_html(ws,{editable:false});
                            html+=`<h3 style="margin:16px 0 8px;color:var(--text)">${eh(name)}</h3>${tbl}`;
                        }
                        html+='</div>';
                        body.innerHTML=sanitizeHTML(html);
                        body.querySelectorAll("table").forEach(tbl=>{tbl.style.cssText="width:100%;border-collapse:collapse;font-size:13px";tbl.querySelectorAll("td,th").forEach(c=>{c.style.cssText="border:1px solid var(--border);padding:4px 8px"})});
                    }catch(e){body.innerHTML=`<div class="preview-error"><div class="icon">&#x26a0;&#xfe0f;</div><div>${t("previewXlsFail")}${eh(e.message)}</div><div style="margin-top:12px"><button class="modal-btn modal-btn-primary" onclick="downloadFile('${esc(path)}')">${t("downloadFileBtn")}</button></div></div>`}
                }else{
                    body.innerHTML=`<div class="preview-error"><div class="icon">&#x1f4c4;</div><div>${t("previewOfficeUnsupported")}</div><div style="margin-top:12px"><button class="modal-btn modal-btn-primary" onclick="downloadFile('${esc(path)}')">${t("downloadFileBtn")}</button></div></div>`;
                }
            })().catch(e=>{body.innerHTML=`<div class="preview-error"><div class="icon">&#x274c;</div><div>${t("previewFail")}: ${eh(e.message||"")}</div><div style="margin-top:12px"><button class="modal-btn modal-btn-primary" onclick="downloadFile('${esc(path)}')">${t("downloadFileBtn")}</button></div></div>`});
            break;
        default:body.innerHTML=`<div class="preview-error"><div class="icon">&#x1f4c4;</div><div>${t("previewUnsupported")}</div><div style="margin-top:12px"><button class="modal-btn modal-btn-primary" onclick="downloadFile('${esc(path)}')">${t("downloadFileBtn")}</button></div></div>`;
    }
}

/**
 * 切换到编辑模式：将预览内容替换为可编辑的文本框。
 */
function toggleEdit(){
    if(isEditing)return;
    isEditing=true;
    const body=document.getElementById("modalBody");
    // 创建编辑器 UI
    body.innerHTML=`<div class="editor-wrap">
        <textarea class="editor-textarea" id="editorArea" spellcheck="false">${eh(currentPreviewContent)}</textarea>
        <div class="editor-status"><span id="editorModified"></span><span>${t("editorHint")}</span></div>
    </div>`;
    // 按钮切换: 隐藏"编辑"，显示"保存"和"取消编辑"
    document.getElementById("modalEdit").style.display="none";
    document.getElementById("modalSave").style.display="";
    document.getElementById("modalCancelEdit").style.display="";
    // 聚焦编辑器
    const area=document.getElementById("editorArea");
    area.focus();
    // 监听内容变化
    area.addEventListener("input",()=>{
        const modified=area.value!==currentPreviewContent;
        document.getElementById("editorModified").innerHTML=modified?'<span class="modified">'+t("editorModified")+'</span>':'';
    });
    // Tab 键插入制表符（而非跳转焦点）
    area.addEventListener("keydown",(e)=>{
        if(e.key==="Tab"){
            e.preventDefault();
            const start=area.selectionStart;
            const end=area.selectionEnd;
            area.value=area.value.substring(0,start)+"\t"+area.value.substring(end);
            area.selectionStart=area.selectionEnd=start+1;
            area.dispatchEvent(new Event("input"));
        }
        // Ctrl+S / Cmd+S 保存
        if((e.ctrlKey||e.metaKey)&&e.key==="s"){
            e.preventDefault();
            saveFile();
        }
    });
}

/**
 * 保存文件：将编辑器内容发送到后端写入磁盘。
 */
async function saveFile(){
    const area=document.getElementById("editorArea");
    if(!area){toast(t("editorNotOpen"));return}
    const content=area.value;
    toast(t("saving"));
    try{
        const r=await fetch("/api/save-file",{
            method:"POST",
            headers:{"Content-Type":"application/json"},
            body:JSON.stringify({path:currentPreviewPath,content})
        }).then(r=>r.json());
        if(r.ok){
            currentPreviewContent=content;  // 更新原始内容
            document.getElementById("editorModified").innerHTML='';
            toast(`${t("saved")} (${r.size})`);
        }else{
            toast(r.error||t("saveFail"));
        }
    }catch(e){toast(t("saveNetErr"))}
}

/**
 * 取消编辑：回到预览模式（如果有未保存的修改会提示确认）。
 */
function cancelEdit(){
    const area=document.getElementById("editorArea");
    if(area&&area.value!==currentPreviewContent){
        if(!confirm(t("unsavedConfirm")))return;
    }
    isEditing=false;
    // 重新渲染预览
    const body=document.getElementById("modalBody");
    if(currentPreviewType==='markdown'&&typeof marked!=='undefined'){
        body.innerHTML=`<div class="md-body">${sanitizeHTML(marked.parse(currentPreviewContent))}</div>`;
    }else{
        body.innerHTML=`<pre>${eh(currentPreviewContent)}</pre>`;
    }
    // 按钮切换回来
    document.getElementById("modalEdit").style.display="";
    document.getElementById("modalSave").style.display="none";
    document.getElementById("modalCancelEdit").style.display="none";
}

function closeModal(keepHistory){
    // 如果正在编辑且有未保存修改，提示确认
    if(isEditing){
        const area=document.getElementById("editorArea");
        if(area&&area.value!==currentPreviewContent){
            if(!confirm(t("unsavedCloseConfirm")))return;
        }
    }
    isEditing=false;
    if(!keepHistory) mdNavHistory=[];
    document.getElementById("modal").classList.remove("show");document.body.style.overflow="";
    const b=document.getElementById("modalBody");b.querySelectorAll("video,audio").forEach(el=>{el.pause();el.src=""});b.innerHTML="";
    document.getElementById("modalDetail").style.display="none";
    document.getElementById("modalBack").style.display="none";
    document.getElementById("modalEdit").style.display="none";
    document.getElementById("modalSave").style.display="none";
    document.getElementById("modalCancelEdit").style.display="none";
}
document.addEventListener("keydown",e=>{if(e.key==="Escape"){closeModal();closeDialog()}});

// ═══ Dialog ═══
function openDialog(title,html){
    document.getElementById("dialogTitle").innerHTML=title;
    document.getElementById("dialogBody").innerHTML=html;
    document.getElementById("dialog").classList.add("show");
}
function closeDialog(){document.getElementById("dialog").classList.remove("show")}

// ═══ Download ═══
function downloadFile(path){const a=document.createElement("a");a.href=`/api/download?path=${encodeURIComponent(path)}`;a.download="";document.body.appendChild(a);a.click();a.remove()}

// ═══ Toast ═══
function toast(msg,ms=2500){const el=document.getElementById("toast");el.textContent=msg;el.classList.add("show");clearTimeout(el._t);el._t=setTimeout(()=>el.classList.remove("show"),ms)}

// ═══ Markdown 内链接拦截 ═══

/**
 * 解析相对路径：基于当前文件所在目录，将相对路径转为绝对路径。
 * 例如：currentFile="E:/project/README.md", href="docs/guide.md"
 *       → "E:/project/docs/guide.md"
 *
 * 支持 "../" 上级目录引用。
 */
function resolveRelativePath(currentFilePath, href){
    // 获取当前文件所在的目录
    const dir = currentFilePath.replace(/\\/g,"/").replace(/\/[^/]*$/,"");
    // 拼接相对路径
    const parts = (dir + "/" + href).split("/");
    // 处理 ".." 和 "."
    const resolved = [];
    for(const p of parts){
        if(p === "." || p === "") continue;
        if(p === "..") resolved.pop();
        else resolved.push(p);
    }
    let result = resolved.join("/");
    // Unix/macOS 绝对路径以 "/" 开头，split 后首个空串被跳过，需补回
    if(currentFilePath.replace(/\\/g,"/").startsWith("/")) {
        result = "/" + result;
    }
    return result;
}

/**
 * 判断一个 href 是否是外部链接（http/https/mailto 等）。
 */
function isExternalLink(href){
    return /^(https?:|mailto:|tel:|ftp:)/.test(href);
}

/**
 * 为 Markdown 渲染后的容器绑定链接点击事件。
 * 拦截相对路径的链接，解析为文件系统路径并打开预览。
 *
 * @param {Element} container - 包含渲染后 HTML 的 DOM 容器
 * @param {string} currentFilePath - 当前正在预览的文件的完整路径
 */
function bindMdLinks(container, currentFilePath){
    const mdBody = container.querySelector(".md-body");
    if(!mdBody) return;

    // ── 核心思路：移除所有内部链接的 href，改存到 data-href ──
    // 这样浏览器就完全不可能导航到新页面
    mdBody.querySelectorAll("a").forEach(a => {
        const href = a.getAttribute("href");
        if(!href) return;

        if(isExternalLink(href)){
            // 外部链接：保留 href，新标签打开
            a.setAttribute("target","_blank");
            a.setAttribute("rel","noopener noreferrer");
        } else {
            // 内部链接（锚点或相对路径）：移除 href，存到 data-href
            a.setAttribute("data-href", href);
            a.removeAttribute("href");
            a.style.cursor = "pointer";
            a.style.color = "var(--accent2)";
            a.style.textDecoration = "none";
            // 直接用 onclick（最可靠的拦截方式）
            a.onclick = function(e){
                e.preventDefault();
                e.stopPropagation();
                const link = this.getAttribute("data-href");
                handleMdLinkClick(link, mdBody, currentFilePath);
                return false;
            };
        }
    });
}

/**
 * 处理 Markdown 内部链接的点击。
 * 根据链接格式分三种情况处理。
 */
function handleMdLinkClick(href, mdBody, currentFilePath){
    // 解析链接的文件部分和锚点部分
    const hashIndex = href.indexOf("#");
    const filePart = hashIndex >= 0 ? href.slice(0, hashIndex) : href;
    const anchorPart = hashIndex >= 0 ? href.slice(hashIndex + 1) : "";

    // 情况 1: 纯锚点链接（如 #chapter-1），在当前文档内滚动
    if(!filePart && anchorPart){
        scrollToAnchor(mdBody, anchorPart);
        return;
    }

    // 情况 2: 文件链接（如 docs/guide.md 或 other.md#section）
    if(filePart){
        // marked.js 会对非 ASCII 字符（如中文）进行 URL 编码，需要先解码还原为原始路径
        const decodedFilePart = decodeURIComponent(filePart);
        const fullPath = resolveRelativePath(currentFilePath, decodedFilePart);
        const fileName = decodedFilePart.split("/").pop();
        const fileType = getFileTypeFromName(fileName);
        // 将当前文档压入导航历史栈，支持返回
        mdNavHistory.push({path:currentFilePath, name:document.getElementById("modalTitle").textContent, type:currentPreviewType});
        closeModal(true);
        setTimeout(() => previewFile(fullPath, fileName, fileType), 100);
    }
}

/**
 * 返回上一个 Markdown 文档（从导航历史栈弹出）。
 */
function mdGoBack(){
    if(mdNavHistory.length===0) return;
    const prev=mdNavHistory.pop();
    closeModal(true);
    setTimeout(()=>previewFile(prev.path,prev.name,prev.type),100);
}

/**
 * 在 Markdown 预览容器内滚动到指定锚点位置。
 * 支持多种匹配策略以兼容中文标题和 marked.js 的 ID 生成规则。
 *
 * marked.js 的标题 ID 生成规则:
 *   - 转为小写
 *   - 空格替换为连字符 -
 *   - 移除非字母数字和连字符以外的字符（但保留中文）
 *   例: "C++ 语言概述" → id="c-语言概述"
 *
 * @param {Element} mdBody - .md-body 容器元素
 * @param {string} anchor  - 锚点值（不含 #）
 */
function scrollToAnchor(mdBody, anchor){
    const decoded = decodeURIComponent(anchor);
    const lowerAnchor = decoded.toLowerCase();

    // 策略 1: 精确匹配 id（最常见的情况）
    let target = mdBody.querySelector(`[id="${CSS.escape(decoded)}"]`)
              || mdBody.querySelector(`[id="${CSS.escape(lowerAnchor)}"]`);

    // 策略 2: 遍历所有标题，用多种方式模糊匹配
    if(!target){
        const headings = mdBody.querySelectorAll("h1,h2,h3,h4,h5,h6");
        for(const h of headings){
            const hId = (h.id || "").toLowerCase();
            // 将标题文本按 marked.js 规则转为 id 格式
            const hText = h.textContent.trim().toLowerCase()
                .replace(/\s+/g, "-")
                .replace(/[^\w\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af-]/g, "");

            if(hId === lowerAnchor || hText === lowerAnchor
               || hId.includes(lowerAnchor) || lowerAnchor.includes(hId)){
                target = h;
                break;
            }
        }
    }

    // 策略 3: 如果锚点是中文文字，直接搜索标题文本内容
    if(!target){
        const headings = mdBody.querySelectorAll("h1,h2,h3,h4,h5,h6");
        const searchText = decoded.replace(/-/g, " ").toLowerCase();
        for(const h of headings){
            if(h.textContent.toLowerCase().includes(searchText)){
                target = h;
                break;
            }
        }
    }

    if(target){
        // 滚动弹窗内容区到目标位置
        target.scrollIntoView({behavior:"smooth", block:"start"});
    }
}

/**
 * 根据文件名判断文件类型（前端版本，与后端 get_file_type 对应）。
 */
function getFileTypeFromName(name){
    const ext = (name.match(/\.[^.]+$/) || [""])[0].toLowerCase();
    const map = {
        image: ['.jpg','.jpeg','.png','.gif','.bmp','.webp','.svg','.ico','.tiff','.tif'],
        video: ['.mp4','.webm','.mkv','.avi','.mov','.flv','.wmv','.m4v','.3gp'],
        audio: ['.mp3','.wav','.ogg','.flac','.aac','.wma','.m4a','.opus'],
        markdown: ['.md','.markdown','.mdown','.mkd'],
        pdf: ['.pdf'],
        archive: ['.zip','.rar','.7z','.tar','.gz','.bz2','.xz','.zst','.tgz'],
        office: ['.doc','.docx','.xls','.xlsx','.ppt','.pptx','.odt','.ods','.odp','.rtf'],
        font: ['.ttf','.otf','.woff','.woff2'],
    };
    for(const [type, exts] of Object.entries(map)){
        if(exts.includes(ext)) return type;
    }
    // 与后端 get_file_type() 保持一致的完整文本扩展名列表
    const textExts = [
        '.txt','.text','.log','.csv','.tsv','.nfo',
        '.html','.htm','.css','.js','.ts','.jsx','.tsx','.vue','.svelte',
        '.scss','.sass','.less','.styl','.astro',
        '.ejs','.hbs','.pug','.njk','.liquid','.twig','.wxml','.wxss',
        '.mjs','.cjs','.mts','.cts',
        '.coffee','.litcoffee','.mdx','.svx',
        '.erb','.haml','.slim','.j2','.jinja','.jinja2','.tmpl','.tpl','.mustache',
        '.jsp','.asp','.aspx','.phtml',
        '.json','.jsonc','.json5','.ndjson','.jsonl','.geojson',
        '.xml','.yaml','.yml','.toml','.ini','.cfg','.conf','.proto','.avsc',
        '.jsonnet','.libsonnet','.dhall',
        '.py','.pyw','.pyi',
        '.java','.kt','.kts','.scala','.groovy','.gradle',
        '.c','.h','.cpp','.hpp','.cc','.cxx','.hxx','.m','.mm',
        '.cs','.fs','.fsx','.vb',
        '.go','.rs','.swift','.dart','.zig','.nim','.v','.d',
        '.rb','.php','.pl','.pm','.lua','.r','.jl',
        '.sql','.prisma',
        '.hs','.lhs','.ml','.mli','.ex','.exs','.erl','.hrl',
        '.clj','.cljs','.lisp','.el','.rkt','.tcl','.cr','.hx',
        '.elm','.purs','.res','.resi','.re','.rei',
        '.scm','.ss','.sml','.sig','.idr','.agda','.lean',
        '.raku','.rakumod',
        '.f','.f90','.f95','.f03','.f08','.for','.fpp',
        '.pas','.pp','.lpr','.dpr',
        '.cob','.cbl','.ada','.adb','.ads',
        '.sol','.vy',
        '.glsl','.hlsl','.wgsl','.metal','.vert','.frag','.comp','.cu','.cuh',
        '.sh','.bash','.zsh','.fish','.csh','.ksh','.bat','.cmd','.ps1','.psm1',
        '.ahk','.au3','.awk','.sed','.applescript','.nix',
        '.reg','.inf','.vbs','.vba','.wsf',
        '.plist','.strings','.entitlements','.pbxproj',
        '.desktop','.service','.timer','.socket','.mount',
        '.tf','.tfvars','.hcl','.properties','.sbt','.cmake','.mk','.mak','.cabal','.gemspec','.podspec',
        '.csproj','.vbproj','.fsproj','.sln','.vcxproj','.spec',
        '.htaccess','.nginx','.graphql','.gql',
        '.rst','.asciidoc','.adoc','.tex','.latex','.bib','.sty','.cls',
        '.dtd','.xsd','.xsl','.xslt',
        '.org','.rmd','.rnw','.typ',
        '.srt','.vtt','.ass','.ssa','.sub','.lrc',
        '.m3u','.m3u8','.cue','.ics','.vcf',
        '.pem','.crt','.csr','.key','.pub','.cer',
        '.diff','.patch','.asm','.s','.dockerfile'];
    if(textExts.includes(ext)) return 'text';
    // 无扩展名文件名匹配
    const n = name.split('/').pop().split('\\').pop().toLowerCase();
    const textNames = ['makefile','dockerfile','containerfile','vagrantfile','gemfile','rakefile',
        'procfile','brewfile','justfile','cmakelists.txt','jenkinsfile','snakefile',
        'sconscript','sconstruct','podfile','cartfile','fastfile','appfile','dangerfile',
        'guardfile','berksfile','capfile','thorfile','earthfile','tiltfile',
        'build','build.bazel','workspace','workspace.bazel','buck',
        'go.mod','go.sum','pipfile',
        'license','licence','authors','contributors','changelog',
        'readme','todo','copying','install','news','thanks',
        '.gitignore','.gitattributes','.gitmodules','.gitconfig','.gitkeep','.mailmap',
        '.dockerignore','.dockerfile',
        '.prettierignore','.eslintignore','.helmignore','.slugignore',
        '.editorconfig','.prettierrc','.eslintrc','.stylelintrc',
        '.babelrc','.npmrc','.yarnrc','.nvmrc','.pylintrc','.flake8',
        '.vimrc','.viminfo','.gvimrc','.nanorc','.emacs',
        '.clang-format','.clang-tidy','.yamllint','.markdownlint','.rubocop',
        '.ruby-version','.python-version','.node-version','.java-version','.tool-versions',
        '.env','.env.local','.env.development','.env.production','.env.test','.env.staging','.env.example',
        '.profile','.login','.logout',
        '.bashrc','.bash_profile','.bash_login','.bash_logout','.bash_aliases',
        '.zshrc','.zshenv','.zprofile','.zlogin','.zlogout',
        '.cshrc','.tcshrc','.inputrc',
        '.bash_history','.zsh_history','.history',
        '.wgetrc','.curlrc','.screenrc','.netrc','.htpasswd','.condarc','.gemrc'];
    if(textNames.includes(n)) return 'text';
    return 'other';
}

// ═══ Utils ═══
// CSRF 保护: 包装全局 fetch，为所有 POST 请求自动附加 X-Requested-With 头
const _origFetch=window.fetch;window.fetch=function(url,opts){if(opts&&opts.method&&["POST","DELETE","PUT","PATCH"].includes(opts.method.toUpperCase())){opts.headers=opts.headers||{};if(opts.headers instanceof Headers){opts.headers.set("X-Requested-With","XMLHttpRequest")}else if(Array.isArray(opts.headers)){opts.headers.push(["X-Requested-With","XMLHttpRequest"])}else{opts.headers["X-Requested-With"]="XMLHttpRequest"}}return _origFetch.call(this,url,opts)};
function eh(s){const d=document.createElement("div");d.textContent=s;return d.innerHTML}
function esc(s){return s.replace(/\\/g,"/").replace(/'/g,"\\'").replace(/`/g,"\\`").replace(/"/g,"&quot;").replace(/\n/g,"\\n").replace(/\r/g,"\\r")}
function sanitizeHTML(html){return typeof DOMPurify!=='undefined'?DOMPurify.sanitize(html,{ADD_TAGS:['use'],ADD_ATTR:['target','xlink:href']}):eh(html)}
function xhrUpload(fd,onProgress,abortSignal){return new Promise((resolve,reject)=>{const xhr=new XMLHttpRequest();xhr.open("POST","/api/upload");xhr.setRequestHeader("X-Requested-With","XMLHttpRequest");if(onProgress)xhr.upload.addEventListener("progress",e=>{if(e.lengthComputable)onProgress(Math.round(e.loaded*100/e.total),e.loaded,e.total)});xhr.onload=()=>{try{resolve(JSON.parse(xhr.responseText))}catch(e){reject(e)}};xhr.onerror=()=>reject(new Error("upload failed"));xhr.onabort=()=>reject(new DOMException("Aborted","AbortError"));if(abortSignal){if(abortSignal.aborted){reject(new DOMException("Aborted","AbortError"));return}abortSignal.addEventListener("abort",()=>xhr.abort())}xhr.send(fd)})}
function xhrPost(url,fd,onProgress,abortSignal){return new Promise((resolve,reject)=>{const xhr=new XMLHttpRequest();xhr.open("POST",url);xhr.setRequestHeader("X-Requested-With","XMLHttpRequest");if(onProgress)xhr.upload.addEventListener("progress",e=>{if(e.lengthComputable)onProgress(e.loaded,e.total)});xhr.onload=()=>{try{resolve(JSON.parse(xhr.responseText))}catch(e){reject(e)}};xhr.onerror=()=>reject(new Error("request failed"));xhr.onabort=()=>reject(new DOMException("Aborted","AbortError"));if(abortSignal){if(abortSignal.aborted){reject(new DOMException("Aborted","AbortError"));return}abortSignal.addEventListener("abort",()=>xhr.abort())}xhr.send(fd)})}
function formatBytes(b){if(b<1024)return b+" B";if(b<1048576)return(b/1024).toFixed(1)+" KB";if(b<1073741824)return(b/1048576).toFixed(1)+" MB";return(b/1073741824).toFixed(2)+" GB"}
// ═══ Stream Operation (NDJSON 流式进度) ═══
async function streamOp(url,body,onProgress){
    body.stream=true;
    const resp=await fetch(url,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(body)});
    const ct=resp.headers.get("content-type")||"";
    if(ct.includes("application/json")){return await resp.json()}
    const reader=resp.body.getReader();const dec=new TextDecoder();let buf="";let result=null;
    while(true){
        const{done,value}=await reader.read();if(done)break;
        buf+=dec.decode(value,{stream:true});
        const lines=buf.split("\n");buf=lines.pop();
        for(const ln of lines){if(!ln.trim())continue;const d=JSON.parse(ln);
            if(d.ok!==undefined||d.error!==undefined||d.conflict!==undefined)result=d;
            else if(onProgress)onProgress(d);
        }
    }
    if(buf.trim()){try{const d=JSON.parse(buf);if(d.ok!==undefined||d.error!==undefined||d.conflict!==undefined)result=d;else if(onProgress)onProgress(d)}catch(e){}}
    return result||{ok:true};
}
function showOpProgress(title,isBytes){
    openDialog(title,`<div class="modal-form uq-wrap">
        <div class="upload-progress-bar"><div class="upload-progress-fill" id="opBar" style="width:0%"></div></div>
        <div class="upload-progress-text" id="opPct">0%</div>
        <div id="opFile" style="font-size:13px;color:var(--text2);margin-top:4px;word-break:break-all;text-align:center;min-height:18px"></div>
    </div>`);
    window._opIsBytes=isBytes;
}
function updateOpProgress(d){
    const bar=document.getElementById("opBar");const pct=document.getElementById("opPct");const fn=document.getElementById("opFile");
    if(!bar)return;
    const percent=d.t>0?Math.round(d.p*100/d.t):0;
    bar.style.width=percent+"%";
    if(window._opIsBytes)pct.textContent=`${percent}% (${formatBytes(d.p)} / ${formatBytes(d.t)})`;
    else pct.textContent=`${d.p} / ${d.t}`;
    if(d.f&&fn)fn.textContent=d.f;
}

// ═══ Theme ═══
let currentTheme=localStorage.getItem("fb_theme")||"dark";
(function initTheme(){
    document.documentElement.setAttribute("data-theme",currentTheme);
    const btn=document.getElementById("themeBtn");
    if(btn)btn.textContent=currentTheme==="dark"?"☀":"🌙";
})();
function toggleTheme(){
    currentTheme=currentTheme==="dark"?"light":"dark";
    document.documentElement.setAttribute("data-theme",currentTheme);
    localStorage.setItem("fb_theme",currentTheme);
    document.getElementById("themeBtn").textContent=currentTheme==="dark"?"☀":"🌙";
}

// ═══ Language / i18n ═══
const I18N={
    zh:{upload:"⬆ 上传",mkdir:"📁+ 文件夹",mkfile:"📄+ 文件",select:"☐ 多选",selectAll:"☑ 全选",
        batchDl:"📦 打包下载",batchDel2:"🗑 批量删除",batchMove:"✂ 批量移动",batchCopy:"📋 批量复制",
        clipboard:"📋 剪贴板",bookmarks:"⭐ 收藏",logout:"🚪 登出",
        loginHint:"请输入访问密码",loginBtn:"登录",loginFail:"登录失败",
        errWrongPwd:"密码错误",errRateLimit:"尝试次数过多，请稍后再试",errInvalidReq:"请求无效",
        searchPh:"搜索文件名或内容...",searchName:"文件名搜索",searchContent:"内容搜索",
        sortLabel:"排序:",sortName:"名称",sortSize:"大小",sortCtime:"创建时间",sortMtime:"修改时间",
        filterLabel:"筛选:",filterAll:"全部类型",filterImage:"🖼 图片",filterVideo:"🎬 视频",
        filterAudio:"🎵 音频",filterText:"📝 文本/代码",filterArchive:"📦 压缩包",
        filterFont:"🔤 字体",filterOther:"📄 其他",filterExtPh:"后缀 如 .py,.md",filterClear:"清除筛选",
        statusReady:"就绪",dropHint:"📤 松开鼠标上传文件",breadcrumbRoot:"🏠 根",
        regexOff:"普通搜索（点击开启正则）",regexOn:"已启用正则搜索（点击关闭）",
        modalBack:"← 返回上级文档",modalEdit:"✏ 编辑",modalSave:"💾 保存",modalCancelEdit:"取消编辑",modalDownload:"下载",modalShare:"🔗 分享",modalClose:"关闭",
        actRename:"重命名",actDelete:"删除",actDownload:"下载",actCopy:"复制",actMove:"移动",actDownloadFolder:"下载文件夹",
        statusItems:" 项 — ",statusFiltered:"(已筛选)",statusDrives:"个磁盘",emptyFolder:"空文件夹",loadFail:"加载失败",createdPrefix:"创建:",
        selectFirst:"请先选择文件",packing:"正在打包...",packFail:"打包失败",dlStarted:"下载已开始",packDlFail:"打包下载失败",packingDl:"打包下载中",
        enterDirFirst:"请先进入一个目录",selectFiles:"请选择文件",enterName:"请输入名称",enterFilename:"请输入文件名",
        extHint:"建议包含扩展名，如 .txt、.md、.py",nameEmpty:"名称不能为空",
        createOk:"创建成功",createFail:"创建失败",fileCreated:"文件已创建: ",deleted:"已删除",deleteFail:"删除失败",
        renameOk:"重命名成功",renameFail:"重命名失败",copyOk:"复制成功",copyFail:"复制失败",moveOk:"移动成功",moveFail:"移动失败",
        opCopying:"复制中...",opMoving:"移动中...",opDeleting:"删除中...",opExtracting:"解压中...",
        clipUpdated:"剪贴板已更新",bookmarked:"已收藏",bookmarkFail:"收藏失败",unbookmarked:"已取消收藏",
        uploadUploading:"上传中...",uploadFail:"上传失败",uploaded:"上传成功: ",
        noPreviewFile:"没有正在预览的文件",shareFail:"生成分享链接失败",linkCopied:"链接已复制",
        saving:"保存中...",saved:"已保存",saveFail:"保存失败",saveNetErr:"保存失败: 网络错误",editorNotOpen:"编辑器未打开",
        extractOk:"解压成功",extractFail:"解压失败",dlFolderPacking:"正在打包下载文件夹...",
        dragUpload:"已上传",dragUploadFail:"部分文件上传失败: ",dragUploadErr:"上传失败",dragUploadSkip:"跳过无法访问的文件: ",
        searchNoResult:"未找到匹配结果",searchFound:"找到",searchResults:"个结果",searchScanned:"扫描",searchFiles:"个文件",searchFail:"搜索失败",
        batchDelTitle:"批量删除",batchDelConfirm:"确定要删除选中的",batchDelUnit:"个文件吗？",batchDelIrreversible:"此操作不可撤销",
        batchDelBtn:"确认删除",batchDelDone:"已删除",batchFail:"个失败",
        batchMoveTitle:"批量移动",batchMoveUnit:"个文件",batchMoveDone:"已移动",batchCopyTitle:"批量复制",batchCopyDone:"已复制",
        uploadTitle:"上传文件",uploadTarget:"目标目录: ",uploadHint:"支持多选，无大小限制",uploadBtn:"开始上传",uploadChoose:"选择文件",uploadChooseFolder:"选择文件夹",uploadNoFile:"未选择任何文件",uploadFileCount:"已选择 {n} 个文件",uploadFolderCount:"已选择文件夹，共 {n} 个文件",uploadFolderHint:"支持上传整个文件夹（包含所有子目录）",uploadReadingFolder:"正在读取文件夹...",
        uploadOkCount:"成功",uploadFailCount:"失败: ",uploadDone:"成功上传",uploadDoneUnit:"个文件",
        uploadPauseBtn:"暂停",uploadResumeBtn:"继续",uploadCancelBtn:"取消",uploadCancelled:"已取消上传",uploadSkippedN:"跳过",uploadCloseBtn:"关闭",
        mkdirTitle:"新建文件夹",mkdirIn:"在",mkdirCreate:"下创建",mkdirPlaceholder:"文件夹名称",mkdirBtn:"创建",
        mkfileTitle:"📄 新建文件",mkfilePlaceholder:"文件名，如: notes.md、config.json、script.py",
        mkfileHint:"请输入完整文件名（含扩展名），如 readme.md、data.csv、app.py",
        mkfileContentLabel:"初始内容（可选）",mkfileContentPh:"可以留空，也可以输入初始内容...",mkfileBtn:"创建文件",
        deleteTitle:"确认删除",deleteMsg:"确定要删除",deleteAsk:"吗？",deleteIrreversible:"此操作不可撤销",deleteBtn:"确认删除",
        deleteRecTitle:"⚠ 确认递归删除",deleteNotEmpty:"不为空！",
        deleteRecWarn:"将递归删除文件夹内的所有内容，此操作不可撤销！",deleteRecBtn:"🔥 强制删除全部内容",
        renameTitle:"重命名",renameCurrent:"当前名称: ",renameBtn:"确认",
        clipTitle:"📋 共享剪贴板",clipHint:"在手机和电脑之间共享文本。粘贴到这里，另一端即可获取。",
        clipPlaceholder:"输入要共享的文本...",clipLastUpdate:"上次更新: ",clipSaveBtn:"保存",
        bmTitle:"⭐ 收藏夹",bmEmpty:"还没有收藏",bmHint:"进入目录后点击 +⭐ 收藏",
        shareTitle:"分享链接",shareHint:"任何人无需登录即可下载：",shareCopyBtn:"📋 复制链接",
        shareExpireLabel:"选择链接有效期：",shareCreateBtn:"生成分享链接",
        shareExpire5m:"5 分钟",shareExpire30m:"30 分钟",shareExpire1h:"1 小时",shareExpire6h:"6 小时",shareExpire12h:"12 小时",shareExpire24h:"24 小时",
        pickerHint:"点击文件夹进入，在目标目录点击下方按钮确认",pickerConfirm:"确认选择当前目录",
        pickerLoading:"加载中...",pickerFail:"加载失败",pickerNoSub:"无子目录",pickerCopy:"复制",pickerMove:"移动",
        pickerPathPh:"目标目录路径",pickerGo:"跳转",
        editorModified:"● 已修改",editorHint:"Tab 键插入制表符 | Ctrl+S 保存",
        unsavedConfirm:"有未保存的修改，确定放弃吗？",unsavedCloseConfirm:"有未保存的修改，确定关闭吗？",
        previewFail:"加载失败",previewUnsupported:"此文件类型不支持预览",
        pdfMobileHint:"手机浏览器不支持在线阅读 PDF",openInBrowser:"在浏览器中打开",
        previewArchiveUnsupported:"此压缩格式不支持预览，请下载后查看",previewOfficeUnsupported:"此 Office 格式暂不支持在线预览",
        previewDocxFail:"DOCX 渲染失败: ",previewXlsFail:"Excel 渲染失败: ",mermaidFail:"Mermaid 渲染失败: ",downloadFileBtn:"下载文件",
        detailSize:"大小:",detailType:"类型:",detailModified:"修改:",
        zipEntries:"个条目",zipExtractHere:"解压到此处",zipFilename:"文件名",
        bmAddTitle:"收藏当前目录",gridToggleTitle:"切换网格/列表视图",themeToggleTitle:"切换亮/暗主题",langToggleTitle:"切换语言",
        uploadTitleTip:"上传文件",mkdirTitleTip:"新建文件夹",mkfileTitleTip:"新建文件",selectTitleTip:"多选模式",selectAllTitleTip:"全选/取消全选",batchDlTitleTip:"批量下载",batchDelTitleTip:"批量删除",batchMoveTitleTip:"批量移动",batchCopyTitleTip:"批量复制",clipboardTitleTip:"共享剪贴板",bookmarksTitleTip:"收藏夹",
        conflictTitle:"⚠ 文件已存在",conflictMsg:"目标位置已存在同名项目：",conflictOverwrite:"覆盖",conflictRename:"重命名保留两者",conflictSkip:"跳过",conflictApplyAll:"应用到后续所有冲突",
        conflictExtractMsg:"以下文件在目标位置已存在：",conflictExtractMore:"等共 {n} 个文件",uploadConflictLabel:"文件已存在时："},
    en:{upload:"⬆ Upload",mkdir:"📁+ Folder",mkfile:"📄+ File",select:"☐ Select",selectAll:"☑ All",
        batchDl:"📦 Download",batchDel2:"🗑 Delete",batchMove:"✂ Move",batchCopy:"📋 Copy",
        clipboard:"📋 Clipboard",bookmarks:"⭐ Bookmarks",logout:"🚪 Logout",
        loginHint:"Enter access password",loginBtn:"Login",loginFail:"Login failed",
        errWrongPwd:"Wrong password",errRateLimit:"Too many attempts, please try later",errInvalidReq:"Invalid request",
        searchPh:"Search filename or content...",searchName:"Filename",searchContent:"Content",
        sortLabel:"Sort:",sortName:"Name",sortSize:"Size",sortCtime:"Created",sortMtime:"Modified",
        filterLabel:"Filter:",filterAll:"All types",filterImage:"🖼 Images",filterVideo:"🎬 Videos",
        filterAudio:"🎵 Audio",filterText:"📝 Text/Code",filterArchive:"📦 Archives",
        filterFont:"🔤 Fonts",filterOther:"📄 Other",filterExtPh:"Ext e.g. .py,.md",filterClear:"Clear filter",
        statusReady:"Ready",dropHint:"📤 Drop files to upload",breadcrumbRoot:"🏠 Root",
        regexOff:"Normal search (click to enable regex)",regexOn:"Regex enabled (click to disable)",
        modalBack:"← Back",modalEdit:"✏ Edit",modalSave:"💾 Save",modalCancelEdit:"Cancel",modalDownload:"Download",modalShare:"🔗 Share",modalClose:"Close",
        actRename:"Rename",actDelete:"Delete",actDownload:"Download",actCopy:"Copy",actMove:"Move",actDownloadFolder:"Download folder",
        statusItems:" items — ",statusFiltered:"(filtered)",statusDrives:" drive(s)",emptyFolder:"Empty folder",loadFail:"Failed to load",createdPrefix:"Created:",
        selectFirst:"Select files first",packing:"Packing...",packFail:"Pack failed",dlStarted:"Download started",packDlFail:"Batch download failed",packingDl:"Packing & downloading",
        enterDirFirst:"Enter a directory first",selectFiles:"Select files",enterName:"Enter a name",enterFilename:"Enter a filename",
        extHint:"Include an extension, e.g. .txt, .md, .py",nameEmpty:"Name cannot be empty",
        createOk:"Created",createFail:"Create failed",fileCreated:"File created: ",deleted:"Deleted",deleteFail:"Delete failed",
        renameOk:"Renamed",renameFail:"Rename failed",copyOk:"Copied",copyFail:"Copy failed",moveOk:"Moved",moveFail:"Move failed",
        opCopying:"Copying...",opMoving:"Moving...",opDeleting:"Deleting...",opExtracting:"Extracting...",
        clipUpdated:"Clipboard updated",bookmarked:"Bookmarked",bookmarkFail:"Bookmark failed",unbookmarked:"Bookmark removed",
        uploadUploading:"Uploading...",uploadFail:"Upload failed",uploaded:"Uploaded: ",
        noPreviewFile:"No file being previewed",shareFail:"Failed to generate share link",linkCopied:"Link copied",
        saving:"Saving...",saved:"Saved",saveFail:"Save failed",saveNetErr:"Save failed: network error",editorNotOpen:"Editor not open",
        extractOk:"Extracted",extractFail:"Extract failed",dlFolderPacking:"Packing folder for download...",
        dragUpload:"uploaded",dragUploadFail:"Some files failed: ",dragUploadErr:"Upload failed",dragUploadSkip:"Skipped inaccessible files: ",
        searchNoResult:"No matches found",searchFound:"Found",searchResults:"result(s)",searchScanned:"scanned",searchFiles:"file(s)",searchFail:"Search failed",
        batchDelTitle:"Batch Delete",batchDelConfirm:"Delete selected",batchDelUnit:"file(s)?",batchDelIrreversible:"This action cannot be undone",
        batchDelBtn:"Confirm Delete",batchDelDone:"Deleted",batchFail:"failed",
        batchMoveTitle:"Batch Move",batchMoveUnit:"file(s)",batchMoveDone:"Moved",batchCopyTitle:"Batch Copy",batchCopyDone:"Copied",
        uploadTitle:"Upload Files",uploadTarget:"Target: ",uploadHint:"Multi-select, no size limit",uploadBtn:"Start Upload",uploadChoose:"Choose Files",uploadChooseFolder:"Choose Folder",uploadNoFile:"No file selected",uploadFileCount:"{n} file(s) selected",uploadFolderCount:"Folder selected, {n} file(s) total",uploadFolderHint:"Upload entire folder with all subdirectories",uploadReadingFolder:"Reading folder...",
        uploadOkCount:"Success",uploadFailCount:"Failed: ",uploadDone:"Uploaded",uploadDoneUnit:"file(s)",
        uploadPauseBtn:"Pause",uploadResumeBtn:"Resume",uploadCancelBtn:"Cancel",uploadCancelled:"Upload cancelled",uploadSkippedN:"Skipped",uploadCloseBtn:"Close",
        mkdirTitle:"New Folder",mkdirIn:"In",mkdirCreate:"",mkdirPlaceholder:"Folder name",mkdirBtn:"Create",
        mkfileTitle:"📄 New File",mkfilePlaceholder:"Filename, e.g. notes.md, config.json, script.py",
        mkfileHint:"Enter full filename with extension",
        mkfileContentLabel:"Initial content (optional)",mkfileContentPh:"Leave empty or enter initial content...",mkfileBtn:"Create File",
        deleteTitle:"Confirm Delete",deleteMsg:"Delete",deleteAsk:"?",deleteIrreversible:"This action cannot be undone",deleteBtn:"Confirm Delete",
        deleteRecTitle:"⚠ Confirm Recursive Delete",deleteNotEmpty:"is not empty!",
        deleteRecWarn:"ALL contents will be recursively deleted. This cannot be undone!",deleteRecBtn:"🔥 Force Delete All Contents",
        renameTitle:"Rename",renameCurrent:"Current name: ",renameBtn:"Confirm",
        clipTitle:"📋 Shared Clipboard",clipHint:"Share text between phone and PC. Paste here, access from the other device.",
        clipPlaceholder:"Enter text to share...",clipLastUpdate:"Last updated: ",clipSaveBtn:"Save",
        bmTitle:"⭐ Bookmarks",bmEmpty:"No bookmarks yet",bmHint:"Enter a directory and click +⭐ to bookmark",
        shareTitle:"Share Link",shareHint:"Anyone can download without login:",shareCopyBtn:"📋 Copy Link",
        shareExpireLabel:"Select link expiration:",shareCreateBtn:"Create Share Link",
        shareExpire5m:"5 minutes",shareExpire30m:"30 minutes",shareExpire1h:"1 hour",shareExpire6h:"6 hours",shareExpire12h:"12 hours",shareExpire24h:"24 hours",
        pickerHint:"Click folder to enter, then confirm at target",pickerConfirm:"Confirm Current Directory",
        pickerLoading:"Loading...",pickerFail:"Failed to load",pickerNoSub:"No subdirectories",pickerCopy:"Copy",pickerMove:"Move",
        pickerPathPh:"Target directory path",pickerGo:"Go",
        editorModified:"● Modified",editorHint:"Tab inserts tab | Ctrl+S to save",
        unsavedConfirm:"Unsaved changes. Discard?",unsavedCloseConfirm:"Unsaved changes. Close anyway?",
        previewFail:"Failed to load",previewUnsupported:"Preview not supported for this file type",
        pdfMobileHint:"PDF preview is not supported on mobile browsers",openInBrowser:"Open in Browser",
        previewArchiveUnsupported:"This archive format cannot be previewed. Please download.",previewOfficeUnsupported:"This Office format cannot be previewed online",
        previewDocxFail:"DOCX render failed: ",previewXlsFail:"Excel render failed: ",mermaidFail:"Mermaid render failed: ",downloadFileBtn:"Download File",
        detailSize:"Size:",detailType:"Type:",detailModified:"Modified:",
        zipEntries:"entries",zipExtractHere:"Extract here",zipFilename:"Filename",
        bmAddTitle:"Bookmark current directory",gridToggleTitle:"Toggle grid/list view",themeToggleTitle:"Toggle light/dark theme",langToggleTitle:"Toggle language",
        uploadTitleTip:"Upload files",mkdirTitleTip:"New folder",mkfileTitleTip:"New file",selectTitleTip:"Multi-select mode",selectAllTitleTip:"Select all / Deselect all",batchDlTitleTip:"Batch download",batchDelTitleTip:"Batch delete",batchMoveTitleTip:"Batch move",batchCopyTitleTip:"Batch copy",clipboardTitleTip:"Shared clipboard",bookmarksTitleTip:"Bookmarks",
        conflictTitle:"⚠ File Already Exists",conflictMsg:"An item with the same name already exists:",conflictOverwrite:"Overwrite",conflictRename:"Rename (Keep Both)",conflictSkip:"Skip",conflictApplyAll:"Apply to all conflicts",
        conflictExtractMsg:"The following files already exist:",conflictExtractMore:"and {n} more file(s)",uploadConflictLabel:"If file exists:"}
};
const _serverLang="{{ server_lang }}";
const _autoLang=navigator.language&&navigator.language.startsWith("zh")?"zh":"en";
let currentLang=(_serverLang&&_serverLang!=="auto")?_serverLang:(localStorage.getItem("fb_lang")||_autoLang);
function t(k){return (I18N[currentLang]&&I18N[currentLang][k])||k}
(function initLang(){
    applyLang(currentLang);
    const btn=document.getElementById("langBtn");
    if(btn)btn.textContent=currentLang==="zh"?"EN":"中";
})();
function applyLang(lang){
    const tr=I18N[lang]||{};
    document.querySelectorAll("[data-i18n]").forEach(el=>{
        const key=el.getAttribute("data-i18n");if(tr[key])el.textContent=tr[key];
    });
    document.querySelectorAll("[data-i18n-ph]").forEach(el=>{
        const key=el.getAttribute("data-i18n-ph");if(tr[key])el.placeholder=tr[key];
    });
    document.querySelectorAll("[data-i18n-title]").forEach(el=>{
        const key=el.getAttribute("data-i18n-title");if(tr[key])el.title=tr[key];
    });
    document.querySelectorAll("[data-i18n-opt]").forEach(el=>{
        const key=el.getAttribute("data-i18n-opt");if(tr[key])el.textContent=tr[key];
    });
}
function toggleLang(){
    currentLang=currentLang==="zh"?"en":"zh";
    applyLang(currentLang);
    localStorage.setItem("fb_lang",currentLang);
    document.getElementById("langBtn").textContent=currentLang==="zh"?"EN":"中";
    // 刷新动态生成的文本
    if(typeof updateBreadcrumb==="function")updateBreadcrumb(currentPath||"");
    const rb=document.querySelector(".regex-btn");
    if(rb){rb.title=useRegex?t("regexOn"):t("regexOff");}
    // 刷新文件列表（根路径是磁盘列表，需重新 fetch；非根路径用缓存重渲染）
    if(!currentPath&&!isSearching){fetchList("")}
    else if(lastItems){renderFileList(lastItems)}
}

// ═══ Grid View ═══
let isGridView=localStorage.getItem("fb_grid")==="1";
(function initGridView(){
    const btn=document.getElementById("gridViewBtn");
    if(isGridView){
        document.getElementById("content").classList.add("grid-view");
        if(btn)btn.style.color="var(--accent)";
    }
})();
function toggleGridView(){
    isGridView=!isGridView;
    const content=document.getElementById("content");
    const btn=document.getElementById("gridViewBtn");
    content.classList.toggle("grid-view",isGridView);
    btn.style.color=isGridView?"var(--accent)":"";
    localStorage.setItem("fb_grid",isGridView?"1":"0");
    // 重新渲染以显示/隐藏缩略图
    if(!currentPath&&!isSearching){fetchList("")}
    else if(lastItems){renderFileList(lastItems)}
}
// lastItems 已在 renderFileList 内部赋值，此处仅声明初始值
let lastItems=[];

// ═══ Drag & Drop Upload ═══
(function initDragDrop(){
    const overlay=document.getElementById("dropOverlay");
    let dragCounter=0;
    document.addEventListener("dragenter",e=>{
        if(!currentPath)return;
        dragCounter++;
        overlay.classList.add("show");
    });
    document.addEventListener("dragleave",e=>{
        dragCounter--;
        if(dragCounter<=0){dragCounter=0;overlay.classList.remove("show")}
    });
    document.addEventListener("dragover",e=>e.preventDefault());
    document.addEventListener("drop",e=>{
        e.preventDefault();
        dragCounter=0;overlay.classList.remove("show");
        if(!currentPath){toast(t("enterDirFirst"));return}
        const items=e.dataTransfer.items;
        if(items&&items.length){
            let hasDir=false;const entries=[];
            for(let i=0;i<items.length;i++){
                const entry=items[i].webkitGetAsEntry&&items[i].webkitGetAsEntry();
                if(entry){entries.push(entry);if(entry.isDirectory)hasDir=true}
            }
            if(hasDir){uploadEntries(entries);return}
        }
        const files=e.dataTransfer.files;
        if(!files.length)return;
        uploadFiles(files);
    });
})();
async function uploadFiles(files){
    const items=[];for(const f of files)items.push({file:f,relativePath:""});
    await startUploadQueue(items,currentPath,"rename","toast");
}
async function uploadEntries(entries){
    const dToast=document.getElementById("dragUploadToast");
    const dText=document.getElementById("dragUploadText");
    if(dToast){dToast.style.display="block";dText.textContent=t("uploadReadingFolder")}
    const fileList=[];const skippedEntries=[];
    async function readEntry(entry,prefix){
        try{
            if(entry.isFile){
                const file=await new Promise((res,rej)=>entry.file(res,rej));
                fileList.push({file,relPath:prefix+entry.name});
            }else if(entry.isDirectory){
                const dirReader=entry.createReader();
                let allEntries=[];
                const readBatch=()=>new Promise((res,rej)=>dirReader.readEntries(res,rej));
                let batch;
                do{batch=await readBatch();allEntries=allEntries.concat(Array.from(batch))}while(batch.length>0);
                for(const child of allEntries)await readEntry(child,prefix+entry.name+"/");
            }
        }catch(e){skippedEntries.push(prefix+entry.name)}
    }
    for(const entry of entries){
        try{
            if(entry.isDirectory)await readEntry(entry,"");
            else if(entry.isFile){const file=await new Promise((res,rej)=>entry.file(res,rej));fileList.push({file,relPath:""})}
        }catch(e){skippedEntries.push(entry.name)}
    }
    if(skippedEntries.length)toast(t("dragUploadSkip")+skippedEntries.length);
    if(!fileList.length){if(dToast)dToast.style.display="none";return}
    const items=fileList.map(it=>({file:it.file,relativePath:it.relPath}));
    await startUploadQueue(items,currentPath,"rename","toast");
}

// ═══ Copy / Move ═══
// ── 目录选择器（复制/移动共用）──
let _pickerCallback=null;
function openDirPicker(title,defaultPath,onSelect){
    _pickerCallback=onSelect;
    openDialog(title,`<div class="modal-form">
        <div style="display:flex;gap:6px;align-items:center;margin-bottom:8px">
            <input type="text" id="pickerPath" value="${eh(defaultPath)}" style="flex:1" placeholder="${t("pickerPathPh")}">
            <button class="modal-btn modal-btn-close" onclick="pickerGo()" title="${t("pickerGo")}">&#x2192;</button>
        </div>
        <div id="pickerList" style="max-height:260px;overflow-y:auto;border:1px solid var(--border);border-radius:8px;margin-bottom:10px"></div>
        <div class="hint" style="margin-bottom:8px">${t("pickerHint")}</div>
        <button class="modal-btn modal-btn-primary" id="pickerConfirmBtn" style="width:100%">${t("pickerConfirm")}</button>
    </div>`);
    document.getElementById("pickerConfirmBtn").onclick=()=>{
        const dest=document.getElementById("pickerPath")?.value||"";
        closeDialog();
        if(_pickerCallback)_pickerCallback(dest);
    };
    document.getElementById("pickerPath").addEventListener("keydown",e=>{if(e.key==="Enter")pickerGo()});
    pickerLoadDir(defaultPath);
}
function pickerGo(){
    const p=document.getElementById("pickerPath")?.value||"";
    pickerLoadDir(p);
}
function pickerLoadDir(dirPath){
    const list=document.getElementById("pickerList");
    const input=document.getElementById("pickerPath");
    if(!list)return;
    list.innerHTML='<div style="padding:12px;text-align:center;color:var(--text2)">'+t("pickerLoading")+'</div>';
    if(!dirPath){
        // 加载磁盘列表
        fetch("/api/drives").then(r=>r.json()).then(drives=>{
            input.value="";
            list.innerHTML=drives.map(d=>`<div style="padding:8px 12px;cursor:pointer;display:flex;align-items:center;gap:8px;border-bottom:1px solid var(--border)" onclick="pickerLoadDir('${esc(d.path)}')" onmouseenter="this.style.background='var(--hover)'" onmouseleave="this.style.background=''">&#x1f4be; ${eh(d.name)}</div>`).join("");
        }).catch(()=>{list.innerHTML='<div style="padding:12px;color:var(--danger)">'+t("pickerFail")+'</div>'});
        return;
    }
    fetch(`/api/list?path=${encodeURIComponent(dirPath)}&sort=name&order=asc`).then(r=>r.json()).then(data=>{
        if(data.error){list.innerHTML=`<div style="padding:12px;color:var(--danger)">${eh(data.error)}</div>`;return}
        input.value=data.path||dirPath;
        // 显示上级按钮 + 只显示子目录
        let html="";
        if(data.parent!==undefined){
            const parentPath=data.parent||"";
            html+=`<div style="padding:8px 12px;cursor:pointer;display:flex;align-items:center;gap:8px;border-bottom:1px solid var(--border);color:var(--accent)" onclick="pickerLoadDir('${esc(parentPath)}')" onmouseenter="this.style.background='var(--hover)'" onmouseleave="this.style.background=''">&#x2b06; ..</div>`;
        }
        const dirs=(data.items||[]).filter(i=>i.is_dir);
        if(!dirs.length&&!html) html='<div style="padding:12px;color:var(--text2);text-align:center">'+t("pickerNoSub")+'</div>';
        html+=dirs.map(d=>`<div style="padding:8px 12px;cursor:pointer;display:flex;align-items:center;gap:8px;border-bottom:1px solid var(--border)" onclick="pickerLoadDir('${esc(d.path)}')" onmouseenter="this.style.background='var(--hover)'" onmouseleave="this.style.background=''">${d.icon} ${eh(d.name)}</div>`).join("");
        list.innerHTML=html;
    }).catch(()=>{list.innerHTML='<div style="padding:12px;color:var(--danger)">'+t("pickerFail")+'</div>'});
}

// ═══ Conflict Resolution Dialog ═══
function showConflictDialog(name,isBatch,callback){
    let html=`<div class="modal-form">
        <div style="text-align:center;padding:10px 0">
            <div style="font-size:32px;margin-bottom:8px">&#x26a0;&#xfe0f;</div>
            <div>${t("conflictMsg")}</div>
            <div style="font-weight:600;margin:6px 0;word-break:break-all">${eh(name)}</div>
        </div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:center">
            <button class="modal-btn modal-btn-danger" onclick="_conflictResolve('overwrite')">${t("conflictOverwrite")}</button>
            <button class="modal-btn modal-btn-primary" onclick="_conflictResolve('rename')">${t("conflictRename")}</button>
            <button class="modal-btn modal-btn-close" onclick="_conflictResolve('skip')">${t("conflictSkip")}</button>
        </div>`;
    if(isBatch){
        html+=`<label style="display:flex;align-items:center;gap:6px;margin-top:12px;justify-content:center;font-size:13px;color:var(--text2);cursor:pointer">
            <input type="checkbox" id="conflictApplyAll"> ${t("conflictApplyAll")}
        </label>`;
    }
    html+=`</div>`;
    openDialog(t("conflictTitle"),html);
    window._conflictResolve=function(choice){
        const applyAll=isBatch&&document.getElementById("conflictApplyAll")&&document.getElementById("conflictApplyAll").checked;
        closeDialog();
        callback(choice,applyAll);
    };
}
function showExtractConflictDialog(files,total,callback){
    const maxShow=10;
    let listHtml=files.slice(0,maxShow).map(f=>`<div style="font-size:13px;padding:2px 0;word-break:break-all">• ${eh(f)}</div>`).join("");
    if(total>maxShow) listHtml+=`<div style="font-size:13px;color:var(--text2);padding:2px 0">${t("conflictExtractMore").replace("{n}",total)}</div>`;
    const html=`<div class="modal-form">
        <div style="text-align:center;padding:6px 0">
            <div style="font-size:32px;margin-bottom:8px">&#x26a0;&#xfe0f;</div>
            <div style="margin-bottom:8px">${t("conflictExtractMsg")}</div>
        </div>
        <div style="max-height:160px;overflow-y:auto;margin-bottom:12px;padding:8px;background:var(--bg);border-radius:8px;border:1px solid var(--border)">${listHtml}</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:center">
            <button class="modal-btn modal-btn-danger" onclick="_conflictResolve('overwrite')">${t("conflictOverwrite")}</button>
            <button class="modal-btn modal-btn-primary" onclick="_conflictResolve('rename')">${t("conflictRename")}</button>
            <button class="modal-btn modal-btn-close" onclick="_conflictResolve('skip')">${t("conflictSkip")}</button>
        </div></div>`;
    openDialog(t("conflictTitle"),html);
    window._conflictResolve=function(choice){closeDialog();callback(choice)};
}

function copyPrompt(path,name){
    openDirPicker(`${t("pickerCopy")} ${name}`,currentPath,async(destDir)=>{
        async function doCopy(conflict){
            const body={src:path,dest_dir:destDir};
            if(conflict)body.conflict=conflict;
            showOpProgress(t("opCopying"),true);
            const d=await streamOp("/api/copy",body,updateOpProgress);
            closeDialog();
            if(d.ok){toast(d.skipped?t("conflictSkip"):t("copyOk"));fetchList(currentPath)}
            else if(d.conflict){showConflictDialog(d.name,false,(choice)=>{doCopy(choice)})}
            else toast(d.error||t("copyFail"));
        }
        doCopy();
    });
}
function movePrompt(path,name){
    openDirPicker(`${t("pickerMove")} ${name}`,currentPath,async(destDir)=>{
        async function doMove(conflict){
            const body={src:path,dest_dir:destDir};
            if(conflict)body.conflict=conflict;
            showOpProgress(t("opMoving"),true);
            const d=await streamOp("/api/move",body,updateOpProgress);
            closeDialog();
            if(d.ok){toast(d.skipped?t("conflictSkip"):t("moveOk"));fetchList(currentPath)}
            else if(d.conflict){showConflictDialog(d.name,false,(choice)=>{doMove(choice)})}
            else toast(d.error||t("moveFail"));
        }
        doMove();
    });
}

// ═══ Folder Download ═══
async function downloadFolder(path,name){
    showOpProgress(t("packingDl"),true);
    try{
        const r=await fetch(`/api/download-folder?path=${encodeURIComponent(path)}`);
        if(!r.ok){closeDialog();toast(t("packFail"));return}
        const total=parseInt(r.headers.get("Content-Length")||"0",10);
        const reader=r.body.getReader();const chunks=[];let loaded=0;
        while(true){
            const{done,value}=await reader.read();if(done)break;
            chunks.push(value);loaded+=value.length;
            if(total>0)updateOpProgress({p:loaded,t:total});
        }
        closeDialog();
        const blob=new Blob(chunks,{type:"application/zip"});
        const a=document.createElement("a");
        a.href=URL.createObjectURL(blob);
        a.download=name+".zip";
        a.click();URL.revokeObjectURL(a.href);
        toast(t("dlStarted"));
    }catch(e){closeDialog();toast(t("packDlFail"))}
}

// ═══ ZIP Extract ═══
async function extractZip(zipPath,conflict){
    const destDir=zipPath.replace(/[/\\][^/\\]+$/, "");
    const body={path:zipPath,dest_dir:destDir};
    if(conflict)body.conflict=conflict;
    showOpProgress(t("opExtracting"),false);
    const d=await streamOp("/api/extract",body,updateOpProgress);
    closeDialog();
    if(d.ok){toast(t("extractOk"));fetchList(currentPath)}
    else if(d.conflict){
        showExtractConflictDialog(d.files||[],d.total||0,(choice)=>{extractZip(zipPath,choice)});
    }
    else toast(d.error||t("extractFail"));
}

// ═══ Logout ═══
async function doLogout(){
    try{await fetch("/api/logout",{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"})}catch(e){}
    location.reload();
}

// ═══ Share Link ═══
function showShareDialog(){
    if(!currentPreviewPath){toast(t("noPreviewFile"));return}
    openDialog(t("shareTitle"),`<div class="modal-form">
        <label style="color:var(--text2);font-size:13px">${t("shareExpireLabel")}</label>
        <select id="shareExpireSelect" class="modal-input" style="margin:8px 0">
            <option value="300">${t("shareExpire5m")}</option>
            <option value="1800">${t("shareExpire30m")}</option>
            <option value="3600" selected>${t("shareExpire1h")}</option>
            <option value="21600">${t("shareExpire6h")}</option>
            <option value="43200">${t("shareExpire12h")}</option>
            <option value="86400">${t("shareExpire24h")}</option>
        </select>
        <button class="modal-btn modal-btn-primary" onclick="doShare()" style="width:100%">${t("shareCreateBtn")}</button>
        <div id="shareResult" style="display:none;margin-top:10px">
            <input class="share-url" id="shareUrlInput" readonly onclick="this.select()">
            <button class="modal-btn modal-btn-primary" onclick="copyShareUrl()" style="width:100%;margin-top:8px">${t("shareCopyBtn")}</button>
        </div>
    </div>`);
}
async function doShare(){
    const sel=document.getElementById("shareExpireSelect");
    const expires=parseInt(sel?sel.value:"3600")||3600;
    const r=await fetch("/api/share",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({path:currentPreviewPath,expires})}).then(r=>r.json());
    if(!r.ok){toast(r.error||t("shareFail"));return}
    const fullUrl=location.origin+r.url;
    const result=document.getElementById("shareResult");
    const input=document.getElementById("shareUrlInput");
    if(result&&input){input.value=fullUrl;result.style.display="block"}
}
function copyShareUrl(){
    const input=document.getElementById("shareUrlInput");
    if(!input)return;
    // navigator.clipboard 仅在 HTTPS/localhost 下可用，HTTP 局域网地址不可用
    // 因此优先用 fallback 方案确保兼容
    try{
        if(navigator.clipboard&&window.isSecureContext){
            navigator.clipboard.writeText(input.value).then(()=>toast(t("linkCopied"))).catch(()=>fallbackCopy(input));
        }else{
            fallbackCopy(input);
        }
    }catch(e){fallbackCopy(input)}
}
function fallbackCopy(input){
    input.select();input.setSelectionRange(0,99999);
    document.execCommand("copy");
    toast(t("linkCopied"));
}

// ═══ Donate Dialog ═══
function showDonate(){
    openDialog("Support / 打赏作者",`<div style="text-align:center;padding:8px" data-author="bbyybb" data-sig="LFB-bbloveyy-2026">
        <div style="display:flex;gap:20px;justify-content:center;flex-wrap:wrap;margin-bottom:16px">
            <div><img src="/api/raw?path=docs/wechat_pay.jpg" style="width:220px;height:220px;border-radius:8px;border:1px solid var(--border)" onerror="this.style.display='none'"><div style="margin-top:4px;font-size:13px"><b>微信支付</b></div></div>
            <div><img src="/api/raw?path=docs/alipay.jpg" style="width:220px;height:220px;border-radius:8px;border:1px solid var(--border)" onerror="this.style.display='none'"><div style="margin-top:4px;font-size:13px"><b>支付宝</b></div></div>
            <div><a href="https://www.buymeacoffee.com/bbyybb" target="_blank" rel="noopener"><img src="/api/raw?path=docs/bmc_qr.png" style="width:150px;height:150px;border-radius:8px;border:1px solid var(--border)" onerror="this.style.display='none'"></a><div style="margin-top:4px;font-size:13px"><b>☕ Buy Me a Coffee</b></div></div>
        </div>
        <div style="font-size:13px;color:var(--text2)">
            <a href="https://www.buymeacoffee.com/bbyybb" target="_blank" rel="noopener" style="color:var(--accent)">buymeacoffee.com/bbyybb</a>
            &nbsp;|&nbsp;
            <a href="https://github.com/sponsors/bbyybb/" target="_blank" rel="noopener" style="color:var(--accent)">GitHub Sponsors</a>
        </div>
    </div>`);
}

// ═══ Regex Search Toggle ═══
let useRegex=false;
// 在搜索框旁加正则切换（动态插入）
(function initRegexToggle(){
    const wrap=document.querySelector(".search-box");
    if(!wrap)return;
    const btn=document.createElement("button");
    btn.className="regex-btn";btn.title=t("regexOff");btn.textContent=".*";
    btn.onclick=()=>{
        useRegex=!useRegex;
        btn.classList.toggle("active",useRegex);
        btn.title=useRegex?t("regexOn"):t("regexOff");
        onSearchInput();
    };
    wrap.appendChild(btn);
})();

// 覆盖原 onSearchInput，补充正则支持，同时保留搜索清除按钮和模式栏逻辑
function onSearchInput(e){
    const input=document.getElementById("searchInput");
    if(!input)return;
    const q=input.value.trim();
    // 保持原有逻辑：切换清除按钮和搜索模式栏的显示
    const clearBtn=document.getElementById("searchClear");
    const modeBar=document.getElementById("searchModeBar");
    if(clearBtn)clearBtn.classList.toggle("show",q.length>0);
    if(modeBar)modeBar.style.display=q.length>0?"flex":"none";
    if(!q){isSearching=false;fetchList(currentPath);return}
    isSearching=true;
    clearTimeout(searchTimeout);
    searchTimeout=setTimeout(()=>doSearch(q),500);
}
function doSearch(q){
    isSearching=true;
    const content=document.getElementById("content");
    const loading=document.getElementById("loading");
    loading.classList.add("show");content.innerHTML="";
    const endpoint=searchMode==="content"?"/api/search-content":"/api/search";
    const regexParam=useRegex?"&regex=1":"";
    fetch(`${endpoint}?path=${encodeURIComponent(currentPath)}&q=${encodeURIComponent(q)}${regexParam}`)
    .then(r=>{if(r.status===401){showLoginPage();throw"auth"}return r.json()})
    .then(data=>{
        loading.classList.remove("show");
        if(data.error){content.innerHTML=`<div class="empty"><div class="empty-icon">&#x26a0;&#xfe0f;</div><div>${eh(data.error)}</div></div>`;return}
        const results=data.results||[];
        if(!results.length){content.innerHTML=`<div class="empty"><div class="empty-icon">&#x1f50d;</div><div>${t("searchNoResult")}</div></div>`;return}
        renderFileList(results);
        let status=`${t("searchFound")} ${results.length} ${t("searchResults")}`;
        if(data.files_scanned)status+=` (${t("searchScanned")} ${data.files_scanned} ${t("searchFiles")})`;
        document.getElementById("statusText").textContent=status;
    }).catch(e=>{if(e==="auth")return;loading.classList.remove("show");content.innerHTML=`<div class="empty"><div class="empty-icon">&#x274c;</div><div>${t("searchFail")}</div></div>`});
}
</script>
</body>
</html>
"""


# ════════════════════════════════════════════════════════════
# 主入口
# ════════════════════════════════════════════════════════════
if __name__ == "__main__":
    # 修复 Windows 控制台编码（某些终端默认 GBK，无法输出特殊字符）
    # 使用 try/except 防止在非标准终端（如 IDE 内嵌终端）中失败
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
    except Exception:
        pass  # 编码修复失败不影响主功能

    # ── 终端语言检测（预解析 --lang 参数，确保 --help 也能正确显示对应语言）──
    import locale as _locale
    try:
        _sys_lang = _locale.getlocale()[0] or os.environ.get("LANG", "")
    except Exception:
        _sys_lang = os.environ.get("LANG", "")
    _cli_lang = "zh" if "zh" in (_sys_lang or "").lower() or "chinese" in (_sys_lang or "").lower() else "en"
    # 预扫描 sys.argv 中的 --lang 参数（在 argparse 之前生效）
    for _i, _a in enumerate(sys.argv):
        if _a == "--lang" and _i + 1 < len(sys.argv) and sys.argv[_i + 1] in ("zh", "en"):
            _cli_lang = sys.argv[_i + 1]
            break

    # SSL/HTTPS 配置（可通过 config.json 或 CLI 参数设置）
    _ssl_cert = None
    _ssl_key = None
    _use_https = False
    # 终端 i18n 字典
    _TL = {
        "zh": {
            "desc": "LAN File Browser - 局域网文件浏览器",
            "epilog": "示例:\n  python file_browser.py --roots D:/shared E:/docs\n  python file_browser.py --port 8080 --password mypass",
            "h_port": f"服务端口（默认: {PORT}）", "h_password": "指定固定密码（默认: 自动生成随机密码）",
            "h_no_password": "禁用密码保护", "h_roots": "允许访问的目录白名单（可指定多个），未指定则不限制",
            "h_no_sleep": "不阻止系统睡眠（默认会阻止）", "h_allow_sleep": "同 --no-sleep",
            "h_read_only": "只读模式，禁止所有修改操作（上传/删除/重命名等）",
            "h_no_interactive": "跳过交互式引导，直接使用默认值/命令行参数启动",
            "h_lang": "界面语言（终端+浏览器）: zh(中文) / en(English)",
            "wizard_title": "LAN File Browser - 启动配置", "wizard_hint": "直接按回车使用 [默认值]",
            "port_prompt": f"  端口 [{PORT}]: ", "port_invalid": f"    无效端口，使用默认值 {PORT}",
            "pwd_title": "  密码模式:", "pwd_1": "    1. 自动生成随机密码（默认）", "pwd_2": "    2. 自定义固定密码",
            "pwd_3": "    3. 不设密码", "pwd_4": "    4. 多用户多密码（不同用户不同权限）",
            "pwd_choose": "  请选择 [1]: ", "pwd_input": "  请输入密码: ", "pwd_empty": "    密码为空，将自动生成随机密码",
            "mu_title": "  多用户模式:", "mu_1": "    1. 自动生成（默认，1个管理员 + 1个只读用户）",
            "mu_2": "    2. 手动添加用户", "mu_format": "  输入格式: 用户名 密码 权限(admin/readonly)",
            "mu_end": "  输入空行结束添加", "mu_prompt": "  添加用户 (如: teacher abc123 admin): ",
            "mu_format_err": "    格式错误，需要至少: 用户名 密码 [权限]",
            "mu_role_invalid": "    权限 '{role}' 无效，可选: admin / readonly",
            "mu_none": "    未添加任何用户，将使用自动生成随机密码模式",
            "mu_admin": "管理员", "mu_readonly": "只读",
            "root_title": "  访问范围:", "root_1": "    1. 不限制，可访问所有文件（默认）",
            "root_2": "    2. 只允许访问指定目录", "root_input_hint": "  请输入允许访问的目录路径（多个用逗号分隔）:",
            "root_input": "  路径: ", "root_invalid": "    以下路径不存在，已忽略: ",
            "root_none": "    没有有效目录，将不限制访问范围",
            "perm_title": "  权限模式:", "perm_1": "    1. 完全权限（默认，可浏览/上传/编辑/删除等所有操作）",
            "perm_2": "    2. 只读模式（只能浏览、预览和下载，禁止修改）",
            "perm_multi": "  权限模式: 由各用户角色控制（admin=完全权限, readonly=只读）",
            "sleep_title": "  阻止系统睡眠（服务运行期间防止电脑休眠）:",
            "sleep_1": "    1. 是，阻止睡眠（默认）", "sleep_2": "    2. 否，允许正常睡眠",
            "done": "  配置完成，正在启动服务...", "cancelled": "  已取消，再见！",
            "stopped": "  Server stopped.",
        },
        "en": {
            "desc": "LAN File Browser", "epilog": "Examples:\n  python file_browser.py --roots D:/shared E:/docs\n  python file_browser.py --port 8080 --password mypass",
            "h_port": f"Server port (default: {PORT})", "h_password": "Set fixed password (default: auto-generate)",
            "h_no_password": "Disable password protection", "h_roots": "Directory whitelist (multiple allowed), unrestricted if not set",
            "h_no_sleep": "Don't prevent system sleep (default: prevent)", "h_allow_sleep": "Same as --no-sleep",
            "h_read_only": "Read-only mode, disable all modifications",
            "h_no_interactive": "Skip interactive wizard, start with defaults/CLI args",
            "h_lang": "UI language (terminal + browser): zh(Chinese) / en(English)",
            "wizard_title": "LAN File Browser - Setup", "wizard_hint": "Press Enter for [defaults]",
            "port_prompt": f"  Port [{PORT}]: ", "port_invalid": f"    Invalid port, using default {PORT}",
            "pwd_title": "  Password mode:", "pwd_1": "    1. Auto-generate random password (default)",
            "pwd_2": "    2. Custom fixed password", "pwd_3": "    3. No password",
            "pwd_4": "    4. Multi-user multi-password (different permissions)",
            "pwd_choose": "  Choose [1]: ", "pwd_input": "  Enter password: ", "pwd_empty": "    Empty password, will auto-generate",
            "mu_title": "  Multi-user mode:", "mu_1": "    1. Auto-generate (default, 1 admin + 1 read-only)",
            "mu_2": "    2. Add users manually", "mu_format": "  Format: username password role(admin/readonly)",
            "mu_end": "  Enter empty line to finish", "mu_prompt": "  Add user (e.g. teacher abc123 admin): ",
            "mu_format_err": "    Format error, need at least: username password [role]",
            "mu_role_invalid": "    Role '{role}' invalid, options: admin / readonly",
            "mu_none": "    No users added, will auto-generate random password",
            "mu_admin": "admin", "mu_readonly": "readonly",
            "root_title": "  Access scope:", "root_1": "    1. Unrestricted, access all files (default)",
            "root_2": "    2. Only allow specified directories", "root_input_hint": "  Enter directory paths (comma-separated):",
            "root_input": "  Paths: ", "root_invalid": "    These paths don't exist, ignored: ",
            "root_none": "    No valid directories, access will be unrestricted",
            "perm_title": "  Permission mode:", "perm_1": "    1. Full access (default)",
            "perm_2": "    2. Read-only mode (browse, preview, download only)",
            "perm_multi": "  Permission mode: controlled by user roles (admin=full, readonly=read-only)",
            "sleep_title": "  Prevent system sleep (keep PC awake while running):",
            "sleep_1": "    1. Yes, prevent sleep (default)", "sleep_2": "    2. No, allow normal sleep",
            "done": "  Setup complete, starting server...", "cancelled": "  Cancelled, goodbye!",
            "stopped": "  Server stopped.",
        },
    }
    def _t(k): return _TL[_cli_lang].get(k, _TL["en"].get(k, k))

    # ── 加载 config.json（如果存在）──
    _config_path = os.path.join(DATA_DIR, "config.json")
    if os.path.isfile(_config_path):
        try:
            with open(_config_path, 'r', encoding='utf-8') as _cf:
                _config = json.load(_cf)
            if "port" in _config:           PORT = int(_config["port"])
            if "password" in _config:       PASSWORD = _config["password"]
            if "roots" in _config:          ALLOWED_ROOTS = list(_config["roots"])
            if "read_only" in _config:      READ_ONLY = bool(_config["read_only"])
            if "prevent_sleep" in _config:  PREVENT_SLEEP = bool(_config["prevent_sleep"])
            if "lang" in _config and _config["lang"] in ("zh", "en"):
                _cli_lang = _config["lang"]
            if "users" in _config:          USERS = dict(_config["users"])
            if "ssl_cert" in _config:       _ssl_cert = _config["ssl_cert"]
            if "ssl_key" in _config:        _ssl_key = _config["ssl_key"]
            sys.stderr.write(f"  [INFO] Loaded config from {_config_path}\n")
        except Exception as e:
            sys.stderr.write(f"  [WARN] Failed to load config.json: {e}\n")

    # ── 命令行参数解析 ──
    import argparse
    parser = argparse.ArgumentParser(
        description=_t("desc"),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=_t("epilog"),
    )
    parser.add_argument("--port", type=int, default=None, help=_t("h_port"))
    parser.add_argument("--password", type=str, default=None, help=_t("h_password"))
    parser.add_argument("--no-password", action="store_true", help=_t("h_no_password"))
    parser.add_argument("--roots", nargs="+", default=None, metavar="DIR", help=_t("h_roots"))
    parser.add_argument("--no-sleep", action="store_true", help=_t("h_no_sleep"))
    parser.add_argument("--allow-sleep", action="store_true", help=_t("h_allow_sleep"))
    parser.add_argument("--read-only", action="store_true", help=_t("h_read_only"))
    parser.add_argument("--no-interactive", "-y", action="store_true", help=_t("h_no_interactive"))
    parser.add_argument("--lang", type=str, default=None, choices=["zh", "en"], help=_t("h_lang"))
    parser.add_argument("--ssl-cert", type=str, default=None, metavar="FILE",
                        help="SSL certificate file path (enables HTTPS)")
    parser.add_argument("--ssl-key", type=str, default=None, metavar="FILE",
                        help="SSL private key file path (enables HTTPS)")
    args = parser.parse_args()
    if args.lang:
        _cli_lang = args.lang

    # 将终端语言设置同步到前端（通过 app.config 传递）
    app.config["SERVER_LANG"] = _cli_lang

    # 命令行参数覆盖配置文件中的默认值
    if args.port is not None:
        PORT = args.port
    if args.password is not None:
        PASSWORD = args.password
    if args.no_password:
        PASSWORD = ""
    if args.roots is not None:
        ALLOWED_ROOTS = args.roots
    if args.no_sleep or args.allow_sleep:
        PREVENT_SLEEP = False
    if args.read_only:
        READ_ONLY = True
    if args.ssl_cert:
        _ssl_cert = args.ssl_cert
    if args.ssl_key:
        _ssl_key = args.ssl_key

    # SSL 参数校验
    if bool(_ssl_cert) != bool(_ssl_key):
        sys.stderr.write("  [ERROR] --ssl-cert and --ssl-key must both be specified\n")
        sys.exit(1)
    if _ssl_cert and not os.path.isfile(_ssl_cert):
        sys.stderr.write(f"  [ERROR] SSL cert file not found: {_ssl_cert}\n")
        sys.exit(1)
    if _ssl_key and not os.path.isfile(_ssl_key):
        sys.stderr.write(f"  [ERROR] SSL key file not found: {_ssl_key}\n")
        sys.exit(1)
    _use_https = bool(_ssl_cert and _ssl_key)

    # ── 交互式启动引导 ──
    # 如果没有传命令行参数（除了 --no-interactive），则进入交互式引导
    has_cli_args = any([
        args.port, args.password, args.no_password,
        args.roots, args.no_sleep, args.allow_sleep, args.read_only
    ])

    # 交互引导的输出统一走 stderr，避免 Flask 接管 stdout 导致缓冲问题
    def _p(text=""):
        sys.stderr.write(text + "\n")
        sys.stderr.flush()

    if not args.no_interactive and not has_cli_args:
      try:
        _p("")
        _p("=" * 50)
        _p(f"  {_t('wizard_title')}")
        _p(f"  {_t('wizard_hint')}")
        _p("=" * 50)
        _p("")

        # 端口
        port_input = input(_t("port_prompt")).strip()
        if port_input:
            try:
                PORT = int(port_input)
            except ValueError:
                _p(_t("port_invalid"))

        # 密码模式
        _p("")
        _p(_t("pwd_title"))
        _p(_t("pwd_1"))
        _p(_t("pwd_2"))
        _p(_t("pwd_3"))
        _p(_t("pwd_4"))
        pwd_choice = input(_t("pwd_choose")).strip()
        if pwd_choice == "2":
            custom_pwd = input(_t("pwd_input")).strip()
            if custom_pwd:
                PASSWORD = custom_pwd
            else:
                _p(_t("pwd_empty"))
        elif pwd_choice == "3":
            PASSWORD = ""
        elif pwd_choice == "4":
            _p("")
            _p(_t("mu_title"))
            _p(_t("mu_1"))
            _p(_t("mu_2"))
            mu_choice = input(_t("pwd_choose")).strip()
            if mu_choice == "2":
                _p("")
                _p(_t("mu_format"))
                _p(_t("mu_end"))
                _p("")
                while True:
                    line = input(_t("mu_prompt")).strip()
                    if not line:
                        break
                    parts = line.split()
                    if len(parts) < 2:
                        _p(_t("mu_format_err"))
                        continue
                    uname = parts[0]
                    upwd = parts[1]
                    urole = parts[2] if len(parts) >= 3 else "admin"
                    if urole not in ("admin", "readonly"):
                        _p(_t("mu_role_invalid").replace("{role}", urole))
                        urole = "admin"
                    USERS[uname] = {"password": upwd, "role": urole}
                    _p(f"    + {uname} ({urole})")
                if not USERS:
                    _p(_t("mu_none"))
            else:
                # 自动生成：1个 admin + 1个 readonly，32位高强度密码
                _chars = string.ascii_letters + string.digits + "!@#$%&*-_=+"
                admin_pwd = ''.join(secrets.choice(_chars) for _ in range(32))
                reader_pwd = ''.join(secrets.choice(_chars) for _ in range(32))
                USERS["admin"] = {"password": admin_pwd, "role": "admin"}
                USERS["reader"] = {"password": reader_pwd, "role": "readonly"}
                _p(f"    + admin  ({_t('mu_admin')}): {admin_pwd}")
                _p(f"    + reader ({_t('mu_readonly')}):   {reader_pwd}")

        # 目录白名单
        _p("")
        _p(_t("root_title"))
        _p(_t("root_1"))
        _p(_t("root_2"))
        root_choice = input(_t("pwd_choose")).strip()
        if root_choice == "2":
            _p(_t("root_input_hint"))
            roots_input = input(_t("root_input")).strip()
            if roots_input:
                ALLOWED_ROOTS = [r.strip() for r in roots_input.split(",") if r.strip()]
                valid_roots = [r for r in ALLOWED_ROOTS if os.path.isdir(r)]
                invalid_roots = [r for r in ALLOWED_ROOTS if not os.path.isdir(r)]
                if invalid_roots:
                    _p(f"{_t('root_invalid')}{', '.join(invalid_roots)}")
                ALLOWED_ROOTS = valid_roots
                if not ALLOWED_ROOTS:
                    _p(_t("root_none"))

        # 权限模式（多用户模式下跳过，由各用户角色控制）
        if not USERS:
            _p("")
            _p(_t("perm_title"))
            _p(_t("perm_1"))
            _p(_t("perm_2"))
            perm_choice = input(_t("pwd_choose")).strip()
            if perm_choice == "2":
                READ_ONLY = True
        else:
            _p("")
            _p(_t("perm_multi"))

        # 阻止睡眠
        _p("")
        _p(_t("sleep_title"))
        _p(_t("sleep_1"))
        _p(_t("sleep_2"))
        sleep_choice = input(_t("pwd_choose")).strip()
        if sleep_choice == "2":
            PREVENT_SLEEP = False

        _p("")
        _p("-" * 50)
        _p(f"  {_t('done')}")
        _p("-" * 50)
      except KeyboardInterrupt:
        _p("")
        _p("")
        _p(_t("cancelled"))
        sys.exit(0)

    if not _check_res_integrity(HTML_TEMPLATE):
        sys.stderr.write("\n")
        sys.stderr.write("=" * 54 + "\n")
        sys.stderr.write("  [ERROR] Author attribution has been modified!\n")
        sys.stderr.write("  Original author: \u767d\u767dLOVE\u5c39\u5c39\n")
        sys.stderr.write("  This program refuses to start with\n")
        sys.stderr.write("  tampered attribution. Please restore\n")
        sys.stderr.write("  the original author information.\n")
        sys.stderr.write("=" * 54 + "\n")
        sys.exit(1)

    files_ok, tampered_files = _check_file_integrity()
    if not files_ok:
        sys.stderr.write("\n")
        sys.stderr.write("=" * 54 + "\n")
        sys.stderr.write("  [ERROR] Protected files have been tampered!\n")
        for tf in tampered_files:
            sys.stderr.write(f"  - {tf}\n")
        sys.stderr.write("  Original author: \u767d\u767dLOVE\u5c39\u5c39\n")
        sys.stderr.write("  Run with original files or contact the author.\n")
        sys.stderr.write("=" * 54 + "\n")
        sys.exit(1)

    # 确定访问密码
    if PASSWORD is None:
        # 自动生成 32 位高强度密码（大小写字母 + 数字 + 特殊符号）
        chars = string.ascii_letters + string.digits + "!@#$%&*-_=+"
        access_password = ''.join(secrets.choice(chars) for _ in range(32))
    else:
        access_password = PASSWORD

    ip = get_local_ip()
    _scheme = "https" if _use_https else "http"
    url = f"{_scheme}://{ip}:{PORT}"

    # 使用 sys.stderr.write 确保信息一定能输出
    # （Flask 会接管 stdout，但 stderr 不受影响）
    def banner(text):
        """输出启动信息到 stderr，确保在所有终端环境下都能显示。"""
        try:
            sys.stderr.write(text + "\n")
            sys.stderr.flush()
        except Exception:
            pass

    banner("")
    banner("=" * 54)
    banner(f"  [File Browser v{__version__}] started")
    banner("=" * 54)
    banner(f"  Local:    {_scheme}://localhost:{PORT}")
    banner(f"  Phone:    {url}")
    if USERS:
        banner(f"  Users:    {len(USERS)} user(s):")
        for uname, uinfo in USERS.items():
            banner(f"            - {uname} ({uinfo['role']}): {uinfo['password']}")
    elif access_password:
        banner(f"  Password: {access_password}")
    else:
        banner("  Password: (disabled)")
    if ALLOWED_ROOTS:
        banner(f"  Access:   {len(ALLOWED_ROOTS)} allowed dir(s):")
        for r in ALLOWED_ROOTS:
            banner(f"            - {r}")
    else:
        banner("  Access:   all files (no restriction)")
    # 阻止系统睡眠
    sleep_ok = False
    if PREVENT_SLEEP:
        sleep_ok = prevent_sleep_start()
    banner(f"  Sleep:    {'blocked' if sleep_ok else 'not blocked' if PREVENT_SLEEP else 'allowed'}")
    banner(f"  Mode:     {'READ-ONLY' if READ_ONLY else 'full access'}")
    banner(f"  HTTPS:    {'enabled' if _use_https else 'disabled'}")
    banner(f"  Log:      {ACCESS_LOG_FILE}")
    banner("=" * 54)
    banner("  Press Ctrl+C to stop")
    banner("=" * 54)
    banner("")

    try:
        if _use_https:
            # Waitress 不支持 SSL，HTTPS 模式使用 Flask 内置服务器
            banner("  Server:   Flask built-in (HTTPS mode)")
            _ssl_ctx = (_ssl_cert, _ssl_key)
            app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True,
                    ssl_context=_ssl_ctx)
        else:
            try:
                from waitress import serve as _waitress_serve
                banner("  Server:   Waitress (production)")
                _waitress_serve(app, host="0.0.0.0", port=PORT,
                                threads=8, channel_timeout=120,
                                max_request_body_size=10737418240)
            except ImportError:
                banner("  Server:   Flask built-in (install waitress for production)")
                app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
    except KeyboardInterrupt:
        pass
    finally:
        # 服务停止时恢复系统睡眠
        if PREVENT_SLEEP:
            prevent_sleep_stop()
        sys.stderr.write("\n  Server stopped.\n")

# -*- coding: utf-8 -*-
"""
局域网文件浏览器 (LAN File Browser) v2.1
==========================================
一个运行在电脑端的 Web 文件浏览器，可通过手机（同局域网内）
使用浏览器访问 http://<电脑IP>:25600 来浏览、搜索、预览和下载电脑中的文件。

功能特性 v2.1:
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

import os
import sys
import io
import re
import hmac
import time
import shutil
import socket
import mimetypes
import secrets
import string
import json
import zipfile
import logging
from pathlib import Path
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template_string, request, send_file,
    jsonify, abort, make_response, Response,
)

# ════════════════════════════════════════════════════════════
# Flask 应用实例
# ════════════════════════════════════════════════════════════
app = Flask(__name__)

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

# ════════════════════════════════════════════════════════════
# 全局状态
# ════════════════════════════════════════════════════════════
# 认证 token（启动时生成，单密码模式使用）
AUTH_TOKEN = secrets.token_hex(16)

# 多用户 session: {token: {"user": username, "role": "admin"|"readonly"}}
user_sessions = {}

# 共享剪贴板（内存存储）
clipboard_data = {"text": "", "updated": ""}

# 访问密码（启动时确定）
access_password = ""

# 登录速率限制: {ip: [timestamp1, timestamp2, ...]}
login_attempts = {}

# 临时分享链接: {token: {"path": str, "expires_at": float}}
share_tokens = {}

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

import hashlib as _hl
_RES_MARKERS = ['\u767d\u767dLOVE\u5c39\u5c39', 'LFB-bbloveyy-2026',
                'bbyybb', 'buymeacoffee.com/bbyybb', 'sponsors/bbyybb']
_RES_EXPECTED = 'c908d591dce0b0df'

_SEAL_HASHES = {
    "README.md": "c2bba3d64e3ef259900aeb1258cd368982d675f06a00462fb94a83d84c95abff",
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
        handler = logging.FileHandler(ACCESS_LOG_FILE, encoding="utf-8")
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
    if USERS and token in user_sessions:
        return user_sessions[token]["role"]
    # 单密码模式
    if not USERS and hmac.compare_digest(token, AUTH_TOKEN):
        return "admin"
    return None

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
    """获取本机局域网 IP 地址。"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
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


def get_file_type(filename):
    """根据文件扩展名判断文件类别。"""
    ext = Path(filename).suffix.lower()
    type_map = {
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
            # 数据格式
            '.json', '.jsonc', '.json5', '.ndjson', '.jsonl', '.geojson',
            '.xml', '.yaml', '.yml', '.toml', '.ini', '.cfg', '.conf',
            '.proto', '.avsc',
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
            # Shell / 终端
            '.sh', '.bash', '.zsh', '.fish', '.csh', '.ksh',
            '.bat', '.cmd', '.ps1', '.psm1',
            # 系统配置 — Windows
            '.reg', '.inf', '.vbs', '.vba', '.wsf',
            # 系统配置 — macOS / iOS
            '.plist', '.strings', '.entitlements', '.pbxproj',
            # 系统配置 — Linux
            '.desktop', '.service', '.timer', '.socket', '.mount',
            # DevOps / CI / 构建
            '.tf', '.hcl', '.properties', '.sbt', '.cmake',
            '.mk', '.mak', '.cabal', '.gemspec', '.podspec',
            # Web 服务器 / API
            '.htaccess', '.nginx', '.graphql', '.gql',
            # 文档 / 标记
            '.rst', '.asciidoc', '.adoc', '.tex', '.latex', '.bib', '.sty', '.cls',
            '.dtd', '.xsd', '.xsl', '.xslt',
            # 字幕
            '.srt', '.vtt', '.ass', '.ssa', '.sub', '.lrc',
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
    for ftype, exts in type_map.items():
        if ext in exts:
            return ftype
    # 无扩展名的常见文本文件（按文件名匹配）
    name = Path(filename).name
    text_filenames = {
        # 构建 / 项目文件
        'makefile', 'dockerfile', 'vagrantfile', 'gemfile', 'rakefile',
        'procfile', 'brewfile', 'justfile', 'cmakelists.txt',
        # 项目说明文件
        'license', 'licence', 'authors', 'contributors', 'changelog',
        'readme', 'todo', 'copying', 'install', 'news', 'thanks',
        # Git
        '.gitignore', '.gitattributes', '.gitmodules', '.gitconfig',
        # Docker / CI
        '.dockerignore', '.dockerfile',
        # 编辑器 / IDE 配置
        '.editorconfig', '.prettierrc', '.eslintrc', '.stylelintrc',
        '.babelrc', '.npmrc', '.yarnrc', '.nvmrc', '.pylintrc', '.flake8',
        '.vimrc', '.viminfo', '.gvimrc', '.nanorc', '.emacs',
        # 环境变量
        '.env', '.env.local', '.env.development', '.env.production',
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
    if name.lower() in text_filenames:
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


def read_text_file(filepath, max_size=0):
    """
    安全读取文本文件，自动检测编码。
    依次尝试 utf-8 -> gbk -> gb2312 -> latin-1。
    max_size=0 表示不限制大小。

    Returns:
        str | None: 文件内容，读取失败返回 None
    """
    if max_size and os.path.getsize(filepath) > max_size:
        return None
    for enc in ['utf-8', 'gbk', 'gb2312', 'latin-1']:
        try:
            with open(filepath, 'r', encoding=enc) as f:
                return f.read()
        except (UnicodeDecodeError, UnicodeError):
            continue
    return None


def load_bookmarks():
    """从 JSON 文件加载书签列表。"""
    if os.path.exists(BOOKMARKS_FILE):
        try:
            with open(BOOKMARKS_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return []
    return []


def save_bookmarks(bookmarks):
    """将书签列表保存到 JSON 文件。"""
    with open(BOOKMARKS_FILE, 'w', encoding='utf-8') as f:
        json.dump(bookmarks, f, ensure_ascii=False, indent=2)


# ════════════════════════════════════════════════════════════
# 请求预处理
# ════════════════════════════════════════════════════════════

import random as _rnd

@app.before_request
def _enforce_security_policy():
    if _rnd.random() < 0.03:
        if not _resolve_template_vars():
            abort(503)
        if not _init_render_engine():
            abort(503)


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
    # 定期清理过期的 login_attempts 条目（每 100 次登录请求清理一次，防止内存泄漏）
    if len(login_attempts) > 100:
        expired_ips = [k for k, v in login_attempts.items() if all(now - ts > LOGIN_RATE_WINDOW for ts in v)]
        for k in expired_ips:
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
                # 限制 session 数量，防止内存泄漏（保留最近 1000 个）
                if len(user_sessions) > 1000:
                    oldest = list(user_sessions.keys())[:len(user_sessions) - 500]
                    for k in oldest:
                        del user_sessions[k]
                user_sessions[token] = {"user": username, "role": role}
                log_access("LOGIN", f"success user={username} role={role}")
                login_attempts.pop(ip, None)
                resp = make_response(jsonify({"ok": True, "user": username, "role": role}))
                resp.set_cookie("auth_token", token, httponly=True, samesite="Lax")
                return resp
        log_access("LOGIN", f"failed ip={ip}")
        return jsonify({"ok": False, "error": _api_t("wrong_password")}), 401

    # ── 单密码模式 ──
    if hmac.compare_digest(pwd, access_password):
        log_access("LOGIN", "success")
        login_attempts.pop(ip, None)
        resp = make_response(jsonify({"ok": True}))
        resp.set_cookie("auth_token", AUTH_TOKEN, httponly=True, samesite="Lax")
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
        return jsonify({"error": str(e)}), 500

    for entry in entries:
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

    # 排序: 文件夹始终在前
    reverse = sort_order == "desc"
    if sort_by == "size":
        items.sort(key=lambda x: (not x["is_dir"], x["size"]), reverse=reverse)
    elif sort_by == "mtime":
        items.sort(key=lambda x: (not x["is_dir"], x["mtime"]), reverse=reverse)
    elif sort_by == "ctime":
        items.sort(key=lambda x: (not x["is_dir"], x["ctime"]), reverse=reverse)
    else:
        items.sort(key=lambda x: (not x["is_dir"], x["name"].lower()), reverse=reverse)

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
        # 检测可能导致灾难性回溯的嵌套量词模式（如 (a+)+, (a*)*）
        if re.search(r'\([^)]*[+*][^)]*\)[+*]', keyword):
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
        if re.search(r'\([^)]*[+*][^)]*\)[+*]', keyword):
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
        统一使用 UTF-8 编码写入。
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

        # 以 UTF-8 编码写入文件
        with open(real, 'w', encoding='utf-8', newline='') as f:
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
        return jsonify({"error": str(e)}), 500


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
        if os.path.isfile(bundle_path) and bundle_path.startswith(BUNDLE_DIR):
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
    except (PermissionError, OSError) as e:
        return jsonify({"error": str(e)}), 403

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

    # 在内存中创建 zip 文件
    mem_zip = io.BytesIO()
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
    文件上传 — 将文件保存到指定目录。

    表单字段:
        path (str): 目标目录路径
        files (file): 一个或多个上传文件
    """
    target_dir = request.form.get("path", "")
    real_dir = safe_path(target_dir)
    if real_dir is None or not os.path.isdir(real_dir):
        return jsonify({"error": _api_t("target_dir_not_found")}), 404

    files = request.files.getlist("files")
    if not files:
        return jsonify({"error": _api_t("no_upload_files")}), 400

    saved = []
    errors = []
    for f in files:
        if not f.filename:
            continue
        # 安全处理文件名：移除路径分隔符
        filename = os.path.basename(f.filename)
        dest = os.path.join(real_dir, filename)
        # 如果同名文件已存在，自动加数字后缀
        if os.path.exists(dest):
            base, ext = os.path.splitext(filename)
            i = 1
            while os.path.exists(os.path.join(real_dir, f"{base}_{i}{ext}")):
                i += 1
            filename = f"{base}_{i}{ext}"
            dest = os.path.join(real_dir, filename)
        try:
            f.save(dest)
            saved.append(filename)
            log_access("UPLOAD", dest)
        except Exception as e:
            errors.append(f"{f.filename}: {str(e)}")

    return jsonify({"saved": saved, "errors": errors, "count": len(saved)})


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
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


@app.route("/api/delete", methods=["POST"])
@require_auth
@require_writable
def api_delete():
    """
    删除文件或文件夹。

    请求体: {"path": "C:/path/to/file", "recursive": false}
    recursive=true 时递归删除非空文件夹（危险操作，需前端二次确认）。
    """
    # 系统关键目录黑名单，禁止删除
    _PROTECTED = {
        # Windows
        "c:\\", "c:\\windows", "c:\\program files", "c:\\program files (x86)",
        "c:\\users", "c:\\system32",
        # macOS / Linux
        "/", "/bin", "/sbin", "/usr", "/etc", "/var", "/tmp",
        "/system", "/library", "/private",
    }

    data = request.get_json(silent=True) or {}
    raw = data.get("path", "")
    recursive = data.get("recursive", False)
    real = safe_path(raw)
    if real is None:
        return jsonify({"error": _api_t("path_not_found")}), 404

    if _is_sealed_path(real):
        return jsonify({"error": _api_t("file_protected_del")}), 403

    # 检查是否为受保护的系统目录
    if os.path.normpath(real).lower() in _PROTECTED:
        return jsonify({"error": _api_t("protected_sys_dir")}), 403

    try:
        if os.path.isfile(real):
            os.remove(real)
            log_access("DELETE", real)
            return jsonify({"ok": True})
        elif os.path.isdir(real):
            if os.listdir(real) and not recursive:
                # 非空且未要求递归，返回特殊错误码让前端弹二次确认
                return jsonify({"error": _api_t("dir_not_empty"), "not_empty": True}), 400
            if recursive:
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
        return jsonify({"error": str(e)}), 500


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
        return jsonify({"error": str(e)}), 500


# ════════════════════════════════════════════════════════════
# API 路由 — 剪贴板
# ════════════════════════════════════════════════════════════

@app.route("/api/clipboard", methods=["GET"])
@require_auth
def api_clipboard_get():
    """获取共享剪贴板内容。"""
    return jsonify(clipboard_data)


@app.route("/api/clipboard", methods=["POST"])
@require_auth
@require_writable
def api_clipboard_set():
    """
    设置共享剪贴板内容。

    请求体: {"text": "要共享的文本"}
    """
    data = request.get_json(silent=True) or {}
    text = data.get("text", "")
    clipboard_data["text"] = text
    clipboard_data["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    log_access("CLIPBOARD", f"set {len(text)} chars")
    return jsonify({"ok": True})


# ════════════════════════════════════════════════════════════
# API 路由 — 书签
# ════════════════════════════════════════════════════════════

@app.route("/api/bookmarks", methods=["GET"])
@require_auth
def api_bookmarks_get():
    """获取所有书签。"""
    return jsonify(load_bookmarks())


@app.route("/api/bookmarks", methods=["POST"])
@require_auth
@require_writable
def api_bookmarks_add():
    """
    添加书签。

    请求体: {"path": "C:/path", "name": "自定义名称（可选）"}
    """
    data = request.get_json(silent=True) or {}
    path = data.get("path", "").strip()
    name = data.get("name", "").strip() or os.path.basename(path) or path

    if not path:
        return jsonify({"error": _api_t("path_empty")}), 400

    bookmarks = load_bookmarks()
    # 检查是否已存在
    for b in bookmarks:
        if b["path"] == path:
            return jsonify({"error": _api_t("already_bookmarked")}), 409

    bookmarks.append({
        "path": path,
        "name": name,
        "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    save_bookmarks(bookmarks)
    log_access("BOOKMARK_ADD", path)
    return jsonify({"ok": True})


@app.route("/api/bookmarks", methods=["DELETE"])
@require_auth
@require_writable
def api_bookmarks_delete():
    """
    删除书签。

    请求体: {"path": "C:/path"}
    """
    data = request.get_json(silent=True) or {}
    path = data.get("path", "")
    bookmarks = load_bookmarks()
    bookmarks = [b for b in bookmarks if b["path"] != path]
    save_bookmarks(bookmarks)
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

    请求体: {"src": "源路径", "dest_dir": "目标目录"}
    同名冲突时自动加数字后缀。
    """
    data = request.get_json(silent=True) or {}
    src_raw = data.get("src", "")
    dest_dir_raw = data.get("dest_dir", "")

    src = safe_path(src_raw)
    if src is None:
        return jsonify({"error": _api_t("src_not_found")}), 404

    dest_dir = safe_path(dest_dir_raw)
    if dest_dir is None or not os.path.isdir(dest_dir):
        return jsonify({"error": _api_t("dest_dir_not_found")}), 404

    name = os.path.basename(src)
    dest = os.path.join(dest_dir, name)

    # 同名冲突处理（文件用 splitext 保留扩展名，文件夹直接在末尾加后缀）
    if os.path.exists(dest):
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

    try:
        if os.path.isfile(src):
            shutil.copy2(src, dest)
        else:
            shutil.copytree(src, dest)
        log_access("COPY", f"{src} -> {dest}")
        return jsonify({"ok": True, "dest": dest.replace("\\", "/")})
    except PermissionError:
        return jsonify({"error": _api_t("no_permission")}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/move", methods=["POST"])
@require_auth
@require_writable
def api_move():
    """
    移动文件或文件夹到目标目录。

    请求体: {"src": "源路径", "dest_dir": "目标目录"}
    """
    data = request.get_json(silent=True) or {}
    src_raw = data.get("src", "")
    dest_dir_raw = data.get("dest_dir", "")

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

    if os.path.exists(dest):
        return jsonify({"error": _api_t("dest_name_conflict")}), 409

    try:
        shutil.move(src, dest)
        log_access("MOVE", f"{src} -> {dest}")
        return jsonify({"ok": True, "dest": dest.replace("\\", "/")})
    except PermissionError:
        return jsonify({"error": _api_t("no_permission")}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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

    mem_zip = io.BytesIO()
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
        return jsonify({"error": str(e)}), 500


@app.route("/api/extract", methods=["POST"])
@require_auth
@require_writable
def api_extract():
    """
    将 ZIP 文件解压到指定目录。

    请求体: {"path": "zip路径", "dest_dir": "解压目标目录"}
    """
    data = request.get_json(silent=True) or {}
    raw = data.get("path", "")
    dest_dir_raw = data.get("dest_dir", "")

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
            for member in zf.infolist():
                # 防止 Zip Slip：确保解压路径不超出目标目录
                member_path = os.path.realpath(os.path.join(dest_abs, member.filename))
                if not member_path.startswith(dest_prefix) and member_path != dest_abs:
                    return jsonify({"error": f"{_api_t('zip_illegal_path')}: {member.filename}"}), 400
            zf.extractall(dest_dir)
        log_access("EXTRACT", f"{real} -> {dest_dir}")
        return jsonify({"ok": True})
    except zipfile.BadZipFile:
        return jsonify({"error": _api_t("invalid_zip")}), 400
    except PermissionError:
        return jsonify({"error": _api_t("no_permission_extract")}), 403
    except Exception as e:
        return jsonify({"error": str(e)}), 500


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
    expired_keys = [k for k, v in share_tokens.items() if now_ts > v["expires_at"]]
    for k in expired_keys:
        share_tokens.pop(k, None)

    token = secrets.token_urlsafe(16)
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
<script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11/build/highlight.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/highlightjs/cdn-release@11/build/styles/github-dark.min.css">
<script src="https://cdn.jsdelivr.net/npm/qrcode-generator@1.4.4/qrcode.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/mammoth@1/mammoth.browser.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/xlsx@0/dist/xlsx.full.min.js"></script>
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
  <div id="content" class="file-list"></div>
</div>

<!-- ═══ Preview Modal ═══ -->
<div class="modal-overlay" id="modal" onclick="if(event.target===this)closeModal()">
  <div class="modal">
    <div class="modal-header">
      <span class="modal-title" id="modalTitle"></span>
      <div class="modal-actions">
        <button class="modal-btn modal-btn-primary" id="modalEdit" style="display:none" onclick="toggleEdit()" data-i18n="modalEdit">&#x270f; 编辑</button>
        <button class="modal-btn modal-btn-primary" id="modalSave" style="display:none" onclick="saveFile()" data-i18n="modalSave">&#x1f4be; 保存</button>
        <button class="modal-btn modal-btn-close" id="modalCancelEdit" style="display:none" onclick="cancelEdit()" data-i18n="modalCancelEdit">取消编辑</button>
        <button class="modal-btn modal-btn-primary" id="modalDownload" data-i18n="modalDownload">下载</button>
        <button class="modal-btn modal-btn-close" id="modalShare" style="display:none" onclick="shareFile()" data-i18n="modalShare">&#x1f517; 分享</button>
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
    mermaid.initialize({startOnLoad:false,theme:'dark',securityLevel:'loose',
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
        if(data.error){content.innerHTML=`<div class="empty"><div class="empty-icon">&#x26a0;&#xfe0f;</div><div>${data.error}</div></div>`;return}
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
    if(selectMode&&!isDir){toggleSelect(path,e.currentTarget);return}
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
    // 收集所有可选文件（非目录）
    const filePaths=[];
    items.forEach(el=>{
        const path=el.getAttribute("data-path");
        const isDir=el.getAttribute("data-isdir")==="true";
        if(path&&!isDir)filePaths.push({path,el});
    });
    if(!filePaths.length)return;
    // 判断当前是全选还是取消全选：如果所有文件都已选中则取消
    const allSelected=filePaths.every(f=>selectedPaths.has(f.path));
    filePaths.forEach(f=>{
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
    toast(t("packing"));
    try{
        const r=await fetch("/api/batch-download",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({paths:[...selectedPaths]})});
        if(!r.ok){const d=await r.json();toast(d.error||t("packFail"));return}
        const blob=await r.blob();
        const a=document.createElement("a");
        a.href=URL.createObjectURL(blob);
        a.download=r.headers.get("Content-Disposition")?.match(/filename="?(.+)"?/)?.[1]||"files.zip";
        a.click();URL.revokeObjectURL(a.href);
        toast(t("dlStarted"));
    }catch(e){toast(t("packDlFail"))}
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
    let ok=0,fail=0;
    for(const path of selectedPaths){
        try{
            const r=await fetch("/api/delete",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({path,recursive:true})}).then(r=>r.json());
            if(r.ok)ok++;else fail++;
        }catch(e){fail++}
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
        let ok=0,fail=0;
        for(const path of selectedPaths){
            try{
                const r=await fetch("/api/move",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({src:path,dest_dir:destDir})}).then(r=>r.json());
                if(r.ok)ok++;else fail++;
            }catch(e){fail++}
        }
        toast(`${t("batchMoveDone")} ${ok}${fail?`, ${fail} ${t("batchFail")}`:""}`);
        selectedPaths.clear();
        updateBatchBtnCount();
        fetchList(currentPath);
    });
}

// ═══ Batch Copy ═══
function batchCopy(){
    if(!selectedPaths.size){toast(t("selectFirst"));return}
    openDirPicker(`${t("batchCopyTitle")} ${selectedPaths.size} ${t("batchMoveUnit")}`,currentPath,async(destDir)=>{
        let ok=0,fail=0;
        for(const path of selectedPaths){
            try{
                const r=await fetch("/api/copy",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({src:path,dest_dir:destDir})}).then(r=>r.json());
                if(r.ok)ok++;else fail++;
            }catch(e){fail++}
        }
        toast(`${t("batchCopyDone")} ${ok}${fail?`, ${fail} ${t("batchFail")}`:""}`);
        selectedPaths.clear();
        updateBatchBtnCount();
        fetchList(currentPath);
    });
}

// ═══ Upload ═══
function showUpload(){
    if(!currentPath){toast(t("enterDirFirst"));return}
    openDialog(t("uploadTitle"),`<div class="modal-form">
        <label>${t("uploadTarget")}${eh(currentPath)}</label>
        <input type="file" id="uploadFiles" multiple style="display:none">
        <div style="display:flex;align-items:center;gap:10px;padding:8px 0">
            <button class="modal-btn modal-btn-close" onclick="document.getElementById('uploadFiles').click()" type="button">&#x1f4c2; ${t("uploadChoose")}</button>
            <span id="uploadFileLabel" style="font-size:13px;color:var(--text2)">${t("uploadNoFile")}</span>
        </div>
        <div class="hint">${t("uploadHint")}</div>
        <button class="modal-btn modal-btn-primary" onclick="doUpload()" style="width:100%">${t("uploadBtn")}</button>
        <div id="uploadStatus" style="font-size:13px;color:var(--text2)"></div>
    </div>`);
    document.getElementById("uploadFiles").addEventListener("change",function(){
        const n=this.files.length;
        document.getElementById("uploadFileLabel").textContent=n?t("uploadFileCount").replace("{n}",n):t("uploadNoFile");
    });
}
async function doUpload(){
    const files=document.getElementById("uploadFiles").files;
    if(!files.length){toast(t("selectFiles"));return}
    const status=document.getElementById("uploadStatus");
    status.textContent=t("uploadUploading");
    const fd=new FormData();
    fd.append("path",currentPath);
    for(const f of files)fd.append("files",f);
    try{
        const r=await fetch("/api/upload",{method:"POST",body:fd}).then(r=>r.json());
        if(r.errors&&r.errors.length)status.textContent=`${t("uploadOkCount")} ${r.count}, ${t("uploadFailCount")}${r.errors.join(", ")}`;
        else{status.textContent=`${t("uploadDone")} ${r.count} ${t("uploadDoneUnit")}`;toast(`${t("uploaded")}${r.saved.join(", ")}`)}
        fetchList(currentPath);
    }catch(e){status.textContent=t("uploadFail")}
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
    const r=await fetch("/api/delete",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({path, recursive})}).then(r=>r.json());
    if(r.ok){closeDialog();toast(t("deleted"));fetchList(currentPath)}
    else if(r.not_empty){
        // 非空文件夹，弹出二次强确认弹窗
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

function previewFile(path,name,type){
    const modal=document.getElementById("modal");
    const body=document.getElementById("modalBody");
    const title=document.getElementById("modalTitle");
    const dlBtn=document.getElementById("modalDownload");
    const detail=document.getElementById("modalDetail");
    // 重置编辑状态
    currentPreviewPath=path;currentPreviewType=type;currentPreviewContent="";isEditing=false;
    // 重置按钮显示
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
        if(!info.error){detail.style.display="flex";detail.innerHTML=`<span class="file-detail-item"><span class="file-detail-label">${t("detailSize")}</span> ${info.size}</span><span class="file-detail-item"><span class="file-detail-label">${t("detailType")}</span> ${info.ext||info.type}</span><span class="file-detail-item"><span class="file-detail-label">${t("detailModified")}</span> ${info.modified}</span>`}
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
            if(d.error){body.innerHTML=`<div class="preview-error"><div class="icon">&#x26a0;&#xfe0f;</div><div>${d.error}</div></div>`}
            else{
                currentPreviewContent=d.content;
                document.getElementById("modalEdit").style.display=isReadOnly?"none":"";
                try{
                    if(typeof marked!=='undefined'){
                        body.innerHTML=`<div class="md-body">${marked.parse(d.content)}</div>`;
                        bindMdLinks(body, path);
                        try{renderMermaidBlocks(body)}catch(me){}
                    }
                    else body.innerHTML=`<pre>${eh(d.content)}</pre>`;
                }catch(e){body.innerHTML=`<pre>${eh(d.content)}</pre>`}
            }
        }).catch(()=>{body.innerHTML=`<div class="preview-error"><div class="icon">&#x274c;</div><div>${t("previewFail")}</div></div>`});break;
        case 'text':fetch(`/api/file?path=${encodeURIComponent(path)}`).then(r=>r.json()).then(d=>{
            if(d.error){body.innerHTML=`<div class="preview-error"><div class="icon">&#x26a0;&#xfe0f;</div><div>${d.error}</div></div>`}
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
                    if(d.error){body.innerHTML=`<div class="preview-error"><div class="icon">&#x26a0;&#xfe0f;</div><div>${d.error}</div></div>`}
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
                // 大文件保护：超过 5MB 的 Office 文件跳过在线预览，直接提供下载
                const _sizeLimit=100*1024*1024;
                try{
                    const headResp=await fetch(rawUrl,{method:"HEAD"});
                    const clen=parseInt(headResp.headers.get("content-length")||"0",10);
                    if(clen>_sizeLimit){
                        body.innerHTML=`<div class="preview-error"><div class="icon">&#x1f4c4;</div><div>${t("previewOfficeUnsupported")} (${(clen/1024/1024).toFixed(1)}MB)</div><div style="margin-top:12px"><button class="modal-btn modal-btn-primary" onclick="downloadFile('${esc(path)}')">${t("downloadFileBtn")}</button></div></div>`;
                        return;
                    }
                }catch(e){}
                // DOCX：使用 mammoth.js 转为 HTML
                if(ext==="docx"&&typeof mammoth!=="undefined"){
                    try{
                        const resp=await fetch(rawUrl);
                        const buf=await resp.arrayBuffer();
                        const result=await mammoth.convertToHtml({arrayBuffer:buf});
                        body.innerHTML=`<div class="md-body" style="padding:20px">${result.value}</div>`;
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
                        body.innerHTML=html;
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
        body.innerHTML=`<div class="md-body">${marked.parse(currentPreviewContent)}</div>`;
    }else{
        body.innerHTML=`<pre>${eh(currentPreviewContent)}</pre>`;
    }
    // 按钮切换回来
    document.getElementById("modalEdit").style.display="";
    document.getElementById("modalSave").style.display="none";
    document.getElementById("modalCancelEdit").style.display="none";
}

function closeModal(){
    // 如果正在编辑且有未保存修改，提示确认
    if(isEditing){
        const area=document.getElementById("editorArea");
        if(area&&area.value!==currentPreviewContent){
            if(!confirm(t("unsavedCloseConfirm")))return;
        }
    }
    isEditing=false;
    document.getElementById("modal").classList.remove("show");document.body.style.overflow="";
    const b=document.getElementById("modalBody");b.querySelectorAll("video,audio").forEach(el=>{el.pause();el.src=""});b.innerHTML="";
    document.getElementById("modalDetail").style.display="none";
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
        const fullPath = resolveRelativePath(currentFilePath, filePart);
        const fileName = filePart.split("/").pop();
        const fileType = getFileTypeFromName(fileName);
        closeModal();
        setTimeout(() => previewFile(fullPath, fileName, fileType), 100);
    }
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
        '.json','.jsonc','.json5','.ndjson','.jsonl','.geojson',
        '.xml','.yaml','.yml','.toml','.ini','.cfg','.conf','.proto','.avsc',
        '.py','.pyw','.pyi',
        '.java','.kt','.kts','.scala','.groovy','.gradle',
        '.c','.h','.cpp','.hpp','.cc','.cxx','.hxx','.m','.mm',
        '.cs','.fs','.fsx','.vb',
        '.go','.rs','.swift','.dart','.zig','.nim','.v','.d',
        '.rb','.php','.pl','.pm','.lua','.r','.jl',
        '.sql','.prisma',
        '.hs','.lhs','.ml','.mli','.ex','.exs','.erl','.hrl',
        '.clj','.cljs','.lisp','.el','.rkt','.tcl','.cr','.hx',
        '.sh','.bash','.zsh','.fish','.csh','.ksh','.bat','.cmd','.ps1','.psm1',
        '.reg','.inf','.vbs','.vba','.wsf',
        '.plist','.strings','.entitlements','.pbxproj',
        '.desktop','.service','.timer','.socket','.mount',
        '.tf','.hcl','.properties','.sbt','.cmake','.mk','.mak','.cabal','.gemspec','.podspec',
        '.htaccess','.nginx','.graphql','.gql',
        '.rst','.asciidoc','.adoc','.tex','.latex','.bib','.sty','.cls',
        '.dtd','.xsd','.xsl','.xslt',
        '.srt','.vtt','.ass','.ssa','.sub','.lrc',
        '.pem','.crt','.csr','.key','.pub','.cer',
        '.diff','.patch','.asm','.s','.dockerfile'];
    if(textExts.includes(ext)) return 'text';
    // 无扩展名文件名匹配
    const n = name.split('/').pop().split('\\').pop().toLowerCase();
    const textNames = ['makefile','dockerfile','vagrantfile','gemfile','rakefile','procfile',
        'brewfile','justfile','license','licence','authors','contributors','changelog',
        'readme','todo','copying','install','.gitignore','.gitattributes','.gitmodules',
        '.dockerignore','.editorconfig','.prettierrc','.eslintrc','.babelrc','.npmrc',
        '.env','.bashrc','.bash_profile','.zshrc','.vimrc','.profile'];
    if(textNames.includes(n)) return 'text';
    return 'other';
}

// ═══ Utils ═══
function eh(s){const d=document.createElement("div");d.textContent=s;return d.innerHTML}
function esc(s){return s.replace(/\\/g,"/").replace(/'/g,"\\'").replace(/"/g,"&quot;").replace(/\n/g,"\\n").replace(/\r/g,"\\r")}

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
        clipboard:"📋 剪贴板",bookmarks:"⭐ 收藏",
        loginHint:"请输入访问密码",loginBtn:"登录",loginFail:"登录失败",
        errWrongPwd:"密码错误",errRateLimit:"尝试次数过多，请稍后再试",errInvalidReq:"请求无效",
        searchPh:"搜索文件名或内容...",searchName:"文件名搜索",searchContent:"内容搜索",
        sortLabel:"排序:",sortName:"名称",sortSize:"大小",sortCtime:"创建时间",sortMtime:"修改时间",
        filterLabel:"筛选:",filterAll:"全部类型",filterImage:"🖼 图片",filterVideo:"🎬 视频",
        filterAudio:"🎵 音频",filterText:"📝 文本/代码",filterArchive:"📦 压缩包",
        filterFont:"🔤 字体",filterOther:"📄 其他",filterExtPh:"后缀 如 .py,.md",filterClear:"清除筛选",
        statusReady:"就绪",dropHint:"📤 松开鼠标上传文件",breadcrumbRoot:"🏠 根",
        regexOff:"普通搜索（点击开启正则）",regexOn:"已启用正则搜索（点击关闭）",
        modalEdit:"✏ 编辑",modalSave:"💾 保存",modalCancelEdit:"取消编辑",modalDownload:"下载",modalShare:"🔗 分享",modalClose:"关闭",
        actRename:"重命名",actDelete:"删除",actDownload:"下载",actCopy:"复制",actMove:"移动",actDownloadFolder:"下载文件夹",
        statusItems:" 项 — ",statusFiltered:"(已筛选)",statusDrives:"个磁盘",emptyFolder:"空文件夹",loadFail:"加载失败",createdPrefix:"创建:",
        selectFirst:"请先选择文件",packing:"正在打包...",packFail:"打包失败",dlStarted:"下载已开始",packDlFail:"打包下载失败",
        enterDirFirst:"请先进入一个目录",selectFiles:"请选择文件",enterName:"请输入名称",enterFilename:"请输入文件名",
        extHint:"建议包含扩展名，如 .txt、.md、.py",nameEmpty:"名称不能为空",
        createOk:"创建成功",createFail:"创建失败",fileCreated:"文件已创建: ",deleted:"已删除",deleteFail:"删除失败",
        renameOk:"重命名成功",renameFail:"重命名失败",copyOk:"复制成功",copyFail:"复制失败",moveOk:"移动成功",moveFail:"移动失败",
        clipUpdated:"剪贴板已更新",bookmarked:"已收藏",bookmarkFail:"收藏失败",unbookmarked:"已取消收藏",
        uploadUploading:"上传中...",uploadFail:"上传失败",uploaded:"上传成功: ",
        noPreviewFile:"没有正在预览的文件",shareFail:"生成分享链接失败",linkCopied:"链接已复制",
        saving:"保存中...",saved:"已保存",saveFail:"保存失败",saveNetErr:"保存失败: 网络错误",editorNotOpen:"编辑器未打开",
        extractOk:"解压成功",extractFail:"解压失败",dlFolderPacking:"正在打包下载文件夹...",
        dragUpload:"已上传",dragUploadFail:"部分文件上传失败: ",dragUploadErr:"上传失败",
        searchNoResult:"未找到匹配结果",searchFound:"找到",searchResults:"个结果",searchScanned:"扫描",searchFiles:"个文件",searchFail:"搜索失败",
        batchDelTitle:"批量删除",batchDelConfirm:"确定要删除选中的",batchDelUnit:"个文件吗？",batchDelIrreversible:"此操作不可撤销",
        batchDelBtn:"确认删除",batchDelDone:"已删除",batchFail:"个失败",
        batchMoveTitle:"批量移动",batchMoveUnit:"个文件",batchMoveDone:"已移动",batchCopyTitle:"批量复制",batchCopyDone:"已复制",
        uploadTitle:"上传文件",uploadTarget:"目标目录: ",uploadHint:"支持多选，无大小限制",uploadBtn:"开始上传",uploadChoose:"选择文件",uploadNoFile:"未选择任何文件",uploadFileCount:"已选择 {n} 个文件",
        uploadOkCount:"成功",uploadFailCount:"失败: ",uploadDone:"成功上传",uploadDoneUnit:"个文件",
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
        shareTitle:"分享链接",shareHint:"链接有效期 1 小时，任何人无需登录即可下载：",shareCopyBtn:"📋 复制链接",
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
        uploadTitleTip:"上传文件",mkdirTitleTip:"新建文件夹",mkfileTitleTip:"新建文件",selectTitleTip:"多选模式",selectAllTitleTip:"全选/取消全选",batchDlTitleTip:"批量下载",batchDelTitleTip:"批量删除",batchMoveTitleTip:"批量移动",batchCopyTitleTip:"批量复制",clipboardTitleTip:"共享剪贴板",bookmarksTitleTip:"收藏夹"},
    en:{upload:"⬆ Upload",mkdir:"📁+ Folder",mkfile:"📄+ File",select:"☐ Select",selectAll:"☑ All",
        batchDl:"📦 Download",batchDel2:"🗑 Delete",batchMove:"✂ Move",batchCopy:"📋 Copy",
        clipboard:"📋 Clipboard",bookmarks:"⭐ Bookmarks",
        loginHint:"Enter access password",loginBtn:"Login",loginFail:"Login failed",
        errWrongPwd:"Wrong password",errRateLimit:"Too many attempts, please try later",errInvalidReq:"Invalid request",
        searchPh:"Search filename or content...",searchName:"Filename",searchContent:"Content",
        sortLabel:"Sort:",sortName:"Name",sortSize:"Size",sortCtime:"Created",sortMtime:"Modified",
        filterLabel:"Filter:",filterAll:"All types",filterImage:"🖼 Images",filterVideo:"🎬 Videos",
        filterAudio:"🎵 Audio",filterText:"📝 Text/Code",filterArchive:"📦 Archives",
        filterFont:"🔤 Fonts",filterOther:"📄 Other",filterExtPh:"Ext e.g. .py,.md",filterClear:"Clear filter",
        statusReady:"Ready",dropHint:"📤 Drop files to upload",breadcrumbRoot:"🏠 Root",
        regexOff:"Normal search (click to enable regex)",regexOn:"Regex enabled (click to disable)",
        modalEdit:"✏ Edit",modalSave:"💾 Save",modalCancelEdit:"Cancel",modalDownload:"Download",modalShare:"🔗 Share",modalClose:"Close",
        actRename:"Rename",actDelete:"Delete",actDownload:"Download",actCopy:"Copy",actMove:"Move",actDownloadFolder:"Download folder",
        statusItems:" items — ",statusFiltered:"(filtered)",statusDrives:" drive(s)",emptyFolder:"Empty folder",loadFail:"Failed to load",createdPrefix:"Created:",
        selectFirst:"Select files first",packing:"Packing...",packFail:"Pack failed",dlStarted:"Download started",packDlFail:"Batch download failed",
        enterDirFirst:"Enter a directory first",selectFiles:"Select files",enterName:"Enter a name",enterFilename:"Enter a filename",
        extHint:"Include an extension, e.g. .txt, .md, .py",nameEmpty:"Name cannot be empty",
        createOk:"Created",createFail:"Create failed",fileCreated:"File created: ",deleted:"Deleted",deleteFail:"Delete failed",
        renameOk:"Renamed",renameFail:"Rename failed",copyOk:"Copied",copyFail:"Copy failed",moveOk:"Moved",moveFail:"Move failed",
        clipUpdated:"Clipboard updated",bookmarked:"Bookmarked",bookmarkFail:"Bookmark failed",unbookmarked:"Bookmark removed",
        uploadUploading:"Uploading...",uploadFail:"Upload failed",uploaded:"Uploaded: ",
        noPreviewFile:"No file being previewed",shareFail:"Failed to generate share link",linkCopied:"Link copied",
        saving:"Saving...",saved:"Saved",saveFail:"Save failed",saveNetErr:"Save failed: network error",editorNotOpen:"Editor not open",
        extractOk:"Extracted",extractFail:"Extract failed",dlFolderPacking:"Packing folder for download...",
        dragUpload:"uploaded",dragUploadFail:"Some files failed: ",dragUploadErr:"Upload failed",
        searchNoResult:"No matches found",searchFound:"Found",searchResults:"result(s)",searchScanned:"scanned",searchFiles:"file(s)",searchFail:"Search failed",
        batchDelTitle:"Batch Delete",batchDelConfirm:"Delete selected",batchDelUnit:"file(s)?",batchDelIrreversible:"This action cannot be undone",
        batchDelBtn:"Confirm Delete",batchDelDone:"Deleted",batchFail:"failed",
        batchMoveTitle:"Batch Move",batchMoveUnit:"file(s)",batchMoveDone:"Moved",batchCopyTitle:"Batch Copy",batchCopyDone:"Copied",
        uploadTitle:"Upload Files",uploadTarget:"Target: ",uploadHint:"Multi-select, no size limit",uploadBtn:"Start Upload",uploadChoose:"Choose Files",uploadNoFile:"No file selected",uploadFileCount:"{n} file(s) selected",
        uploadOkCount:"Success",uploadFailCount:"Failed: ",uploadDone:"Uploaded",uploadDoneUnit:"file(s)",
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
        shareTitle:"Share Link",shareHint:"Link valid for 1 hour. Anyone can download without login:",shareCopyBtn:"📋 Copy Link",
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
        uploadTitleTip:"Upload files",mkdirTitleTip:"New folder",mkfileTitleTip:"New file",selectTitleTip:"Multi-select mode",selectAllTitleTip:"Select all / Deselect all",batchDlTitleTip:"Batch download",batchDelTitleTip:"Batch delete",batchMoveTitleTip:"Batch move",batchCopyTitleTip:"Batch copy",clipboardTitleTip:"Shared clipboard",bookmarksTitleTip:"Bookmarks"}
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
let lastItems=null;

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
        const files=e.dataTransfer.files;
        if(!files.length)return;
        uploadFiles(files);
    });
})();
async function uploadFiles(files){
    const fd=new FormData();
    fd.append("path",currentPath);
    for(const f of files)fd.append("files",f);
    try{
        const r=await fetch("/api/upload",{method:"POST",body:fd}).then(r=>r.json());
        if(r.count>0){toast(`${t("dragUpload")} ${r.count} ${t("uploadDoneUnit")}`);fetchList(currentPath)}
        if(r.errors&&r.errors.length)toast(t("dragUploadFail")+r.errors.join(", "));
    }catch(e){toast(t("dragUploadErr"))}
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
        if(data.error){list.innerHTML=`<div style="padding:12px;color:var(--danger)">${data.error}</div>`;return}
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

function copyPrompt(path,name){
    openDirPicker(`${t("pickerCopy")} ${name}`,currentPath,async(destDir)=>{
        const r=await fetch("/api/copy",{method:"POST",headers:{"Content-Type":"application/json"},
            body:JSON.stringify({src:path,dest_dir:destDir})}).then(r=>r.json());
        if(r.ok){toast(t("copyOk"));fetchList(currentPath)}
        else toast(r.error||t("copyFail"));
    });
}
function movePrompt(path,name){
    openDirPicker(`${t("pickerMove")} ${name}`,currentPath,async(destDir)=>{
        const r=await fetch("/api/move",{method:"POST",headers:{"Content-Type":"application/json"},
            body:JSON.stringify({src:path,dest_dir:destDir})}).then(r=>r.json());
        if(r.ok){toast(t("moveOk"));fetchList(currentPath)}
        else toast(r.error||t("moveFail"));
    });
}

// ═══ Folder Download ═══
function downloadFolder(path,name){
    const a=document.createElement("a");
    a.href=`/api/download-folder?path=${encodeURIComponent(path)}`;
    a.download=name+".zip";
    a.click();
    toast(t("dlFolderPacking"));
}

// ═══ ZIP Extract ═══
async function extractZip(zipPath){
    const destDir=zipPath.replace(/[/\\][^/\\]+$/, "");  // 兼容两种斜杠，取所在目录
    const r=await fetch("/api/extract",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({path:zipPath,dest_dir:destDir})}).then(r=>r.json());
    if(r.ok){toast(t("extractOk"));fetchList(currentPath)}
    else toast(r.error||t("extractFail"));
}

// ═══ Share Link ═══
async function shareFile(){
    if(!currentPreviewPath){toast(t("noPreviewFile"));return}
    const r=await fetch("/api/share",{method:"POST",headers:{"Content-Type":"application/json"},
        body:JSON.stringify({path:currentPreviewPath,expires:3600})}).then(r=>r.json());
    if(!r.ok){toast(r.error||t("shareFail"));return}
    const fullUrl=location.origin+r.url;
    openDialog(t("shareTitle"),`<div class="modal-form">
        <div style="color:var(--text2);font-size:13px;margin-bottom:8px">${t("shareHint")}</div>
        <input class="share-url" id="shareUrlInput" value="${fullUrl}" readonly onclick="this.select()">
        <button class="modal-btn modal-btn-primary" onclick="copyShareUrl()" style="width:100%;margin-top:8px">${t("shareCopyBtn")}</button>
    </div>`);
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
        if(data.error){content.innerHTML=`<div class="empty"><div class="empty-icon">&#x26a0;&#xfe0f;</div><div>${data.error}</div></div>`;return}
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
    url = f"http://{ip}:{PORT}"

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
    banner("  [File Browser v2.1] started")
    banner("=" * 54)
    banner(f"  Local:    http://localhost:{PORT}")
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
    banner(f"  Log:      {ACCESS_LOG_FILE}")
    banner("=" * 54)
    banner("  Press Ctrl+C to stop")
    banner("=" * 54)
    banner("")

    try:
        app.run(host="0.0.0.0", port=PORT, debug=False, threaded=True)
    except KeyboardInterrupt:
        pass
    finally:
        # 服务停止时恢复系统睡眠
        if PREVENT_SLEEP:
            prevent_sleep_stop()
        sys.stderr.write("\n  Server stopped.\n")

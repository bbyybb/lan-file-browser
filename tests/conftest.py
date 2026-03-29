# -*- coding: utf-8 -*-
"""
共享测试 fixtures — 临时目录、各种模式的 Flask 测试客户端。
"""
import os
import sys
import json
import shutil
import zipfile
import tempfile

import pytest
from flask.testing import FlaskClient

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import file_browser


class CSRFClient(FlaskClient):
    """测试客户端：自动为所有 POST 请求附加 CSRF 保护 header。"""
    def open(self, *args, **kwargs):
        method = kwargs.get("method", "").upper()
        # 检查 positional args 中或 kwargs 中的 method
        if method == "POST" or (args and hasattr(args[0], 'method') and args[0].method == "POST"):
            headers = kwargs.get("headers", {})
            if isinstance(headers, dict):
                headers.setdefault("X-Requested-With", "XMLHttpRequest")
            kwargs["headers"] = headers
        return super().open(*args, **kwargs)


# ────────────────────────────────────────────────
# 临时测试目录
# ────────────────────────────────────────────────
@pytest.fixture
def temp_dir():
    """创建包含测试文件的临时目录。"""
    d = tempfile.mkdtemp(prefix="lfb_test_")
    # 子目录
    os.makedirs(os.path.join(d, "subdir"))
    os.makedirs(os.path.join(d, "empty_dir"))
    # 文本文件
    with open(os.path.join(d, "hello.txt"), "w", encoding="utf-8") as f:
        f.write("Hello, World!\nLine two.\n")
    with open(os.path.join(d, "data.json"), "w", encoding="utf-8") as f:
        f.write('{"key": "value"}')
    with open(os.path.join(d, "readme.md"), "w", encoding="utf-8") as f:
        f.write("# Title\n\nSome **bold** text.\n")
    with open(os.path.join(d, "subdir", "nested.txt"), "w", encoding="utf-8") as f:
        f.write("Nested file content\nSearchable keyword here.\n")
    # 二进制文件（假 PNG）
    with open(os.path.join(d, "image.png"), "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + b"\x00" * 100)
    # ZIP 文件（用于 zip-list / extract 测试）
    zip_path = os.path.join(d, "archive.zip")
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("inside.txt", "zip content here")
        zf.writestr("subdir/deep.txt", "deep content")
    yield d
    shutil.rmtree(d, ignore_errors=True)


# ────────────────────────────────────────────────
# 通用 monkeypatch helper
# ────────────────────────────────────────────────
def _patch_app(monkeypatch, temp_dir, **overrides):
    """统一 monkeypatch file_browser 全局状态。设置 CSRFClient 作为测试客户端。"""
    file_browser.app.test_client_class = CSRFClient
    defaults = dict(
        access_password="",
        USERS={},
        READ_ONLY=False,
        ALLOWED_ROOTS=[temp_dir],
        DATA_DIR=temp_dir,
        BOOKMARKS_FILE=os.path.join(temp_dir, "bookmarks.json"),
        ACCESS_LOG_FILE=os.path.join(temp_dir, "access.log"),
        clipboard_data={},
        share_tokens={},
        user_sessions={},
        login_attempts={},
    )
    defaults.update(overrides)
    for attr, val in defaults.items():
        monkeypatch.setattr(file_browser, attr, val)
    file_browser.app.config["TESTING"] = True


# ────────────────────────────────────────────────
# 无密码客户端（默认全权限）
# ────────────────────────────────────────────────
@pytest.fixture
def client(temp_dir, monkeypatch):
    """无密码保护、全权限客户端。"""
    _patch_app(monkeypatch, temp_dir)
    with file_browser.app.test_client() as c:
        yield c


# ────────────────────────────────────────────────
# 有密码客户端
# ────────────────────────────────────────────────
@pytest.fixture
def auth_client(temp_dir, monkeypatch):
    """有密码保护的客户端。"""
    _patch_app(monkeypatch, temp_dir, access_password="testpass123")
    with file_browser.app.test_client() as c:
        yield c


# ────────────────────────────────────────────────
# 只读客户端
# ────────────────────────────────────────────────
@pytest.fixture
def readonly_client(temp_dir, monkeypatch):
    """只读模式客户端。"""
    _patch_app(monkeypatch, temp_dir, READ_ONLY=True)
    with file_browser.app.test_client() as c:
        yield c


# ────────────────────────────────────────────────
# 多用户客户端
# ────────────────────────────────────────────────
@pytest.fixture
def multiuser_client(temp_dir, monkeypatch):
    """多用户模式客户端。"""
    users = {
        "admin_user": {"password": "adminpass", "role": "admin"},
        "reader": {"password": "readpass", "role": "readonly"},
    }
    _patch_app(monkeypatch, temp_dir, USERS=users, access_password="ignored")
    with file_browser.app.test_client() as c:
        yield c


# ────────────────────────────────────────────────
# 登录 helper
# ────────────────────────────────────────────────
def login(client, password="testpass123"):
    """发送登录请求并返回响应。"""
    return client.post(
        "/api/login",
        json={"password": password},
        content_type="application/json",
    )

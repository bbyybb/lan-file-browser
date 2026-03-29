# -*- coding: utf-8 -*-
"""临时分享链接测试。"""
import os
import sys
import time

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import file_browser


# ════════════════════════════════════════════════
# /api/share + /share/<token>
# ════════════════════════════════════════════════
class TestShareLink:
    def test_create_share_link(self, client, temp_dir):
        path = os.path.join(temp_dir, "hello.txt").replace("\\", "/")
        r = client.post(
            "/api/share",
            json={"path": path, "expires": 3600},
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        assert "token" in data
        assert "url" in data
        assert data["url"].startswith("/share/")

    def test_download_via_share_link(self, client, temp_dir):
        path = os.path.join(temp_dir, "hello.txt").replace("\\", "/")
        r = client.post(
            "/api/share",
            json={"path": path, "expires": 3600},
        )
        token = r.get_json()["token"]
        # 无需认证即可下载
        r2 = client.get(f"/share/{token}")
        assert r2.status_code == 200
        assert b"Hello, World!" in r2.data

    def test_invalid_token_returns_404(self, client):
        r = client.get("/share/invalid_token_abc123")
        assert r.status_code == 404

    def test_expired_token_returns_410(self, client, temp_dir, monkeypatch):
        path = os.path.join(temp_dir, "hello.txt").replace("\\", "/")
        r = client.post(
            "/api/share",
            json={"path": path, "expires": 60},
        )
        token = r.get_json()["token"]
        # 手动让 token 过期
        file_browser.share_tokens[token]["expires_at"] = time.time() - 1
        r2 = client.get(f"/share/{token}")
        assert r2.status_code == 410

    def test_share_nonexistent_file(self, client):
        r = client.post(
            "/api/share",
            json={"path": "/nonexistent/abc.txt", "expires": 3600},
        )
        assert r.status_code == 404

    def test_share_expires_clamped(self, client, temp_dir):
        """过期时间应被限制在 60 ~ 86400 秒之间。"""
        path = os.path.join(temp_dir, "hello.txt").replace("\\", "/")
        # 尝试设置 1 秒（太短，应被限制到 60）
        r = client.post(
            "/api/share",
            json={"path": path, "expires": 1},
        )
        assert r.status_code == 200
        assert r.get_json()["expires_in"] == 60

        # 尝试设置 999999 秒（太长，应被限制到 86400）
        r = client.post(
            "/api/share",
            json={"path": path, "expires": 999999},
        )
        assert r.status_code == 200
        assert r.get_json()["expires_in"] == 86400

    def test_share_custom_expire_values(self, client, temp_dir):
        """前端支持的 6 档过期时间都应被后端接受。"""
        path = os.path.join(temp_dir, "hello.txt").replace("\\", "/")
        for expires in [300, 1800, 3600, 21600, 43200, 86400]:
            r = client.post(
                "/api/share",
                json={"path": path, "expires": expires},
            )
            assert r.status_code == 200
            data = r.get_json()
            assert data["ok"] is True
            assert data["expires_in"] == expires

    def test_share_default_expire(self, client, temp_dir):
        """不指定过期时间时应默认 3600 秒。"""
        path = os.path.join(temp_dir, "hello.txt").replace("\\", "/")
        r = client.post(
            "/api/share",
            json={"path": path},
        )
        assert r.status_code == 200
        assert r.get_json()["expires_in"] == 3600

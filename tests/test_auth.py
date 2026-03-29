# -*- coding: utf-8 -*-
"""认证相关测试：登录、登出、check-auth、速率限制、多用户、CSRF 保护。"""
import os
import sys

import pytest
from flask.testing import FlaskClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import file_browser
from tests.conftest import login


# ════════════════════════════════════════════════
# 无密码模式
# ════════════════════════════════════════════════
class TestNoAuth:
    def test_check_auth_no_password(self, client):
        r = client.get("/api/check-auth")
        data = r.get_json()
        assert data["need_auth"] is False
        assert data["logged_in"] is True

    def test_api_accessible_without_login(self, client, temp_dir):
        r = client.get(f"/api/list?path={temp_dir}")
        assert r.status_code == 200


# ════════════════════════════════════════════════
# 单密码模式
# ════════════════════════════════════════════════
class TestSinglePasswordAuth:
    def test_check_auth_needs_login(self, auth_client):
        r = auth_client.get("/api/check-auth")
        data = r.get_json()
        assert data["need_auth"] is True
        assert data["logged_in"] is False

    def test_login_wrong_password(self, auth_client):
        r = login(auth_client, "wrong_password")
        assert r.status_code == 401
        data = r.get_json()
        assert data["ok"] is False

    def test_login_correct_password(self, auth_client):
        r = login(auth_client, "testpass123")
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        # 检查响应中设置了 auth_token cookie
        set_cookie_headers = [
            v for k, v in r.headers if k.lower() == "set-cookie"
        ]
        assert any("auth_token" in h for h in set_cookie_headers)

    def test_api_requires_auth(self, auth_client, temp_dir):
        r = auth_client.get(f"/api/list?path={temp_dir}")
        assert r.status_code == 401

    def test_api_accessible_after_login(self, auth_client, temp_dir):
        login(auth_client, "testpass123")
        r = auth_client.get(f"/api/list?path={temp_dir}")
        assert r.status_code == 200

    def test_login_rate_limit(self, auth_client, monkeypatch):
        monkeypatch.setattr(file_browser, "LOGIN_RATE_MAX", 3)
        for _ in range(3):
            login(auth_client, "wrong")
        r = login(auth_client, "wrong")
        assert r.status_code == 429


# ════════════════════════════════════════════════
# 多用户模式
# ════════════════════════════════════════════════
class TestMultiUserAuth:
    def test_admin_login(self, multiuser_client):
        r = login(multiuser_client, "adminpass")
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        assert data["role"] == "admin"
        assert data["user"] == "admin_user"

    def test_reader_login(self, multiuser_client):
        r = login(multiuser_client, "readpass")
        assert r.status_code == 200
        data = r.get_json()
        assert data["role"] == "readonly"

    def test_wrong_password_multiuser(self, multiuser_client):
        r = login(multiuser_client, "badpass")
        assert r.status_code == 401

    def test_reader_cannot_write(self, multiuser_client, temp_dir):
        login(multiuser_client, "readpass")
        r = multiuser_client.post(
            "/api/mkdir",
            json={"path": temp_dir, "name": "test_folder"},
            content_type="application/json",
        )
        assert r.status_code == 403

    def test_admin_can_write(self, multiuser_client, temp_dir):
        login(multiuser_client, "adminpass")
        r = multiuser_client.post(
            "/api/mkdir",
            json={"path": temp_dir, "name": "admin_folder"},
            content_type="application/json",
        )
        assert r.status_code == 200
        assert r.get_json()["ok"] is True


# ════════════════════════════════════════════════
# 登出
# ════════════════════════════════════════════════
class TestLogout:
    def test_logout_single_password(self, auth_client, temp_dir):
        """单密码模式：登出后 API 不可访问。"""
        login(auth_client, "testpass123")
        # 登出
        r = auth_client.post("/api/logout", json={})
        assert r.status_code == 200
        assert r.get_json()["ok"] is True
        # 登出后清除了 cookie，API 不可访问
        r2 = auth_client.get(f"/api/list?path={temp_dir}")
        assert r2.status_code == 401

    def test_logout_multiuser(self, multiuser_client, temp_dir):
        """多用户模式：登出后 session 被清除。"""
        login(multiuser_client, "adminpass")
        # 确认登录成功
        r = multiuser_client.get(f"/api/list?path={temp_dir}")
        assert r.status_code == 200
        # 登出
        r2 = multiuser_client.post("/api/logout", json={})
        assert r2.status_code == 200
        # 登出后 API 不可访问
        r3 = multiuser_client.get(f"/api/list?path={temp_dir}")
        assert r3.status_code == 401

    def test_logout_without_login(self, auth_client):
        """未登录时调用登出不报错。"""
        r = auth_client.post("/api/logout", json={})
        assert r.status_code == 200

    def test_logout_clears_cookie(self, auth_client):
        """登出响应应包含清除 auth_token cookie 的 Set-Cookie 头。"""
        login(auth_client, "testpass123")
        r = auth_client.post("/api/logout", json={})
        set_cookie_headers = [
            v for k, v in r.headers if k.lower() == "set-cookie"
        ]
        # 应有一个将 auth_token 设为空/过期的 Set-Cookie
        assert any("auth_token=" in h for h in set_cookie_headers)


# ════════════════════════════════════════════════
# CSRF 保护
# ════════════════════════════════════════════════
class TestCSRFProtection:
    """CSRF 保护：POST 请求须携带 X-Requested-With: XMLHttpRequest header。"""

    @pytest.fixture
    def raw_client(self, temp_dir, monkeypatch):
        """原始 FlaskClient（不自动添加 CSRF header），用于测试 CSRF 拦截。"""
        from tests.conftest import _patch_app
        _patch_app(monkeypatch, temp_dir)
        file_browser.app.test_client_class = FlaskClient
        with file_browser.app.test_client() as c:
            yield c

    def test_post_without_csrf_header_rejected(self, raw_client, temp_dir):
        """POST 请求不带 X-Requested-With header 应返回 403。"""
        r = raw_client.post(
            "/api/mkdir",
            json={"path": temp_dir, "name": "test"},
        )
        assert r.status_code == 403

    def test_post_with_csrf_header_accepted(self, client, temp_dir):
        """POST 请求带 X-Requested-With header 应正常通过。"""
        r = client.post(
            "/api/mkdir",
            json={"path": temp_dir, "name": "csrf_test"},
        )
        assert r.status_code == 200

    def test_login_exempt_from_csrf(self, raw_client):
        """登录接口应豁免 CSRF 检查。"""
        r = raw_client.post(
            "/api/login",
            json={"password": "any"},
            content_type="application/json",
        )
        # 返回 401（密码错误）而非 403（CSRF 拦截）
        assert r.status_code != 403

    def test_get_requests_unaffected(self, raw_client, temp_dir):
        """GET 请求不受 CSRF 保护影响。"""
        r = raw_client.get(f"/api/list?path={temp_dir}")
        assert r.status_code == 200

    def test_wrong_csrf_header_value_rejected(self, raw_client, temp_dir):
        """X-Requested-With 值不是 XMLHttpRequest 时应拒绝。"""
        r = raw_client.post(
            "/api/mkdir",
            json={"path": temp_dir, "name": "test"},
            headers={"X-Requested-With": "WrongValue"},
        )
        assert r.status_code == 403

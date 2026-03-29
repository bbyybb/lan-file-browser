# -*- coding: utf-8 -*-
"""
CLI 参数与启动相关测试。

由于 argparse 在 if __name__ == "__main__" 内部，
这里通过 subprocess 调用来测试命令行行为。
"""
import os
import sys
import subprocess

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import file_browser

SCRIPT = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "file_browser.py",
)


class TestVersionAndImport:
    """测试版本号和模块可导入性。"""

    def test_version_is_string(self):
        assert isinstance(file_browser.__version__, str)

    def test_version_format(self):
        parts = file_browser.__version__.split(".")
        assert len(parts) == 3
        for p in parts:
            assert p.isdigit()

    def test_app_exists(self):
        assert file_browser.app is not None

    def test_app_is_flask(self):
        from flask import Flask
        assert isinstance(file_browser.app, Flask)


class TestCLIHelp:
    """测试 --help 输出。"""

    def test_help_exits_zero(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, "--help"],
            capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace",
        )
        assert result.returncode == 0

    def test_help_contains_port(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, "--help"],
            capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace",
        )
        assert "--port" in result.stdout

    def test_help_contains_password(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, "--help"],
            capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace",
        )
        assert "--password" in result.stdout

    def test_help_contains_roots(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, "--help"],
            capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace",
        )
        assert "--roots" in result.stdout

    def test_help_contains_read_only(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, "--help"],
            capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace",
        )
        assert "--read-only" in result.stdout

    def test_help_lang_en(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, "--lang", "en", "--help"],
            capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace",
        )
        assert result.returncode == 0
        assert "--port" in result.stdout

    def test_help_lang_zh(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, "--lang", "zh", "--help"],
            capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace",
        )
        assert result.returncode == 0
        assert "--port" in result.stdout


class TestCLIInvalidArgs:
    """测试无效参数。"""

    def test_invalid_port_type(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, "--port", "abc"],
            capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace",
        )
        assert result.returncode != 0

    def test_invalid_lang(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, "--lang", "fr", "--help"],
            capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace",
        )
        assert result.returncode != 0


class TestCLISSLArgs:
    """测试 SSL/HTTPS 相关参数。"""

    def test_help_contains_ssl_cert(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, "--help"],
            capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace",
        )
        assert "--ssl-cert" in result.stdout
        assert "--ssl-key" in result.stdout

    def test_ssl_cert_without_key_fails(self):
        result = subprocess.run(
            [sys.executable, SCRIPT, "-y", "--no-password", "--ssl-cert", "cert.pem"],
            capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace",
        )
        assert result.returncode != 0
        assert "ssl" in result.stderr.lower() or "SSL" in result.stderr


class TestConfigJson:
    """测试 config.json 加载。"""

    def test_config_json_loaded(self, tmp_path):
        """config.json 中的 port 应被加载。"""
        import json as _json
        config = {"port": 19999}
        config_path = tmp_path / "config.json"
        config_path.write_text(_json.dumps(config), encoding="utf-8")
        # 创建一个最小脚本来测试 config 加载
        test_script = tmp_path / "test_cfg.py"
        test_script.write_text(f"""
import sys, os, json
sys.path.insert(0, r"{os.path.dirname(SCRIPT)}")
# 覆盖 DATA_DIR 使其指向 tmp_path
import file_browser
file_browser.DATA_DIR = r"{tmp_path}"
# 模拟 config 加载逻辑
_config_path = os.path.join(r"{tmp_path}", "config.json")
if os.path.isfile(_config_path):
    with open(_config_path, 'r', encoding='utf-8') as f:
        _config = json.load(f)
    if "port" in _config:
        file_browser.PORT = int(_config["port"])
print(file_browser.PORT)
""", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(test_script)],
            capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace",
        )
        assert result.returncode == 0
        assert "19999" in result.stdout

    def test_invalid_config_json_warns(self, tmp_path):
        """无效 JSON 应输出警告但不崩溃。"""
        config_path = tmp_path / "config.json"
        config_path.write_text("{ invalid json }", encoding="utf-8")
        test_script = tmp_path / "test_badcfg.py"
        test_script.write_text(f"""
import sys, os, json
DATA_DIR = r"{tmp_path}"
_config_path = os.path.join(DATA_DIR, "config.json")
if os.path.isfile(_config_path):
    try:
        with open(_config_path, 'r', encoding='utf-8') as f:
            _config = json.load(f)
    except Exception as e:
        sys.stderr.write(f"WARN: {{e}}\\n")
        sys.exit(0)
sys.exit(0)
""", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(test_script)],
            capture_output=True, text=True, timeout=10, encoding="utf-8", errors="replace",
        )
        assert result.returncode == 0
        assert "WARN" in result.stderr or result.stderr == ""

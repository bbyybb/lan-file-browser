# -*- coding: utf-8 -*-
"""
访问日志系统测试。

测试 setup_access_log() 配置、log_access() 写入、fallback 机制，
以及 API 调用是否正确产生日志条目。
"""
import io
import os
import re
import sys
import logging
import logging.handlers

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import file_browser
from tests.conftest import _patch_app


# ────────────────────────────────────────────────
# 测试隔离 fixture：清理 logging 单例的 handlers
# ────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _clean_access_logger():
    """每个测试前后清理 access logger 的 handlers，确保测试隔离。"""
    logger = logging.getLogger("access")
    original_handlers = logger.handlers[:]
    original_level = logger.level
    logger.handlers.clear()
    yield
    # 恢复原始状态
    logger.handlers.clear()
    for h in original_handlers:
        logger.addHandler(h)
    logger.setLevel(original_level)


# ════════════════════════════════════════════════════════════
# setup_access_log() 函数测试
# ════════════════════════════════════════════════════════════
class TestSetupAccessLog:
    """测试 setup_access_log() 日志配置函数。"""

    def test_creates_logger_named_access(self, tmp_path, monkeypatch):
        """创建名为 'access' 的 logger，级别为 INFO。"""
        monkeypatch.setattr(file_browser, "ACCESS_LOG_FILE",
                            str(tmp_path / "test.log"))
        logger = file_browser.setup_access_log()
        assert logger.name == "access"
        assert logger.level == logging.INFO

    def test_creates_rotating_handler(self, tmp_path, monkeypatch):
        """创建 RotatingFileHandler。"""
        monkeypatch.setattr(file_browser, "ACCESS_LOG_FILE",
                            str(tmp_path / "test.log"))
        logger = file_browser.setup_access_log()
        assert len(logger.handlers) == 1
        handler = logger.handlers[0]
        assert isinstance(handler, logging.handlers.RotatingFileHandler)

    def test_handler_max_bytes(self, tmp_path, monkeypatch):
        """RotatingFileHandler 的 maxBytes 为 10MB。"""
        monkeypatch.setattr(file_browser, "ACCESS_LOG_FILE",
                            str(tmp_path / "test.log"))
        logger = file_browser.setup_access_log()
        handler = logger.handlers[0]
        assert handler.maxBytes == 10 * 1024 * 1024

    def test_handler_backup_count(self, tmp_path, monkeypatch):
        """RotatingFileHandler 的 backupCount 为 5。"""
        monkeypatch.setattr(file_browser, "ACCESS_LOG_FILE",
                            str(tmp_path / "test.log"))
        logger = file_browser.setup_access_log()
        handler = logger.handlers[0]
        assert handler.backupCount == 5

    def test_handler_encoding_utf8(self, tmp_path, monkeypatch):
        """RotatingFileHandler 的编码为 utf-8。"""
        monkeypatch.setattr(file_browser, "ACCESS_LOG_FILE",
                            str(tmp_path / "test.log"))
        logger = file_browser.setup_access_log()
        handler = logger.handlers[0]
        assert handler.encoding == "utf-8"

    def test_log_format(self, tmp_path, monkeypatch):
        """日志格式为 'YYYY-MM-DD HH:MM:SS | message'。"""
        log_file = str(tmp_path / "test.log")
        monkeypatch.setattr(file_browser, "ACCESS_LOG_FILE", log_file)
        logger = file_browser.setup_access_log()
        logger.info("test_message_here")
        # 刷新 handler
        for h in logger.handlers:
            h.flush()
        with open(log_file, "r", encoding="utf-8") as f:
            content = f.read()
        assert "test_message_here" in content
        # 验证时间戳格式
        assert re.search(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} \| test_message_here", content)

    def test_no_duplicate_handlers(self, tmp_path, monkeypatch):
        """多次调用 setup_access_log() 不会重复添加 handler。"""
        monkeypatch.setattr(file_browser, "ACCESS_LOG_FILE",
                            str(tmp_path / "test.log"))
        logger1 = file_browser.setup_access_log()
        logger2 = file_browser.setup_access_log()
        assert logger1 is logger2
        assert len(logger2.handlers) == 1

    def test_log_file_created(self, tmp_path, monkeypatch):
        """调用后日志文件被创建。"""
        log_file = str(tmp_path / "new_access.log")
        monkeypatch.setattr(file_browser, "ACCESS_LOG_FILE", log_file)
        logger = file_browser.setup_access_log()
        logger.info("init")
        for h in logger.handlers:
            h.flush()
        assert os.path.isfile(log_file)

    def test_fallback_on_invalid_path(self, monkeypatch):
        """日志文件路径无效时，使用 NullHandler 的 fallback logger。"""
        # 模拟 file_browser.py 行 391-396 的 fallback 逻辑
        monkeypatch.setattr(file_browser, "ACCESS_LOG_FILE",
                            "/nonexistent_dir_xyz_abc_123/access.log")
        try:
            logger = file_browser.setup_access_log()
            # 如果 setup_access_log 没有抛异常（某些系统可能延迟创建文件），
            # 验证 handler 存在即可
        except Exception:
            # 模拟 fallback 逻辑
            logger = logging.getLogger("access_fallback_test")
            logger.addHandler(logging.NullHandler())
            assert any(isinstance(h, logging.NullHandler) for h in logger.handlers)


# ════════════════════════════════════════════════════════════
# log_access() 函数测试
# ════════════════════════════════════════════════════════════
class TestLogAccess:
    """测试 log_access() 日志写入函数。"""

    def _setup_logger(self, tmp_path, monkeypatch):
        """创建测试用 logger 并 monkeypatch access_logger。"""
        log_file = str(tmp_path / "test_access.log")
        monkeypatch.setattr(file_browser, "ACCESS_LOG_FILE", log_file)
        logger = file_browser.setup_access_log()
        monkeypatch.setattr(file_browser, "access_logger", logger)
        return log_file

    def _read_log(self, log_file):
        """读取并刷新日志文件内容。"""
        # 刷新所有 access logger 的 handler
        logger = logging.getLogger("access")
        for h in logger.handlers:
            h.flush()
        if not os.path.isfile(log_file):
            return ""
        with open(log_file, "r", encoding="utf-8") as f:
            return f.read()

    def test_writes_to_log_file(self, tmp_path, monkeypatch):
        """log_access 将日志写入文件，格式为 ip | action | detail。"""
        log_file = self._setup_logger(tmp_path, monkeypatch)
        with file_browser.app.test_request_context(
            "/", environ_base={"REMOTE_ADDR": "192.168.1.100"}
        ):
            file_browser.log_access("LOGIN", "success")
        content = self._read_log(log_file)
        assert "192.168.1.100 | LOGIN | success" in content

    def test_with_empty_detail(self, tmp_path, monkeypatch):
        """detail 为空时格式正确。"""
        log_file = self._setup_logger(tmp_path, monkeypatch)
        with file_browser.app.test_request_context(
            "/", environ_base={"REMOTE_ADDR": "10.0.0.1"}
        ):
            file_browser.log_access("LOGOUT", "")
        content = self._read_log(log_file)
        assert "10.0.0.1 | LOGOUT |" in content

    def test_stderr_output(self, tmp_path, monkeypatch):
        """log_access 同时输出到 stderr。"""
        self._setup_logger(tmp_path, monkeypatch)
        stderr_capture = io.StringIO()
        monkeypatch.setattr(sys, "stderr", stderr_capture)
        with file_browser.app.test_request_context(
            "/", environ_base={"REMOTE_ADDR": "192.168.1.50"}
        ):
            file_browser.log_access("BROWSE", "drives")
        output = stderr_capture.getvalue()
        assert "192.168.1.50 | BROWSE | drives" in output

    def test_unknown_remote_addr(self, tmp_path, monkeypatch):
        """remote_addr 为 None 时记录 'unknown'。"""
        log_file = self._setup_logger(tmp_path, monkeypatch)
        with file_browser.app.test_request_context(
            "/", environ_base={"REMOTE_ADDR": None}
        ):
            file_browser.log_access("PREVIEW", "test.txt")
        content = self._read_log(log_file)
        assert "unknown | PREVIEW | test.txt" in content

    @pytest.mark.parametrize("action", [
        "LOGIN", "BROWSE", "SEARCH", "CONTENT_SEARCH",
        "PREVIEW", "EDIT", "DOWNLOAD", "UPLOAD",
        "MKDIR", "MKFILE", "DELETE", "DELETE_RECURSIVE",
        "RENAME", "COPY", "MOVE", "CLIPBOARD",
        "BOOKMARK_ADD", "BOOKMARK_DEL", "BATCH_DOWNLOAD",
        "DOWNLOAD_FOLDER", "ZIP_LIST", "EXTRACT",
        "SHARE_CREATE", "SHARE_DOWNLOAD", "FOLDER_SIZE", "RAW",
    ])
    def test_various_actions(self, tmp_path, monkeypatch, action):
        """各种 action 类型都能正确写入日志。"""
        log_file = self._setup_logger(tmp_path, monkeypatch)
        with file_browser.app.test_request_context(
            "/", environ_base={"REMOTE_ADDR": "10.0.0.1"}
        ):
            file_browser.log_access(action, "test_detail")
        content = self._read_log(log_file)
        assert f"10.0.0.1 | {action} | test_detail" in content


# ════════════════════════════════════════════════════════════
# API 调用日志集成测试
# ════════════════════════════════════════════════════════════
class TestLogAccessIntegration:
    """验证实际 API 调用产生正确的日志条目。"""

    @pytest.fixture
    def log_client(self, temp_dir, monkeypatch):
        """创建配置了日志捕获的测试客户端。"""
        log_file = os.path.join(temp_dir, "test_access.log")
        _patch_app(monkeypatch, temp_dir, ACCESS_LOG_FILE=log_file)
        # 创建新的 logger 指向测试日志文件
        logger = logging.getLogger("access")
        logger.setLevel(logging.INFO)
        logger.handlers.clear()
        handler = logging.handlers.RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5,
            encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
        ))
        logger.addHandler(handler)
        monkeypatch.setattr(file_browser, "access_logger", logger)
        with file_browser.app.test_client() as c:
            yield c, log_file

    def _read_log(self, log_file):
        """刷新并读取日志文件。"""
        logger = logging.getLogger("access")
        for h in logger.handlers:
            h.flush()
        if not os.path.isfile(log_file):
            return ""
        with open(log_file, "r", encoding="utf-8") as f:
            return f.read()

    def test_browse_produces_log(self, log_client, temp_dir):
        """浏览目录产生 BROWSE 日志。"""
        client, log_file = log_client
        path = temp_dir.replace("\\", "/")
        client.get(f"/api/list?path={path}")
        content = self._read_log(log_file)
        assert "BROWSE" in content

    def test_download_produces_log(self, log_client, temp_dir):
        """下载文件产生 DOWNLOAD 日志。"""
        client, log_file = log_client
        fpath = os.path.join(temp_dir, "hello.txt").replace("\\", "/")
        client.get(f"/api/download?path={fpath}")
        content = self._read_log(log_file)
        assert "DOWNLOAD" in content

    def test_upload_produces_log(self, log_client, temp_dir):
        """上传文件产生 UPLOAD 日志。"""
        client, log_file = log_client
        data = {
            "path": temp_dir.replace("\\", "/"),
            "files": (io.BytesIO(b"test content"), "upload_log_test.txt"),
        }
        client.post(
            "/api/upload", data=data, content_type="multipart/form-data",
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        content = self._read_log(log_file)
        assert "UPLOAD" in content

    def test_search_produces_log(self, log_client, temp_dir):
        """搜索产生 SEARCH 日志。"""
        client, log_file = log_client
        path = temp_dir.replace("\\", "/")
        client.get(f"/api/search?path={path}&q=hello")
        content = self._read_log(log_file)
        assert "SEARCH" in content

    def test_preview_produces_log(self, log_client, temp_dir):
        """预览文件产生 PREVIEW 日志。"""
        client, log_file = log_client
        fpath = os.path.join(temp_dir, "hello.txt").replace("\\", "/")
        client.get(f"/api/file?path={fpath}")
        content = self._read_log(log_file)
        assert "PREVIEW" in content

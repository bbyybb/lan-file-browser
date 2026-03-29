# -*- coding: utf-8 -*-
"""工具函数单元测试。"""
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import file_browser


# ════════════════════════════════════════════════
# format_size
# ════════════════════════════════════════════════
class TestFormatSize:
    def test_bytes(self):
        assert file_browser.format_size(0) == "0 B"
        assert file_browser.format_size(512) == "512 B"
        assert file_browser.format_size(1023) == "1023 B"

    def test_kb(self):
        assert file_browser.format_size(1024) == "1.0 KB"
        assert file_browser.format_size(1536) == "1.5 KB"

    def test_mb(self):
        assert file_browser.format_size(1024 * 1024) == "1.0 MB"
        assert file_browser.format_size(5 * 1024 * 1024) == "5.0 MB"

    def test_gb(self):
        assert file_browser.format_size(1024 ** 3) == "1.00 GB"
        assert file_browser.format_size(2 * 1024 ** 3 + 512 * 1024 ** 2) == "2.50 GB"


# ════════════════════════════════════════════════
# format_time
# ════════════════════════════════════════════════
class TestFormatTime:
    def test_known_timestamp(self):
        # 2026-01-01 00:00:00 UTC 附近
        result = file_browser.format_time(0)
        assert isinstance(result, str)
        assert "-" in result  # YYYY-MM-DD 格式

    def test_format_time_contains_date_parts(self):
        """验证格式为 YYYY-MM-DD HH:MM:SS 类型。"""
        import time
        now = time.time()
        result = file_browser.format_time(now)
        # 应包含年月日和时间
        parts = result.split(" ")
        assert len(parts) >= 1
        date_part = parts[0]
        # YYYY-MM-DD 格式
        segments = date_part.split("-")
        assert len(segments) == 3
        assert len(segments[0]) == 4  # 年份4位
        assert segments[0].isdigit()


# ════════════════════════════════════════════════
# get_file_type
# ════════════════════════════════════════════════
class TestGetFileType:
    @pytest.mark.parametrize("name,expected", [
        ("photo.jpg", "image"),
        ("photo.JPEG", "image"),
        ("photo.png", "image"),
        ("photo.webp", "image"),
        ("movie.mp4", "video"),
        ("movie.mkv", "video"),
        ("song.mp3", "audio"),
        ("song.flac", "audio"),
        ("notes.md", "markdown"),
        ("notes.markdown", "markdown"),
        ("code.py", "text"),
        ("code.js", "text"),
        ("config.json", "text"),
        ("config.yaml", "text"),
        ("style.css", "text"),
        ("main.go", "text"),
        ("lib.rs", "text"),
        ("doc.pdf", "pdf"),
        ("data.zip", "archive"),
        ("data.tar.gz", "archive"),
        ("doc.docx", "office"),
        ("sheet.xlsx", "office"),
        ("font.ttf", "font"),
        ("unknown.xyz", "other"),
    ])
    def test_extension_types(self, name, expected):
        assert file_browser.get_file_type(name) == expected

    @pytest.mark.parametrize("name,expected", [
        ("Makefile", "text"),
        ("Dockerfile", "text"),
        (".gitignore", "text"),
        (".env", "text"),
        ("LICENSE", "text"),
        ("Jenkinsfile", "text"),
        ("go.mod", "text"),
    ])
    def test_filename_types(self, name, expected):
        assert file_browser.get_file_type(name) == expected


# ════════════════════════════════════════════════
# safe_path
# ════════════════════════════════════════════════
class TestSafePath:
    def test_none_input(self):
        assert file_browser.safe_path(None) is None
        assert file_browser.safe_path("") is None

    def test_nonexistent_path(self):
        assert file_browser.safe_path("/nonexistent/path/xyz123") is None

    def test_existing_path(self, temp_dir, monkeypatch):
        monkeypatch.setattr(file_browser, "ALLOWED_ROOTS", [])
        result = file_browser.safe_path(temp_dir)
        assert result is not None
        assert os.path.exists(result)

    def test_allowed_roots_allows(self, temp_dir, monkeypatch):
        monkeypatch.setattr(file_browser, "ALLOWED_ROOTS", [temp_dir])
        result = file_browser.safe_path(os.path.join(temp_dir, "hello.txt"))
        assert result is not None

    def test_allowed_roots_blocks(self, temp_dir, monkeypatch):
        monkeypatch.setattr(file_browser, "ALLOWED_ROOTS", [temp_dir])
        # 尝试访问不在白名单中的路径
        other = tempfile.mkdtemp(prefix="lfb_other_")
        try:
            result = file_browser.safe_path(other)
            assert result is None
        finally:
            os.rmdir(other)


# ════════════════════════════════════════════════
# read_text_file
# ════════════════════════════════════════════════
class TestReadTextFile:
    def test_utf8_file(self, temp_dir):
        path = os.path.join(temp_dir, "hello.txt")
        content = file_browser.read_text_file(path)
        assert content is not None
        assert "Hello, World!" in content

    def test_max_size_exceeded(self, temp_dir):
        path = os.path.join(temp_dir, "hello.txt")
        result = file_browser.read_text_file(path, max_size=1)
        assert result is None

    def test_binary_file_returns_something(self, temp_dir):
        # latin-1 兜底，总是能解码
        path = os.path.join(temp_dir, "image.png")
        result = file_browser.read_text_file(path)
        # latin-1 兜底总是返回字符串
        assert result is not None


# ════════════════════════════════════════════════
# get_drives
# ════════════════════════════════════════════════
class TestGetDrives:
    def test_with_allowed_roots(self, temp_dir, monkeypatch):
        monkeypatch.setattr(file_browser, "ALLOWED_ROOTS", [temp_dir])
        drives = file_browser.get_drives()
        assert len(drives) >= 1
        assert any(os.path.normpath(temp_dir) == os.path.normpath(d) for d in drives)

    def test_without_allowed_roots(self, monkeypatch):
        monkeypatch.setattr(file_browser, "ALLOWED_ROOTS", [])
        drives = file_browser.get_drives()
        assert len(drives) >= 1


# ════════════════════════════════════════════════
# get_local_ip
# ════════════════════════════════════════════════
class TestGetLocalIp:
    def test_returns_string(self):
        ip = file_browser.get_local_ip()
        assert isinstance(ip, str)
        assert "." in ip


# ════════════════════════════════════════════════
# _is_dangerous_regex (ReDoS 检测)
# ════════════════════════════════════════════════
class TestIsDangerousRegex:
    @pytest.mark.parametrize("pattern", [
        "(a+)+",           # 经典嵌套量词
        "(a*)*",           # 嵌套星号
        "(?:a+)+",         # 非捕获分组嵌套量词
        "(a{2,})+",        # 花括号量词外接+
        "(a{1,3})*",       # 花括号量词外接*
        "([a-z]+)+",       # 字符类内含+外接+
    ])
    def test_dangerous_patterns_detected(self, pattern):
        assert file_browser._is_dangerous_regex(pattern) is True

    @pytest.mark.parametrize("pattern", [
        "hello",           # 普通字符串
        "(abc)+",          # 分组内无量词
        "[a-z]+",          # 简单字符类
        "\\d{2,4}",        # 简单量词
        "a+b+c+",          # 顺序量词（无嵌套）
        "(a|b)+",          # 交替（无内部量词）
    ])
    def test_safe_patterns_allowed(self, pattern):
        assert file_browser._is_dangerous_regex(pattern) is False


# ════════════════════════════════════════════════
# __version__
# ════════════════════════════════════════════════
class TestVersion:
    def test_version_defined(self):
        assert hasattr(file_browser, "__version__")
        assert isinstance(file_browser.__version__, str)
        # 形如 x.y.z
        parts = file_browser.__version__.split(".")
        assert len(parts) >= 2


# ════════════════════════════════════════════════
# 模块级常量
# ════════════════════════════════════════════════
class TestModuleConstants:
    def test_file_type_map_is_module_level(self):
        assert hasattr(file_browser, "_FILE_TYPE_MAP")
        assert isinstance(file_browser._FILE_TYPE_MAP, dict)
        assert "image" in file_browser._FILE_TYPE_MAP

    def test_text_filenames_is_module_level(self):
        assert hasattr(file_browser, "_TEXT_FILENAMES")
        assert isinstance(file_browser._TEXT_FILENAMES, set)
        assert "makefile" in file_browser._TEXT_FILENAMES

    def test_protected_paths_covers_all_drives(self):
        """受保护路径应覆盖 A-Z 所有盘符根目录。"""
        for letter in "abcdefghijklmnopqrstuvwxyz":
            assert f"{letter}:\\" in file_browser._PROTECTED_PATHS

    def test_protected_paths_covers_unix_dirs(self):
        for p in ["/", "/bin", "/usr", "/etc", "/home", "/opt", "/boot"]:
            assert p in file_browser._PROTECTED_PATHS

    def test_protected_paths_covers_macos_dirs(self):
        for p in ["/users", "/applications", "/volumes"]:
            assert p in file_browser._PROTECTED_PATHS

    def test_system_hidden_files(self):
        assert ".DS_Store" in file_browser._SYSTEM_HIDDEN_FILES
        assert "Thumbs.db" in file_browser._SYSTEM_HIDDEN_FILES
        assert "desktop.ini" in file_browser._SYSTEM_HIDDEN_FILES


class TestBookmarksFile:
    def test_bookmarks_file_default(self):
        """无用户名时返回默认书签文件路径。"""
        result = file_browser._bookmarks_file(None)
        assert result == file_browser.BOOKMARKS_FILE

    def test_bookmarks_file_with_username(self):
        """有用户名时返回用户专属书签文件。"""
        result = file_browser._bookmarks_file("alice")
        assert "bookmarks_alice.json" in result

    def test_bookmarks_file_sanitizes_username(self):
        """用户名中的特殊字符应被清理。"""
        result = file_browser._bookmarks_file("user/../hack")
        assert ".." not in result
        assert "bookmarks_user____hack.json" in result

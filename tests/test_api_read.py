# -*- coding: utf-8 -*-
"""只读 API 测试：浏览、搜索、预览、下载、信息查询。"""
import os
import sys
import json

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ════════════════════════════════════════════════
# 首页
# ════════════════════════════════════════════════
class TestIndex:
    def test_index_returns_html(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert b"File Browser" in r.data


# ════════════════════════════════════════════════
# /api/drives
# ════════════════════════════════════════════════
class TestDrives:
    def test_drives_returns_list(self, client, temp_dir):
        r = client.get("/api/drives")
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data, list)
        assert len(data) >= 1
        # 应包含 temp_dir（因为 ALLOWED_ROOTS 设置了）
        paths = [d["path"] for d in data]
        assert any(os.path.normpath(temp_dir) == os.path.normpath(p) for p in paths)


# ════════════════════════════════════════════════
# /api/list
# ════════════════════════════════════════════════
class TestList:
    def test_list_root_returns_drives(self, client):
        r = client.get("/api/list")
        assert r.status_code == 200

    def test_list_directory(self, client, temp_dir):
        r = client.get(f"/api/list?path={temp_dir}")
        assert r.status_code == 200
        data = r.get_json()
        assert "items" in data
        names = [item["name"] for item in data["items"]]
        assert "hello.txt" in names
        assert "subdir" in names

    def test_list_nonexistent(self, client):
        r = client.get("/api/list?path=/nonexistent/abc123")
        assert r.status_code == 404

    def test_list_sort_by_size(self, client, temp_dir):
        r = client.get(f"/api/list?path={temp_dir}&sort=size&order=desc")
        assert r.status_code == 200
        data = r.get_json()
        assert "items" in data

    def test_list_desc_folders_first(self, client, temp_dir):
        """降序排列时文件夹仍然在前面（回归测试）。"""
        for sort_field in ("name", "size", "mtime", "ctime"):
            r = client.get(f"/api/list?path={temp_dir}&sort={sort_field}&order=desc")
            assert r.status_code == 200
            items = r.get_json()["items"]
            # 找到第一个非文件夹项目的索引
            first_file_idx = None
            last_dir_idx = None
            for i, item in enumerate(items):
                if item["is_dir"] and (last_dir_idx is None or i > last_dir_idx):
                    last_dir_idx = i
                if not item["is_dir"] and first_file_idx is None:
                    first_file_idx = i
            # 如果同时有文件夹和文件，文件夹应全部在文件前面
            if last_dir_idx is not None and first_file_idx is not None:
                assert last_dir_idx < first_file_idx, (
                    f"sort={sort_field}&order=desc: 文件夹 (idx={last_dir_idx}) "
                    f"应在文件 (idx={first_file_idx}) 前面"
                )

    def test_list_asc_folders_first(self, client, temp_dir):
        """升序排列时文件夹也在前面。"""
        r = client.get(f"/api/list?path={temp_dir}&sort=name&order=asc")
        assert r.status_code == 200
        items = r.get_json()["items"]
        first_file_idx = None
        last_dir_idx = None
        for i, item in enumerate(items):
            if item["is_dir"] and (last_dir_idx is None or i > last_dir_idx):
                last_dir_idx = i
            if not item["is_dir"] and first_file_idx is None:
                first_file_idx = i
        if last_dir_idx is not None and first_file_idx is not None:
            assert last_dir_idx < first_file_idx

    def test_list_filter_by_type(self, client, temp_dir):
        r = client.get(f"/api/list?path={temp_dir}&filter_type=text")
        assert r.status_code == 200
        data = r.get_json()
        items = data["items"]
        # 只有文本文件和文件夹（文件夹始终保留）
        for item in items:
            if not item["is_dir"]:
                assert item["type"] == "text"

    def test_list_filter_by_ext(self, client, temp_dir):
        r = client.get(f"/api/list?path={temp_dir}&filter_ext=.txt")
        assert r.status_code == 200
        data = r.get_json()
        for item in data["items"]:
            if not item["is_dir"]:
                assert item["ext"] == ".txt"


# ════════════════════════════════════════════════
# /api/search
# ════════════════════════════════════════════════
class TestSearch:
    def test_search_by_name(self, client, temp_dir):
        r = client.get(f"/api/search?path={temp_dir}&q=hello")
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] >= 1
        names = [item["name"] for item in data["results"]]
        assert "hello.txt" in names

    def test_search_empty_query(self, client, temp_dir):
        r = client.get(f"/api/search?path={temp_dir}&q=")
        assert r.status_code == 200
        data = r.get_json()
        assert data["results"] == []

    def test_search_no_results(self, client, temp_dir):
        r = client.get(f"/api/search?path={temp_dir}&q=nonexistent_xyz")
        assert r.status_code == 200
        assert r.get_json()["total"] == 0

    def test_search_regex(self, client, temp_dir):
        r = client.get(f"/api/search?path={temp_dir}&q=hel.*\\.txt&regex=1")
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] >= 1

    def test_search_bad_regex(self, client, temp_dir):
        r = client.get(f"/api/search?path={temp_dir}&q=[invalid&regex=1")
        assert r.status_code == 400


# ════════════════════════════════════════════════
# /api/search-content
# ════════════════════════════════════════════════
class TestSearchContent:
    def test_content_search(self, client, temp_dir):
        r = client.get(f"/api/search-content?path={temp_dir}&q=Searchable")
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] >= 1
        # 检查匹配内容
        result = data["results"][0]
        assert "matches" in result
        assert any("Searchable" in m["text"] for m in result["matches"])

    def test_content_search_empty_query(self, client, temp_dir):
        r = client.get(f"/api/search-content?path={temp_dir}&q=")
        assert r.status_code == 200
        assert r.get_json()["results"] == []


# ════════════════════════════════════════════════
# /api/file (文本预览)
# ════════════════════════════════════════════════
class TestFile:
    def test_read_text_file(self, client, temp_dir):
        path = os.path.join(temp_dir, "hello.txt").replace("\\", "/")
        r = client.get(f"/api/file?path={path}")
        assert r.status_code == 200
        data = r.get_json()
        assert "Hello, World!" in data["content"]
        assert data["ext"] == "txt"

    def test_read_markdown_file(self, client, temp_dir):
        path = os.path.join(temp_dir, "readme.md").replace("\\", "/")
        r = client.get(f"/api/file?path={path}")
        assert r.status_code == 200
        assert "# Title" in r.get_json()["content"]

    def test_read_nonexistent(self, client):
        r = client.get("/api/file?path=/nonexistent/abc.txt")
        assert r.status_code == 404

    def test_read_binary_rejected(self, client, temp_dir):
        path = os.path.join(temp_dir, "image.png").replace("\\", "/")
        r = client.get(f"/api/file?path={path}")
        assert r.status_code == 400


# ════════════════════════════════════════════════
# /api/download
# ════════════════════════════════════════════════
class TestDownload:
    def test_download_file(self, client, temp_dir):
        path = os.path.join(temp_dir, "hello.txt").replace("\\", "/")
        r = client.get(f"/api/download?path={path}")
        assert r.status_code == 200
        assert b"Hello, World!" in r.data

    def test_download_nonexistent(self, client):
        r = client.get("/api/download?path=/nonexistent/abc.txt")
        assert r.status_code == 404


# ════════════════════════════════════════════════
# /api/raw
# ════════════════════════════════════════════════
class TestRaw:
    def test_raw_file(self, client, temp_dir):
        path = os.path.join(temp_dir, "image.png").replace("\\", "/")
        r = client.get(f"/api/raw?path={path}")
        assert r.status_code == 200
        assert r.data.startswith(b"\x89PNG")

    def test_raw_nonexistent(self, client):
        r = client.get("/api/raw?path=/nonexistent/abc.png")
        assert r.status_code == 404


# ════════════════════════════════════════════════
# /api/info
# ════════════════════════════════════════════════
class TestInfo:
    def test_file_info(self, client, temp_dir):
        path = os.path.join(temp_dir, "hello.txt").replace("\\", "/")
        r = client.get(f"/api/info?path={path}")
        assert r.status_code == 200
        data = r.get_json()
        assert data["name"] == "hello.txt"
        assert data["is_dir"] is False
        assert data["type"] == "text"
        assert "created" in data
        assert "modified" in data

    def test_dir_info(self, client, temp_dir):
        r = client.get(f"/api/info?path={temp_dir}")
        assert r.status_code == 200
        data = r.get_json()
        assert data["is_dir"] is True

    def test_info_nonexistent(self, client):
        r = client.get("/api/info?path=/nonexistent/abc")
        assert r.status_code == 404


# ════════════════════════════════════════════════
# /api/folder-size
# ════════════════════════════════════════════════
class TestFolderSize:
    def test_folder_size(self, client, temp_dir):
        r = client.get(f"/api/folder-size?path={temp_dir}")
        assert r.status_code == 200
        data = r.get_json()
        assert data["size"] > 0
        assert isinstance(data["size_str"], str)

    def test_folder_size_nonexistent(self, client):
        r = client.get("/api/folder-size?path=/nonexistent/abc")
        assert r.status_code == 404


# ════════════════════════════════════════════════
# /api/clipboard GET
# ════════════════════════════════════════════════
class TestClipboardGet:
    def test_get_empty_clipboard(self, client):
        r = client.get("/api/clipboard")
        assert r.status_code == 200
        data = r.get_json()
        assert "text" in data


# ════════════════════════════════════════════════
# /api/bookmarks GET
# ════════════════════════════════════════════════
class TestBookmarksGet:
    def test_get_empty_bookmarks(self, client):
        r = client.get("/api/bookmarks")
        assert r.status_code == 200
        data = r.get_json()
        assert isinstance(data, list)
        assert len(data) == 0


# ════════════════════════════════════════════════
# /api/zip-list
# ════════════════════════════════════════════════
class TestZipList:
    def test_list_zip_contents(self, client, temp_dir):
        path = os.path.join(temp_dir, "archive.zip").replace("\\", "/")
        r = client.get(f"/api/zip-list?path={path}")
        assert r.status_code == 200
        data = r.get_json()
        assert data["count"] >= 2
        names = [item["name"] for item in data["items"]]
        assert "inside.txt" in names

    def test_zip_list_nonexistent(self, client):
        r = client.get("/api/zip-list?path=/nonexistent/abc.zip")
        assert r.status_code == 404


# ════════════════════════════════════════════════
# 安全响应头
# ════════════════════════════════════════════════
class TestSecurityHeaders:
    def test_x_content_type_options(self, client):
        r = client.get("/")
        assert r.headers.get("X-Content-Type-Options") == "nosniff"

    def test_x_frame_options(self, client):
        r = client.get("/")
        assert r.headers.get("X-Frame-Options") == "SAMEORIGIN"

    def test_referrer_policy(self, client):
        r = client.get("/")
        assert r.headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"

    def test_security_headers_on_api(self, client, temp_dir):
        r = client.get(f"/api/list?path={temp_dir}")
        assert r.headers.get("X-Content-Type-Options") == "nosniff"

    def test_content_security_policy(self, client):
        r = client.get("/")
        csp = r.headers.get("Content-Security-Policy", "")
        assert "default-src 'self'" in csp
        assert "script-src" in csp
        assert "object-src 'none'" in csp
        assert "base-uri 'self'" in csp

    def test_csp_on_api(self, client, temp_dir):
        r = client.get(f"/api/list?path={temp_dir}")
        assert "Content-Security-Policy" in r.headers


# ════════════════════════════════════════════════
# /api/info 错误脱敏
# ════════════════════════════════════════════════
class TestInfoErrorSanitization:
    def test_info_nonexistent_does_not_leak_path(self, client):
        r = client.get("/api/info?path=/nonexistent/abc")
        assert r.status_code == 404
        data = r.get_json()
        # 错误消息不应包含系统路径
        assert "/nonexistent" not in data.get("error", "")


# ════════════════════════════════════════════════
# /api/search-content 正则模式
# ════════════════════════════════════════════════
class TestSearchContentRegex:
    def test_content_search_regex(self, client, temp_dir):
        r = client.get(f"/api/search-content?path={temp_dir}&q=Search.*keyword&regex=1")
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] >= 1

    def test_content_search_bad_regex(self, client, temp_dir):
        r = client.get(f"/api/search-content?path={temp_dir}&q=[invalid&regex=1")
        assert r.status_code == 400

    def test_content_search_nested_quantifier_rejected(self, client, temp_dir):
        r = client.get(f"/api/search-content?path={temp_dir}&q=(?:a%2B)%2B&regex=1")
        assert r.status_code == 400

    def test_search_nested_quantifier_rejected(self, client, temp_dir):
        """文件名搜索也应拒绝嵌套量词。"""
        r = client.get(f"/api/search?path={temp_dir}&q=(?:a%2B)%2B&regex=1")
        assert r.status_code == 400

# -*- coding: utf-8 -*-
"""中文编码与中文文件名测试：验证 GBK/GB18030 编码检测、编码保留、中文文件名 CRUD、中文内容搜索。"""
import io
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import file_browser
from tests.conftest import _patch_app, login


# ════════════════════════════════════════════════
# detect_encoding — 编码检测
# ════════════════════════════════════════════════
class TestDetectEncoding:
    def test_utf8(self, tmp_path):
        f = tmp_path / "utf8.txt"
        f.write_text("你好世界", encoding="utf-8")
        assert file_browser.detect_encoding(str(f)) == "utf-8"

    def test_gbk(self, tmp_path):
        f = tmp_path / "gbk.txt"
        f.write_bytes("你好世界".encode("gbk"))
        assert file_browser.detect_encoding(str(f)) in ("gbk", "gb18030")

    def test_gb18030(self, tmp_path):
        f = tmp_path / "gb18030.txt"
        # GB18030 特有字符（四字节编码区域）
        text = "你好世界"
        f.write_bytes(text.encode("gb18030"))
        enc = file_browser.detect_encoding(str(f))
        assert enc in ("gbk", "gb18030")

    def test_latin1(self, tmp_path):
        f = tmp_path / "latin.txt"
        f.write_bytes(b"\xe9\xe8\xea")  # 非 UTF-8/GBK 可解码
        enc = file_browser.detect_encoding(str(f))
        assert enc == "latin-1"

    def test_empty_file(self, tmp_path):
        f = tmp_path / "empty.txt"
        f.write_text("")
        assert file_browser.detect_encoding(str(f)) == "utf-8"


# ════════════════════════════════════════════════
# read_text_file — 中文内容读取
# ════════════════════════════════════════════════
class TestReadTextFileChinese:
    def test_read_utf8(self, tmp_path):
        f = tmp_path / "utf8.txt"
        f.write_text("你好世界\n第二行", encoding="utf-8")
        content = file_browser.read_text_file(str(f))
        assert "你好世界" in content
        assert "第二行" in content

    def test_read_gbk(self, tmp_path):
        f = tmp_path / "gbk.txt"
        f.write_bytes("你好世界\n中文内容".encode("gbk"))
        content = file_browser.read_text_file(str(f))
        assert "你好世界" in content
        assert "中文内容" in content

    def test_read_gb18030(self, tmp_path):
        f = tmp_path / "gb18030.txt"
        f.write_bytes("你好世界".encode("gb18030"))
        content = file_browser.read_text_file(str(f))
        assert "你好世界" in content


# ════════════════════════════════════════════════
# 辅助 fixture — 含中文文件的临时目录
# ════════════════════════════════════════════════
@pytest.fixture
def chinese_temp_dir(tmp_path):
    """创建包含中文文件名和中文内容的临时目录。"""
    d = str(tmp_path)
    # UTF-8 中文文件
    with open(os.path.join(d, "你好.txt"), "w", encoding="utf-8") as f:
        f.write("这是一个中文文件\n包含多行内容\n")
    # GBK 编码文件
    with open(os.path.join(d, "测试文档.txt"), "wb") as f:
        f.write("这是GBK编码的内容\n第二行数据".encode("gbk"))
    # 中文子目录
    os.makedirs(os.path.join(d, "中文目录"))
    with open(os.path.join(d, "中文目录", "子文件.txt"), "w", encoding="utf-8") as f:
        f.write("子目录中的文件内容\n搜索关键词在这里\n")
    # 纯英文文件（对照组）
    with open(os.path.join(d, "english.txt"), "w", encoding="utf-8") as f:
        f.write("Plain English content\n")
    return d


@pytest.fixture
def chinese_client(chinese_temp_dir, monkeypatch):
    """使用中文临时目录的无密码客户端。"""
    _patch_app(monkeypatch, chinese_temp_dir)
    with file_browser.app.test_client() as c:
        yield c


# ════════════════════════════════════════════════
# API — 中文文件名浏览
# ════════════════════════════════════════════════
class TestChineseFileBrowsing:
    def test_list_chinese_filenames(self, chinese_client, chinese_temp_dir):
        r = chinese_client.get(f"/api/list?path={chinese_temp_dir}")
        assert r.status_code == 200
        data = r.get_json()
        names = [item["name"] for item in data["items"]]
        assert "你好.txt" in names
        assert "测试文档.txt" in names
        assert "中文目录" in names

    def test_list_chinese_subdir(self, chinese_client, chinese_temp_dir):
        subdir = os.path.join(chinese_temp_dir, "中文目录").replace("\\", "/")
        r = chinese_client.get(f"/api/list?path={subdir}")
        assert r.status_code == 200
        data = r.get_json()
        names = [item["name"] for item in data["items"]]
        assert "子文件.txt" in names


# ════════════════════════════════════════════════
# API — 中文文件名搜索
# ════════════════════════════════════════════════
class TestChineseSearch:
    def test_search_chinese_filename(self, chinese_client, chinese_temp_dir):
        r = chinese_client.get(f"/api/search?path={chinese_temp_dir}&q=你好")
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] >= 1
        assert any("你好" in item["name"] for item in data["results"])

    def test_search_chinese_content(self, chinese_client, chinese_temp_dir):
        r = chinese_client.get(f"/api/search-content?path={chinese_temp_dir}&q=搜索关键词")
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] >= 1
        assert any("搜索关键词" in m["text"] for item in data["results"] for m in item["matches"])


# ════════════════════════════════════════════════
# API — 中文文件名创建
# ════════════════════════════════════════════════
class TestChineseFileCreate:
    def test_mkdir_chinese_name(self, chinese_client, chinese_temp_dir):
        r = chinese_client.post(
            "/api/mkdir",
            json={"path": chinese_temp_dir, "name": "新建文件夹"},
        )
        assert r.status_code == 200
        assert r.get_json()["ok"] is True
        assert os.path.isdir(os.path.join(chinese_temp_dir, "新建文件夹"))

    def test_mkfile_chinese_name(self, chinese_client, chinese_temp_dir):
        r = chinese_client.post(
            "/api/mkfile",
            json={"path": chinese_temp_dir, "name": "笔记.md", "content": "# 中文标题\n"},
        )
        assert r.status_code == 200
        assert r.get_json()["ok"] is True
        created = os.path.join(chinese_temp_dir, "笔记.md")
        assert os.path.isfile(created)
        with open(created, "r", encoding="utf-8") as f:
            assert "中文标题" in f.read()

    def test_upload_chinese_filename(self, chinese_client, chinese_temp_dir):
        r = chinese_client.post(
            "/api/upload",
            data={
                "path": chinese_temp_dir,
                "files": (io.BytesIO("上传的中文内容".encode("utf-8")), "上传文件.txt"),
            },
            content_type="multipart/form-data",
        )
        assert r.status_code == 200
        assert r.get_json()["count"] == 1
        assert os.path.isfile(os.path.join(chinese_temp_dir, "上传文件.txt"))


# ════════════════════════════════════════════════
# API — 中文文件重命名
# ════════════════════════════════════════════════
class TestChineseRename:
    def test_rename_chinese_file(self, chinese_client, chinese_temp_dir):
        old_path = os.path.join(chinese_temp_dir, "你好.txt").replace("\\", "/")
        r = chinese_client.post(
            "/api/rename",
            json={"path": old_path, "name": "你好世界.txt"},
        )
        assert r.status_code == 200
        assert r.get_json()["ok"] is True
        assert os.path.isfile(os.path.join(chinese_temp_dir, "你好世界.txt"))
        assert not os.path.isfile(os.path.join(chinese_temp_dir, "你好.txt"))


# ════════════════════════════════════════════════
# API — 中文文件删除
# ════════════════════════════════════════════════
class TestChineseDelete:
    def test_delete_chinese_file(self, chinese_client, chinese_temp_dir):
        fpath = os.path.join(chinese_temp_dir, "你好.txt").replace("\\", "/")
        r = chinese_client.post("/api/delete", json={"path": fpath})
        assert r.status_code == 200
        assert not os.path.exists(os.path.join(chinese_temp_dir, "你好.txt"))

    def test_delete_chinese_dir(self, chinese_client, chinese_temp_dir):
        dpath = os.path.join(chinese_temp_dir, "中文目录").replace("\\", "/")
        r = chinese_client.post("/api/delete", json={"path": dpath, "recursive": True})
        assert r.status_code == 200
        assert not os.path.exists(os.path.join(chinese_temp_dir, "中文目录"))


# ════════════════════════════════════════════════
# API — 编码保留（保存 GBK 文件后编码不变）
# ════════════════════════════════════════════════
class TestEncodingPreservation:
    def test_save_preserves_gbk_encoding(self, chinese_client, chinese_temp_dir):
        """保存 GBK 编码文件后，文件仍为 GBK 编码。"""
        fpath = os.path.join(chinese_temp_dir, "测试文档.txt").replace("\\", "/")
        # 先读取
        r = chinese_client.get(f"/api/file?path={fpath}")
        assert r.status_code == 200
        original_content = r.get_json()["content"]
        assert "GBK" in original_content

        # 修改并保存
        new_content = original_content + "\n新增一行内容"
        r = chinese_client.post(
            "/api/save-file",
            json={"path": fpath, "content": new_content},
        )
        assert r.status_code == 200
        assert r.get_json()["ok"] is True

        # 验证文件仍可被 GBK 解码
        real_path = os.path.join(chinese_temp_dir, "测试文档.txt")
        with open(real_path, "rb") as f:
            raw_bytes = f.read()
        decoded = raw_bytes.decode("gbk")
        assert "新增一行内容" in decoded

    def test_save_preserves_utf8_encoding(self, chinese_client, chinese_temp_dir):
        """保存 UTF-8 编码文件后，文件仍为 UTF-8 编码。"""
        fpath = os.path.join(chinese_temp_dir, "你好.txt").replace("\\", "/")
        r = chinese_client.post(
            "/api/save-file",
            json={"path": fpath, "content": "修改后的内容"},
        )
        assert r.status_code == 200
        real_path = os.path.join(chinese_temp_dir, "你好.txt")
        with open(real_path, "r", encoding="utf-8") as f:
            assert "修改后的内容" in f.read()


# ════════════════════════════════════════════════
# API — 中文文件预览
# ════════════════════════════════════════════════
class TestChinesePreview:
    def test_preview_utf8_chinese_file(self, chinese_client, chinese_temp_dir):
        fpath = os.path.join(chinese_temp_dir, "你好.txt").replace("\\", "/")
        r = chinese_client.get(f"/api/file?path={fpath}")
        assert r.status_code == 200
        data = r.get_json()
        assert "中文文件" in data["content"]

    def test_preview_gbk_chinese_file(self, chinese_client, chinese_temp_dir):
        fpath = os.path.join(chinese_temp_dir, "测试文档.txt").replace("\\", "/")
        r = chinese_client.get(f"/api/file?path={fpath}")
        assert r.status_code == 200
        data = r.get_json()
        assert "GBK编码" in data["content"]

    def test_download_chinese_filename(self, chinese_client, chinese_temp_dir):
        fpath = os.path.join(chinese_temp_dir, "你好.txt").replace("\\", "/")
        r = chinese_client.get(f"/api/download?path={fpath}")
        assert r.status_code == 200

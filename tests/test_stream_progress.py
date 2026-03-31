# -*- coding: utf-8 -*-
"""
流式进度功能的单元测试。

覆盖 /api/copy、/api/move、/api/delete、/api/extract 四个端点在
stream=true 时返回 NDJSON 流式进度响应的各种场景。
"""
import os
import sys
import json

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import file_browser


# ────────────────────────────────────────────────
# 辅助函数
# ────────────────────────────────────────────────

def parse_ndjson(response_data):
    """解析 NDJSON 响应数据，返回 (progress_lines, result_line) 元组。"""
    lines = response_data.decode("utf-8").strip().split("\n")
    parsed = [json.loads(line) for line in lines if line.strip()]
    progress = [d for d in parsed if "p" in d and "t" in d]
    results = [d for d in parsed if "ok" in d or "error" in d]
    return progress, results[0] if results else None


# ════════════════════════════════════════════════════════════
# 复制流式测试
# ════════════════════════════════════════════════════════════

class TestCopyStream:
    """测试 /api/copy 的流式进度功能。"""

    def test_copy_file_stream(self, client, temp_dir):
        """复制文件带 stream=true，验证返回 NDJSON 且 ok=true，目标文件存在且内容正确。"""
        dest = os.path.join(temp_dir, "copy_dest")
        os.makedirs(dest)

        resp = client.post("/api/copy", json={
            "src": os.path.join(temp_dir, "hello.txt"),
            "dest_dir": dest,
            "stream": True,
        })
        assert resp.status_code == 200
        assert "text/x-ndjson" in resp.content_type

        progress, result = parse_ndjson(resp.data)
        assert result is not None
        assert result["ok"] is True

        # 验证目标文件存在且内容正确
        copied = os.path.join(dest, "hello.txt")
        assert os.path.isfile(copied)
        with open(copied, "r", encoding="utf-8") as f:
            assert f.read() == "Hello, World!\nLine two.\n"

    def test_copy_file_no_stream(self, client, temp_dir):
        """复制文件不带 stream，验证返回普通 JSON（向后兼容）。"""
        dest = os.path.join(temp_dir, "copy_dest_nostream")
        os.makedirs(dest)

        resp = client.post("/api/copy", json={
            "src": os.path.join(temp_dir, "hello.txt"),
            "dest_dir": dest,
        })
        assert resp.status_code == 200
        assert "application/json" in resp.content_type

        data = resp.get_json()
        assert data["ok"] is True

    def test_copy_dir_stream(self, client, temp_dir):
        """复制目录带 stream=true，验证进度行包含 'f' 字段。"""
        dest = os.path.join(temp_dir, "copy_dir_dest")
        os.makedirs(dest)

        resp = client.post("/api/copy", json={
            "src": os.path.join(temp_dir, "subdir"),
            "dest_dir": dest,
            "stream": True,
        })
        assert resp.status_code == 200
        assert "text/x-ndjson" in resp.content_type

        progress, result = parse_ndjson(resp.data)
        assert result is not None
        assert result["ok"] is True

        # 目录复制的进度行应包含 f 字段（相对路径文件名）
        for p in progress:
            assert "f" in p
            assert "p" in p
            assert "t" in p

    def test_copy_conflict_returns_json(self, client, temp_dir):
        """冲突时即使 stream=true 也返回普通 JSON 409。"""
        # hello.txt 已存在于 temp_dir，复制到同目录会冲突
        resp = client.post("/api/copy", json={
            "src": os.path.join(temp_dir, "hello.txt"),
            "dest_dir": temp_dir,
            "stream": True,
        })
        assert resp.status_code == 409
        data = resp.get_json()
        assert data["conflict"] is True


# ════════════════════════════════════════════════════════════
# 移动流式测试
# ════════════════════════════════════════════════════════════

class TestMoveStream:
    """测试 /api/move 的流式进度功能。"""

    def test_move_file_stream(self, client, temp_dir):
        """移动文件带 stream=true，验证 ok=true，源文件不存在，目标存在。"""
        # 创建一个待移动的文件
        src = os.path.join(temp_dir, "move_me.txt")
        with open(src, "w", encoding="utf-8") as f:
            f.write("move this content")

        dest = os.path.join(temp_dir, "move_dest")
        os.makedirs(dest)

        resp = client.post("/api/move", json={
            "src": src,
            "dest_dir": dest,
            "stream": True,
        })
        assert resp.status_code == 200
        assert "text/x-ndjson" in resp.content_type

        progress, result = parse_ndjson(resp.data)
        assert result is not None
        assert result["ok"] is True

        # 源文件不存在，目标文件存在
        assert not os.path.exists(src)
        moved = os.path.join(dest, "move_me.txt")
        assert os.path.isfile(moved)
        with open(moved, "r", encoding="utf-8") as f:
            assert f.read() == "move this content"

    def test_move_same_fs_instant(self, client, temp_dir):
        """同分区移动应该瞬时完成（返回包含 ok 的流或极少进度行）。"""
        src = os.path.join(temp_dir, "instant_move.txt")
        with open(src, "w", encoding="utf-8") as f:
            f.write("instant move")

        dest = os.path.join(temp_dir, "instant_dest")
        os.makedirs(dest)

        resp = client.post("/api/move", json={
            "src": src,
            "dest_dir": dest,
            "stream": True,
        })
        assert resp.status_code == 200

        progress, result = parse_ndjson(resp.data)
        assert result is not None
        assert result["ok"] is True

        # 同分区 rename 是瞬时的，不应有进度行（或极少）
        assert len(progress) == 0


# ════════════════════════════════════════════════════════════
# 删除流式测试
# ════════════════════════════════════════════════════════════

class TestDeleteStream:
    """测试 /api/delete 的流式进度功能。"""

    def test_delete_recursive_stream(self, client, temp_dir):
        """创建含多个文件的目录，递归删除带 stream=true，验证进度行有 p/t/f 字段。"""
        # 创建一个包含多个文件的目录
        del_dir = os.path.join(temp_dir, "to_delete")
        os.makedirs(del_dir)
        for i in range(5):
            with open(os.path.join(del_dir, f"file_{i}.txt"), "w") as f:
                f.write(f"content {i}")

        resp = client.post("/api/delete", json={
            "path": del_dir,
            "recursive": True,
            "stream": True,
        })
        assert resp.status_code == 200
        assert "text/x-ndjson" in resp.content_type

        progress, result = parse_ndjson(resp.data)
        assert result is not None
        assert result["ok"] is True

        # 验证进度行格式
        assert len(progress) > 0
        for p in progress:
            assert "p" in p
            assert "t" in p
            assert "f" in p

        # 验证目录已被删除
        assert not os.path.exists(del_dir)

    def test_delete_file_no_stream_needed(self, client, temp_dir):
        """删除单个文件（无论 stream 与否都是普通 JSON，因为单文件删除不走流式）。"""
        target = os.path.join(temp_dir, "single_del.txt")
        with open(target, "w") as f:
            f.write("delete me")

        resp = client.post("/api/delete", json={
            "path": target,
            "stream": True,
        })
        assert resp.status_code == 200
        # 单文件删除直接返回普通 JSON，不走流式
        assert "application/json" in resp.content_type
        data = resp.get_json()
        assert data["ok"] is True
        assert not os.path.exists(target)


# ════════════════════════════════════════════════════════════
# 解压流式测试
# ════════════════════════════════════════════════════════════

class TestExtractStream:
    """测试 /api/extract 的流式进度功能。"""

    def test_extract_stream(self, client, temp_dir):
        """解压 archive.zip 带 stream=true，验证进度行和 ok=true。"""
        extract_dest = os.path.join(temp_dir, "extract_dest")
        os.makedirs(extract_dest)

        resp = client.post("/api/extract", json={
            "path": os.path.join(temp_dir, "archive.zip"),
            "dest_dir": extract_dest,
            "stream": True,
        })
        assert resp.status_code == 200
        assert "text/x-ndjson" in resp.content_type

        progress, result = parse_ndjson(resp.data)
        assert result is not None
        assert result["ok"] is True

        # archive.zip 包含 inside.txt 和 subdir/deep.txt，应有进度行
        assert len(progress) > 0
        for p in progress:
            assert "p" in p
            assert "t" in p
            assert "f" in p

        # 验证解压出的文件存在
        assert os.path.isfile(os.path.join(extract_dest, "inside.txt"))
        assert os.path.isfile(os.path.join(extract_dest, "subdir", "deep.txt"))

    def test_extract_conflict_returns_json(self, client, temp_dir):
        """冲突时返回 409 JSON。"""
        # 先解压一次，制造冲突
        extract_dest = os.path.join(temp_dir, "extract_conflict")
        os.makedirs(extract_dest)
        with open(os.path.join(extract_dest, "inside.txt"), "w") as f:
            f.write("existing content")

        resp = client.post("/api/extract", json={
            "path": os.path.join(temp_dir, "archive.zip"),
            "dest_dir": extract_dest,
            "stream": True,
        })
        assert resp.status_code == 409
        data = resp.get_json()
        assert data["conflict"] is True


# ════════════════════════════════════════════════════════════
# 端到端 / 边界测试
# ════════════════════════════════════════════════════════════

class TestStreamE2E:
    """端到端流式进度测试。"""

    def test_copy_large_file_has_progress(self, client, temp_dir):
        """创建一个 3MB 的文件（超过 1MB 分块），复制它，验证返回了多个进度行（p 值递增到 t）。"""
        # 创建 3MB 大文件
        large_file = os.path.join(temp_dir, "large.bin")
        with open(large_file, "wb") as f:
            f.write(b'\x00' * (3 * 1024 * 1024))

        dest = os.path.join(temp_dir, "large_dest")
        os.makedirs(dest)

        resp = client.post("/api/copy", json={
            "src": large_file,
            "dest_dir": dest,
            "stream": True,
        })
        assert resp.status_code == 200
        assert "text/x-ndjson" in resp.content_type

        progress, result = parse_ndjson(resp.data)
        assert result is not None
        assert result["ok"] is True

        # 3MB 文件以 1MB 分块复制，应该有多个进度行
        assert len(progress) >= 2

        # 验证 p 值递增且最终 p == t
        prev_p = 0
        for p in progress:
            assert p["p"] >= prev_p
            prev_p = p["p"]
        # 最后一个进度行的 p 应等于 t（文件总大小）
        assert progress[-1]["p"] == progress[-1]["t"]
        assert progress[-1]["t"] == 3 * 1024 * 1024

        # 验证目标文件大小正确
        copied = os.path.join(dest, "large.bin")
        assert os.path.isfile(copied)
        assert os.path.getsize(copied) == 3 * 1024 * 1024

    def test_readonly_blocks_stream(self, client, temp_dir, monkeypatch):
        """只读模式下 stream 请求也返回 403。"""
        monkeypatch.setattr(file_browser, "READ_ONLY", True)

        dest = os.path.join(temp_dir, "ro_dest")
        os.makedirs(dest)

        # 测试 copy
        resp = client.post("/api/copy", json={
            "src": os.path.join(temp_dir, "hello.txt"),
            "dest_dir": dest,
            "stream": True,
        })
        assert resp.status_code == 403

        # 测试 move
        resp = client.post("/api/move", json={
            "src": os.path.join(temp_dir, "hello.txt"),
            "dest_dir": dest,
            "stream": True,
        })
        assert resp.status_code == 403

        # 测试 delete
        resp = client.post("/api/delete", json={
            "path": os.path.join(temp_dir, "hello.txt"),
            "stream": True,
        })
        assert resp.status_code == 403

        # 测试 extract
        resp = client.post("/api/extract", json={
            "path": os.path.join(temp_dir, "archive.zip"),
            "dest_dir": dest,
            "stream": True,
        })
        assert resp.status_code == 403

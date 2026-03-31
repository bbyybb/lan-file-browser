# -*- coding: utf-8 -*-
"""分片断点续传 API 测试：upload-init / upload-chunk / upload-complete / upload-cancel / upload-status。"""
import io
import os
import sys
import json
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import file_browser


# ────────────────────────────────────────────────
# 辅助 fixture：每个测试前清空 _upload_sessions
# ────────────────────────────────────────────────
@pytest.fixture(autouse=True)
def _clean_upload_sessions(monkeypatch):
    """每个测试前重置上传会话字典，防止测试间互相干扰。"""
    monkeypatch.setattr(file_browser, "_upload_sessions", {})


def _init_upload(client, temp_dir, **overrides):
    """快捷辅助：调用 /api/upload-init 并返回响应。"""
    payload = {
        "path": temp_dir,
        "filename": "testfile.bin",
        "size": 1024,
        "relativePath": "",
        "conflict": "rename",
    }
    payload.update(overrides)
    return client.post(
        "/api/upload-init",
        json=payload,
        content_type="application/json",
    )


def _upload_chunk(client, upload_id, data, offset=0):
    """快捷辅助：调用 /api/upload-chunk 发送一个分片。"""
    return client.post(
        "/api/upload-chunk",
        data={
            "upload_id": upload_id,
            "offset": str(offset),
            "chunk": (io.BytesIO(data), "chunk.bin"),
        },
        content_type="multipart/form-data",
    )


# ════════════════════════════════════════════════
# /api/upload-init
# ════════════════════════════════════════════════
class TestUploadInit:
    def test_init_creates_session(self, client, temp_dir):
        """正常初始化应返回 upload_id 和 chunk_size。"""
        r = _init_upload(client, temp_dir, size=2048)
        assert r.status_code == 200
        body = r.get_json()
        assert "upload_id" in body
        assert body["chunk_size"] > 0
        assert body["uploaded_bytes"] == 0
        assert body["dest_filename"] == "testfile.bin"

    def test_init_missing_filename(self, client, temp_dir):
        """filename 为空时返回 400。"""
        r = _init_upload(client, temp_dir, filename="")
        assert r.status_code == 400

    def test_init_invalid_path(self, client, temp_dir):
        """目标目录不存在时返回 404。"""
        r = _init_upload(client, temp_dir, path="/nonexistent/dir")
        assert r.status_code == 404

    def test_init_conflict_skip(self, client, temp_dir):
        """文件已存在 + conflict=skip 应返回 skipped=True。"""
        # 预先创建目标文件
        with open(os.path.join(temp_dir, "existing.txt"), "w") as f:
            f.write("existing")
        r = _init_upload(client, temp_dir, filename="existing.txt", conflict="skip")
        assert r.status_code == 200
        body = r.get_json()
        assert body["skipped"] is True
        assert body["dest_filename"] == "existing.txt"

    def test_init_conflict_rename(self, client, temp_dir):
        """文件已存在 + conflict=rename 应返回不同文件名（自动加后缀）。"""
        with open(os.path.join(temp_dir, "dup.txt"), "w") as f:
            f.write("data")
        r = _init_upload(client, temp_dir, filename="dup.txt", conflict="rename")
        assert r.status_code == 200
        body = r.get_json()
        assert body["dest_filename"] != "dup.txt"
        assert "dup_1.txt" in body["dest_filename"]

    def test_init_conflict_overwrite(self, client, temp_dir):
        """文件已存在 + conflict=overwrite 应返回原文件名。"""
        with open(os.path.join(temp_dir, "overme.txt"), "w") as f:
            f.write("old")
        r = _init_upload(client, temp_dir, filename="overme.txt", conflict="overwrite")
        assert r.status_code == 200
        body = r.get_json()
        assert body["dest_filename"] == "overme.txt"
        assert "upload_id" in body

    def test_init_readonly_blocked(self, readonly_client, temp_dir):
        """只读模式下返回 403。"""
        r = _init_upload(readonly_client, temp_dir)
        assert r.status_code == 403

    def test_init_path_traversal(self, client, temp_dir):
        """relativePath 含 .. 时返回 400。"""
        r = _init_upload(client, temp_dir, relativePath="../escape/bad.txt")
        assert r.status_code == 400

    def test_init_resume_existing(self, client, temp_dir):
        """已有同目标、同大小的会话时返回 resumed=True 和正确的 uploaded_bytes。"""
        # 第一次初始化
        r1 = _init_upload(client, temp_dir, filename="resume.bin", size=4096)
        body1 = r1.get_json()
        uid = body1["upload_id"]

        # 写入一些数据到临时文件，模拟部分上传
        _upload_chunk(client, uid, b"A" * 1000, offset=0)

        # 第二次初始化相同文件——应恢复
        r2 = _init_upload(client, temp_dir, filename="resume.bin", size=4096)
        assert r2.status_code == 200
        body2 = r2.get_json()
        assert body2.get("resumed") is True
        assert body2["upload_id"] == uid
        assert body2["uploaded_bytes"] == 1000


# ════════════════════════════════════════════════
# /api/upload-chunk
# ════════════════════════════════════════════════
class TestUploadChunk:
    def test_chunk_normal(self, client, temp_dir):
        """正常上传分片后 uploaded_bytes 正确返回。"""
        r = _init_upload(client, temp_dir, size=512)
        uid = r.get_json()["upload_id"]

        chunk_data = b"X" * 256
        cr = _upload_chunk(client, uid, chunk_data, offset=0)
        assert cr.status_code == 200
        assert cr.get_json()["uploaded_bytes"] == 256

    def test_chunk_invalid_session(self, client, temp_dir):
        """upload_id 无效时返回 404。"""
        cr = _upload_chunk(client, "nonexistent_id", b"data", offset=0)
        assert cr.status_code == 404

    def test_chunk_no_data(self, client, temp_dir):
        """无分片数据返回 400。"""
        r = _init_upload(client, temp_dir, size=100)
        uid = r.get_json()["upload_id"]

        # 不发送 chunk 文件
        cr = client.post(
            "/api/upload-chunk",
            data={"upload_id": uid, "offset": "0"},
            content_type="multipart/form-data",
        )
        assert cr.status_code == 400

    def test_chunk_sequential(self, client, temp_dir):
        """多次分片顺序上传，offset 正确累加。"""
        r = _init_upload(client, temp_dir, size=600)
        uid = r.get_json()["upload_id"]

        cr1 = _upload_chunk(client, uid, b"A" * 200, offset=0)
        assert cr1.get_json()["uploaded_bytes"] == 200

        cr2 = _upload_chunk(client, uid, b"B" * 200, offset=200)
        assert cr2.get_json()["uploaded_bytes"] == 400

        cr3 = _upload_chunk(client, uid, b"C" * 200, offset=400)
        assert cr3.get_json()["uploaded_bytes"] == 600


# ════════════════════════════════════════════════
# /api/upload-complete
# ════════════════════════════════════════════════
class TestUploadComplete:
    def test_complete_normal(self, client, temp_dir):
        """完成后文件出现在目标目录，临时文件被删除。"""
        content = b"file content here"
        r = _init_upload(client, temp_dir, filename="completed.bin", size=len(content))
        body = r.get_json()
        uid = body["upload_id"]

        _upload_chunk(client, uid, content, offset=0)

        # 记下临时文件路径
        tmp_path = file_browser._upload_sessions[uid]["tmp_path"]

        cr = client.post(
            "/api/upload-complete",
            json={"upload_id": uid},
            content_type="application/json",
        )
        assert cr.status_code == 200
        result = cr.get_json()
        assert result["ok"] is True
        assert result["filename"] == "completed.bin"

        # 验证目标文件内容
        dest = os.path.join(temp_dir, "completed.bin")
        assert os.path.isfile(dest)
        with open(dest, "rb") as f:
            assert f.read() == content

        # 验证临时文件已清理
        assert not os.path.exists(tmp_path)

    def test_complete_invalid_session(self, client, temp_dir):
        """upload_id 无效返回 404。"""
        cr = client.post(
            "/api/upload-complete",
            json={"upload_id": "bad_id"},
            content_type="application/json",
        )
        assert cr.status_code == 404

    def test_complete_overwrite_existing(self, client, temp_dir):
        """目标文件已存在时使用 overwrite 策略可以覆盖成功。"""
        dest_path = os.path.join(temp_dir, "overwrite_target.txt")
        with open(dest_path, "w") as f:
            f.write("old content")

        new_content = b"new content bytes"
        r = _init_upload(
            client, temp_dir,
            filename="overwrite_target.txt",
            size=len(new_content),
            conflict="overwrite",
        )
        uid = r.get_json()["upload_id"]

        _upload_chunk(client, uid, new_content, offset=0)

        cr = client.post(
            "/api/upload-complete",
            json={"upload_id": uid},
            content_type="application/json",
        )
        assert cr.status_code == 200
        assert cr.get_json()["ok"] is True

        with open(dest_path, "rb") as f:
            assert f.read() == new_content


# ════════════════════════════════════════════════
# /api/upload-cancel
# ════════════════════════════════════════════════
class TestUploadCancel:
    def test_cancel_normal(self, client, temp_dir):
        """取消后临时文件被删除。"""
        r = _init_upload(client, temp_dir, size=100)
        uid = r.get_json()["upload_id"]

        # 写入部分数据
        _upload_chunk(client, uid, b"partial", offset=0)
        tmp_path = file_browser._upload_sessions[uid]["tmp_path"]
        assert os.path.exists(tmp_path)

        cr = client.post(
            "/api/upload-cancel",
            json={"upload_id": uid},
            content_type="application/json",
        )
        assert cr.status_code == 200
        assert cr.get_json()["ok"] is True
        assert not os.path.exists(tmp_path)

    def test_cancel_invalid_session(self, client, temp_dir):
        """upload_id 无效返回 404。"""
        cr = client.post(
            "/api/upload-cancel",
            json={"upload_id": "no_such_id"},
            content_type="application/json",
        )
        assert cr.status_code == 404


# ════════════════════════════════════════════════
# /api/upload-status
# ════════════════════════════════════════════════
class TestUploadStatus:
    def test_status_normal(self, client, temp_dir):
        """返回正确的 uploaded_bytes 和 total_size。"""
        total = 500
        r = _init_upload(client, temp_dir, filename="status_test.bin", size=total)
        uid = r.get_json()["upload_id"]

        _upload_chunk(client, uid, b"Z" * 200, offset=0)

        sr = client.get(f"/api/upload-status?upload_id={uid}")
        assert sr.status_code == 200
        body = sr.get_json()
        assert body["upload_id"] == uid
        assert body["uploaded_bytes"] == 200
        assert body["total_size"] == total
        assert body["filename"] == "status_test.bin"

    def test_status_invalid_session(self, client, temp_dir):
        """upload_id 无效返回 404。"""
        sr = client.get("/api/upload-status?upload_id=ghost")
        assert sr.status_code == 404


# ════════════════════════════════════════════════
# 端到端流程测试
# ════════════════════════════════════════════════
class TestChunkedUploadE2E:
    def test_full_flow(self, client, temp_dir):
        """完整流程：init -> chunk x N -> complete，验证最终文件内容正确。"""
        # 构造一段超过单分片大小的数据（此处用较小数据模拟多分片）
        chunk_a = b"A" * 300
        chunk_b = b"B" * 300
        chunk_c = b"C" * 100
        total = len(chunk_a) + len(chunk_b) + len(chunk_c)  # 700
        full_content = chunk_a + chunk_b + chunk_c

        # 1. 初始化
        r = _init_upload(client, temp_dir, filename="e2e_full.dat", size=total)
        assert r.status_code == 200
        uid = r.get_json()["upload_id"]

        # 2. 分片上传
        _upload_chunk(client, uid, chunk_a, offset=0)
        _upload_chunk(client, uid, chunk_b, offset=300)
        _upload_chunk(client, uid, chunk_c, offset=600)

        # 3. 完成
        cr = client.post(
            "/api/upload-complete",
            json={"upload_id": uid},
            content_type="application/json",
        )
        assert cr.status_code == 200
        result = cr.get_json()
        assert result["ok"] is True
        assert result["filename"] == "e2e_full.dat"

        # 4. 验证文件内容
        dest = os.path.join(temp_dir, "e2e_full.dat")
        assert os.path.isfile(dest)
        with open(dest, "rb") as f:
            assert f.read() == full_content

    def test_full_flow_with_resume(self, client, temp_dir):
        """断点续传流程：init -> 部分 chunk -> 重新 init（恢复）-> 剩余 chunk -> complete。"""
        part1 = b"FIRST_HALF__" * 10   # 120 字节
        part2 = b"SECOND_HALF_" * 10   # 120 字节
        total = len(part1) + len(part2)  # 240
        full_content = part1 + part2

        # 第一次初始化
        r1 = _init_upload(client, temp_dir, filename="resume_e2e.dat", size=total)
        uid1 = r1.get_json()["upload_id"]

        # 上传第一部分
        _upload_chunk(client, uid1, part1, offset=0)

        # 模拟"断线后重新请求"——再次 init 相同文件
        r2 = _init_upload(client, temp_dir, filename="resume_e2e.dat", size=total)
        body2 = r2.get_json()
        assert body2.get("resumed") is True
        assert body2["upload_id"] == uid1
        assert body2["uploaded_bytes"] == len(part1)

        # 上传第二部分
        _upload_chunk(client, uid1, part2, offset=len(part1))

        # 完成
        cr = client.post(
            "/api/upload-complete",
            json={"upload_id": uid1},
            content_type="application/json",
        )
        assert cr.status_code == 200
        assert cr.get_json()["ok"] is True

        dest = os.path.join(temp_dir, "resume_e2e.dat")
        with open(dest, "rb") as f:
            assert f.read() == full_content

    def test_readonly_blocks_all(self, readonly_client, temp_dir):
        """只读模式下所有写操作端点返回 403。"""
        # upload-init
        r = _init_upload(readonly_client, temp_dir)
        assert r.status_code == 403

        # upload-chunk（即使伪造 upload_id 也应被拦截）
        cr = _upload_chunk(readonly_client, "fake_id", b"data", offset=0)
        assert cr.status_code == 403

        # upload-complete
        cr2 = readonly_client.post(
            "/api/upload-complete",
            json={"upload_id": "fake_id"},
            content_type="application/json",
        )
        assert cr2.status_code == 403

        # upload-cancel 只需 @require_auth，不需要 @require_writable，不测 403
        # upload-status 同上（只需认证，不限写权限）

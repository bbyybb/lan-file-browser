# -*- coding: utf-8 -*-
"""写操作 API 测试：上传、新建、删除、重命名、编辑、复制、移动、书签、剪贴板、批量操作。"""
import io
import os
import sys
import json
import zipfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# ════════════════════════════════════════════════
# /api/upload
# ════════════════════════════════════════════════
class TestUpload:
    def test_upload_file(self, client, temp_dir):
        data = {
            "path": temp_dir,
            "files": (io.BytesIO(b"uploaded content"), "uploaded.txt"),
        }
        r = client.post(
            "/api/upload",
            data=data,
            content_type="multipart/form-data",
        )
        assert r.status_code == 200
        result = r.get_json()
        assert result["count"] == 1
        assert "uploaded.txt" in result["saved"]
        assert os.path.isfile(os.path.join(temp_dir, "uploaded.txt"))

    def test_upload_duplicate_name(self, client, temp_dir):
        # 上传同名文件两次，第二次应自动加后缀
        for _ in range(2):
            client.post(
                "/api/upload",
                data={"path": temp_dir, "files": (io.BytesIO(b"data"), "dup.txt")},
                content_type="multipart/form-data",
            )
        assert os.path.isfile(os.path.join(temp_dir, "dup.txt"))
        assert os.path.isfile(os.path.join(temp_dir, "dup_1.txt"))

    def test_upload_no_files(self, client, temp_dir):
        r = client.post(
            "/api/upload",
            data={"path": temp_dir},
            content_type="multipart/form-data",
        )
        assert r.status_code == 400


# ════════════════════════════════════════════════
# /api/mkdir
# ════════════════════════════════════════════════
class TestMkdir:
    def test_create_folder(self, client, temp_dir):
        r = client.post(
            "/api/mkdir",
            json={"path": temp_dir, "name": "new_folder"},
        )
        assert r.status_code == 200
        assert r.get_json()["ok"] is True
        assert os.path.isdir(os.path.join(temp_dir, "new_folder"))

    def test_create_duplicate_folder(self, client, temp_dir):
        r = client.post(
            "/api/mkdir",
            json={"path": temp_dir, "name": "subdir"},  # 已存在
        )
        assert r.status_code == 409

    def test_create_folder_invalid_name(self, client, temp_dir):
        r = client.post(
            "/api/mkdir",
            json={"path": temp_dir, "name": "bad/name"},
        )
        assert r.status_code == 400

    def test_create_folder_empty_name(self, client, temp_dir):
        r = client.post(
            "/api/mkdir",
            json={"path": temp_dir, "name": ""},
        )
        assert r.status_code == 400


# ════════════════════════════════════════════════
# /api/mkfile
# ════════════════════════════════════════════════
class TestMkfile:
    def test_create_file(self, client, temp_dir):
        r = client.post(
            "/api/mkfile",
            json={"path": temp_dir, "name": "new.txt", "content": "initial content"},
        )
        assert r.status_code == 200
        assert r.get_json()["ok"] is True
        fpath = os.path.join(temp_dir, "new.txt")
        assert os.path.isfile(fpath)
        with open(fpath, "r", encoding="utf-8") as f:
            assert f.read() == "initial content"

    def test_create_file_duplicate(self, client, temp_dir):
        r = client.post(
            "/api/mkfile",
            json={"path": temp_dir, "name": "hello.txt"},  # 已存在
        )
        assert r.status_code == 409


# ════════════════════════════════════════════════
# /api/save-file
# ════════════════════════════════════════════════
class TestSaveFile:
    def test_save_text_file(self, client, temp_dir):
        path = os.path.join(temp_dir, "hello.txt").replace("\\", "/")
        r = client.post(
            "/api/save-file",
            json={"path": path, "content": "Updated content!"},
        )
        assert r.status_code == 200
        data = r.get_json()
        assert data["ok"] is True
        assert "backup" in data
        # 验证内容已更新
        with open(os.path.join(temp_dir, "hello.txt"), "r", encoding="utf-8") as f:
            assert f.read() == "Updated content!"
        # 验证备份文件存在
        assert os.path.isfile(os.path.join(temp_dir, "hello.txt.bak"))

    def test_save_nonexistent(self, client):
        r = client.post(
            "/api/save-file",
            json={"path": "/nonexistent/abc.txt", "content": "test"},
        )
        assert r.status_code == 404

    def test_save_binary_rejected(self, client, temp_dir):
        path = os.path.join(temp_dir, "image.png").replace("\\", "/")
        r = client.post(
            "/api/save-file",
            json={"path": path, "content": "test"},
        )
        assert r.status_code == 400


# ════════════════════════════════════════════════
# /api/delete
# ════════════════════════════════════════════════
class TestDelete:
    def test_delete_file(self, client, temp_dir):
        # 先创建一个临时文件
        fpath = os.path.join(temp_dir, "to_delete.txt")
        with open(fpath, "w") as f:
            f.write("delete me")
        path = fpath.replace("\\", "/")
        r = client.post("/api/delete", json={"path": path})
        assert r.status_code == 200
        assert r.get_json()["ok"] is True
        assert not os.path.exists(fpath)

    def test_delete_empty_dir(self, client, temp_dir):
        path = os.path.join(temp_dir, "empty_dir").replace("\\", "/")
        r = client.post("/api/delete", json={"path": path})
        assert r.status_code == 200

    def test_delete_nonempty_dir_without_recursive(self, client, temp_dir):
        path = os.path.join(temp_dir, "subdir").replace("\\", "/")
        r = client.post("/api/delete", json={"path": path, "recursive": False})
        assert r.status_code == 400
        data = r.get_json()
        assert data.get("not_empty") is True

    def test_delete_nonempty_dir_recursive(self, client, temp_dir):
        # 创建要删除的目录
        del_dir = os.path.join(temp_dir, "del_dir")
        os.makedirs(del_dir)
        with open(os.path.join(del_dir, "f.txt"), "w") as f:
            f.write("x")
        path = del_dir.replace("\\", "/")
        r = client.post("/api/delete", json={"path": path, "recursive": True})
        assert r.status_code == 200
        assert not os.path.exists(del_dir)

    def test_delete_nonexistent(self, client):
        r = client.post("/api/delete", json={"path": "/nonexistent/abc"})
        assert r.status_code == 404

    def test_delete_protected_system_dir(self, client, temp_dir, monkeypatch):
        """系统关键目录应受保护不被删除。"""
        # 不限制 ALLOWED_ROOTS 以便访问系统路径
        monkeypatch.setattr("file_browser.ALLOWED_ROOTS", [])
        # 尝试删除根目录（/）— 即使路径存在也应被拒绝
        if sys.platform == 'win32':
            r = client.post("/api/delete", json={"path": "C:\\", "recursive": True})
        else:
            r = client.post("/api/delete", json={"path": "/", "recursive": True})
        assert r.status_code == 403

    def test_delete_protected_extended_dirs(self, client, temp_dir, monkeypatch):
        """扩展的受保护目录也应被拒绝（A-Z盘符、/home、/opt等）。"""
        monkeypatch.setattr("file_browser.ALLOWED_ROOTS", [])
        if sys.platform == 'win32':
            for drive in ["D:\\", "E:\\", "Z:\\"]:
                r = client.post("/api/delete", json={"path": drive, "recursive": True})
                assert r.status_code in (403, 404), f"{drive} should be protected"
        else:
            for path in ["/home", "/opt", "/boot", "/usr/local"]:
                r = client.post("/api/delete", json={"path": path, "recursive": True})
                assert r.status_code in (403, 404), f"{path} should be protected"


# ════════════════════════════════════════════════
# /api/rename
# ════════════════════════════════════════════════
class TestRename:
    def test_rename_file(self, client, temp_dir):
        path = os.path.join(temp_dir, "hello.txt").replace("\\", "/")
        r = client.post(
            "/api/rename",
            json={"path": path, "name": "hello_renamed.txt"},
        )
        assert r.status_code == 200
        assert r.get_json()["ok"] is True
        assert os.path.isfile(os.path.join(temp_dir, "hello_renamed.txt"))
        assert not os.path.isfile(os.path.join(temp_dir, "hello.txt"))

    def test_rename_to_existing(self, client, temp_dir):
        path = os.path.join(temp_dir, "data.json").replace("\\", "/")
        r = client.post(
            "/api/rename",
            json={"path": path, "name": "readme.md"},  # 已存在
        )
        assert r.status_code == 409

    def test_rename_empty_name(self, client, temp_dir):
        path = os.path.join(temp_dir, "hello.txt").replace("\\", "/")
        r = client.post(
            "/api/rename",
            json={"path": path, "name": ""},
        )
        assert r.status_code == 400

    def test_rename_invalid_chars(self, client, temp_dir):
        path = os.path.join(temp_dir, "hello.txt").replace("\\", "/")
        r = client.post(
            "/api/rename",
            json={"path": path, "name": "bad:name.txt"},
        )
        assert r.status_code == 400


# ════════════════════════════════════════════════
# /api/copy
# ════════════════════════════════════════════════
class TestCopy:
    def test_copy_file(self, client, temp_dir):
        src = os.path.join(temp_dir, "hello.txt").replace("\\", "/")
        dest_dir = os.path.join(temp_dir, "subdir").replace("\\", "/")
        r = client.post(
            "/api/copy",
            json={"src": src, "dest_dir": dest_dir},
        )
        assert r.status_code == 200
        assert r.get_json()["ok"] is True
        assert os.path.isfile(os.path.join(temp_dir, "subdir", "hello.txt"))
        # 原文件仍在
        assert os.path.isfile(os.path.join(temp_dir, "hello.txt"))

    def test_copy_conflict_auto_rename(self, client, temp_dir):
        # 先复制一份到 subdir
        src = os.path.join(temp_dir, "hello.txt").replace("\\", "/")
        dest_dir = os.path.join(temp_dir, "subdir").replace("\\", "/")
        # subdir 已有 nested.txt，但没有 hello.txt
        client.post("/api/copy", json={"src": src, "dest_dir": dest_dir})
        # 再复制一次，应该自动重命名
        r = client.post("/api/copy", json={"src": src, "dest_dir": dest_dir})
        assert r.status_code == 200
        dest = r.get_json()["dest"]
        assert "copy" in dest.lower()


# ════════════════════════════════════════════════
# /api/move
# ════════════════════════════════════════════════
class TestMove:
    def test_move_file(self, client, temp_dir):
        # 创建要移动的文件
        src_path = os.path.join(temp_dir, "move_me.txt")
        with open(src_path, "w") as f:
            f.write("move test")
        src = src_path.replace("\\", "/")
        dest_dir = os.path.join(temp_dir, "subdir").replace("\\", "/")
        r = client.post(
            "/api/move",
            json={"src": src, "dest_dir": dest_dir},
        )
        assert r.status_code == 200
        assert r.get_json()["ok"] is True
        assert os.path.isfile(os.path.join(temp_dir, "subdir", "move_me.txt"))
        assert not os.path.isfile(src_path)

    def test_move_to_self(self, client, temp_dir):
        src = os.path.join(temp_dir, "subdir").replace("\\", "/")
        dest = os.path.join(temp_dir, "subdir").replace("\\", "/")
        r = client.post(
            "/api/move",
            json={"src": src, "dest_dir": dest},
        )
        assert r.status_code == 400

    def test_move_conflict(self, client, temp_dir):
        # subdir 已有 nested.txt
        src = os.path.join(temp_dir, "subdir", "nested.txt").replace("\\", "/")
        # 在 temp_dir 创建同名文件
        with open(os.path.join(temp_dir, "nested.txt"), "w") as f:
            f.write("conflict")
        dest_dir = temp_dir.replace("\\", "/")
        r = client.post(
            "/api/move",
            json={"src": src, "dest_dir": dest_dir},
        )
        assert r.status_code == 409


# ════════════════════════════════════════════════
# /api/clipboard POST
# ════════════════════════════════════════════════
class TestClipboardWrite:
    def test_set_clipboard(self, client):
        r = client.post(
            "/api/clipboard",
            json={"text": "shared text here"},
        )
        assert r.status_code == 200
        assert r.get_json()["ok"] is True
        # 读回来验证
        r2 = client.get("/api/clipboard")
        assert r2.get_json()["text"] == "shared text here"


# ════════════════════════════════════════════════
# /api/bookmarks POST / DELETE
# ════════════════════════════════════════════════
class TestBookmarksWrite:
    def test_add_bookmark(self, client, temp_dir):
        r = client.post(
            "/api/bookmarks",
            json={"path": temp_dir, "name": "Test Bookmark"},
        )
        assert r.status_code == 200
        assert r.get_json()["ok"] is True
        # 验证添加了
        r2 = client.get("/api/bookmarks")
        bms = r2.get_json()
        assert len(bms) == 1
        assert bms[0]["path"] == temp_dir

    def test_add_duplicate_bookmark(self, client, temp_dir):
        client.post("/api/bookmarks", json={"path": temp_dir})
        r = client.post("/api/bookmarks", json={"path": temp_dir})
        assert r.status_code == 409

    def test_delete_bookmark(self, client, temp_dir):
        client.post("/api/bookmarks", json={"path": temp_dir})
        r = client.delete(
            "/api/bookmarks",
            json={"path": temp_dir},
        )
        assert r.status_code == 200
        r2 = client.get("/api/bookmarks")
        assert len(r2.get_json()) == 0


# ════════════════════════════════════════════════
# /api/batch-download
# ════════════════════════════════════════════════
class TestBatchDownload:
    def test_batch_download(self, client, temp_dir):
        paths = [
            os.path.join(temp_dir, "hello.txt").replace("\\", "/"),
            os.path.join(temp_dir, "data.json").replace("\\", "/"),
        ]
        r = client.post(
            "/api/batch-download",
            json={"paths": paths},
        )
        assert r.status_code == 200
        assert r.content_type == "application/zip"
        # 验证是有效的 ZIP
        zf = zipfile.ZipFile(io.BytesIO(r.data))
        names = zf.namelist()
        assert "hello.txt" in names
        assert "data.json" in names

    def test_batch_download_empty(self, client):
        r = client.post("/api/batch-download", json={"paths": []})
        assert r.status_code == 400


# ════════════════════════════════════════════════
# /api/download-folder
# ════════════════════════════════════════════════
class TestDownloadFolder:
    def test_download_folder_as_zip(self, client, temp_dir):
        path = os.path.join(temp_dir, "subdir").replace("\\", "/")
        r = client.get(f"/api/download-folder?path={path}")
        assert r.status_code == 200
        assert r.content_type == "application/zip"
        zf = zipfile.ZipFile(io.BytesIO(r.data))
        names = zf.namelist()
        assert any("nested.txt" in n for n in names)


# ════════════════════════════════════════════════
# /api/extract
# ════════════════════════════════════════════════
class TestExtract:
    def test_extract_zip(self, client, temp_dir):
        zip_path = os.path.join(temp_dir, "archive.zip").replace("\\", "/")
        dest_dir = os.path.join(temp_dir, "subdir").replace("\\", "/")
        r = client.post(
            "/api/extract",
            json={"path": zip_path, "dest_dir": dest_dir},
        )
        assert r.status_code == 200
        assert r.get_json()["ok"] is True
        assert os.path.isfile(os.path.join(temp_dir, "subdir", "inside.txt"))

    def test_extract_nonexistent_zip(self, client, temp_dir):
        dest_dir = temp_dir.replace("\\", "/")
        r = client.post(
            "/api/extract",
            json={"path": "/nonexistent/abc.zip", "dest_dir": dest_dir},
        )
        assert r.status_code == 404


# ════════════════════════════════════════════════
# 只读模式
# ════════════════════════════════════════════════
class TestReadOnly:
    """所有写操作在只读模式下应返回 403。"""

    def test_upload_forbidden(self, readonly_client, temp_dir):
        r = readonly_client.post(
            "/api/upload",
            data={"path": temp_dir, "files": (io.BytesIO(b"x"), "f.txt")},
            content_type="multipart/form-data",
        )
        assert r.status_code == 403

    def test_mkdir_forbidden(self, readonly_client, temp_dir):
        r = readonly_client.post(
            "/api/mkdir",
            json={"path": temp_dir, "name": "nope"},
        )
        assert r.status_code == 403

    def test_mkfile_forbidden(self, readonly_client, temp_dir):
        r = readonly_client.post(
            "/api/mkfile",
            json={"path": temp_dir, "name": "nope.txt"},
        )
        assert r.status_code == 403

    def test_delete_forbidden(self, readonly_client, temp_dir):
        path = os.path.join(temp_dir, "hello.txt").replace("\\", "/")
        r = readonly_client.post("/api/delete", json={"path": path})
        assert r.status_code == 403

    def test_rename_forbidden(self, readonly_client, temp_dir):
        path = os.path.join(temp_dir, "hello.txt").replace("\\", "/")
        r = readonly_client.post(
            "/api/rename",
            json={"path": path, "name": "new.txt"},
        )
        assert r.status_code == 403

    def test_save_forbidden(self, readonly_client, temp_dir):
        path = os.path.join(temp_dir, "hello.txt").replace("\\", "/")
        r = readonly_client.post(
            "/api/save-file",
            json={"path": path, "content": "nope"},
        )
        assert r.status_code == 403

    def test_copy_forbidden(self, readonly_client, temp_dir):
        src = os.path.join(temp_dir, "hello.txt").replace("\\", "/")
        dest = os.path.join(temp_dir, "subdir").replace("\\", "/")
        r = readonly_client.post(
            "/api/copy",
            json={"src": src, "dest_dir": dest},
        )
        assert r.status_code == 403

    def test_move_forbidden(self, readonly_client, temp_dir):
        src = os.path.join(temp_dir, "hello.txt").replace("\\", "/")
        dest = os.path.join(temp_dir, "subdir").replace("\\", "/")
        r = readonly_client.post(
            "/api/move",
            json={"src": src, "dest_dir": dest},
        )
        assert r.status_code == 403

    def test_clipboard_write_forbidden(self, readonly_client):
        r = readonly_client.post(
            "/api/clipboard",
            json={"text": "nope"},
        )
        assert r.status_code == 403

    def test_extract_forbidden(self, readonly_client, temp_dir):
        zip_path = os.path.join(temp_dir, "archive.zip").replace("\\", "/")
        r = readonly_client.post(
            "/api/extract",
            json={"path": zip_path, "dest_dir": temp_dir},
        )
        assert r.status_code == 403

    def test_read_operations_allowed(self, readonly_client, temp_dir):
        """只读模式下读操作应正常。"""
        r = readonly_client.get(f"/api/list?path={temp_dir}")
        assert r.status_code == 200
        path = os.path.join(temp_dir, "hello.txt").replace("\\", "/")
        r = readonly_client.get(f"/api/file?path={path}")
        assert r.status_code == 200
        r = readonly_client.get(f"/api/download?path={path}")
        assert r.status_code == 200


# ════════════════════════════════════════════════
# .DS_Store / 系统隐藏文件过滤
# ════════════════════════════════════════════════
class TestSystemHiddenFiles:
    def test_ds_store_filtered(self, client, temp_dir):
        """api_list 应过滤 .DS_Store 等系统隐藏文件。"""
        # 创建 .DS_Store 和 Thumbs.db
        for name in [".DS_Store", "Thumbs.db", "desktop.ini"]:
            with open(os.path.join(temp_dir, name), "w") as f:
                f.write("system")
        r = client.get(f"/api/list?path={temp_dir}")
        assert r.status_code == 200
        names = [item["name"] for item in r.get_json()["items"]]
        assert ".DS_Store" not in names
        assert "Thumbs.db" not in names
        assert "desktop.ini" not in names
        # 正常文件应仍然可见
        assert "hello.txt" in names


# ════════════════════════════════════════════════
# 多用户剪贴板隔离
# ════════════════════════════════════════════════
class TestMultiUserClipboard:
    def test_clipboard_isolated_per_user(self, multiuser_client, temp_dir):
        """不同用户的剪贴板应互相隔离。"""
        from tests.conftest import login
        # admin 设置剪贴板
        login(multiuser_client, "adminpass")
        multiuser_client.post("/api/clipboard", json={"text": "admin secret"})
        r = multiuser_client.get("/api/clipboard")
        assert r.get_json()["text"] == "admin secret"

        # 切换到 reader（新 session）— 用新客户端模拟
        # 直接用同一 client 重新登录即可（cookie 会被覆盖）
        login(multiuser_client, "readpass")
        r = multiuser_client.get("/api/clipboard")
        # reader 不应看到 admin 的剪贴板内容
        assert r.get_json()["text"] == ""


# ════════════════════════════════════════════════
# 多用户书签隔离
# ════════════════════════════════════════════════
class TestMultiUserBookmarks:
    def test_bookmarks_isolated_per_user(self, multiuser_client, temp_dir):
        """不同用户的书签应互相隔离。"""
        from tests.conftest import login
        # admin 添加书签
        login(multiuser_client, "adminpass")
        multiuser_client.post("/api/bookmarks", json={"path": temp_dir, "name": "Admin BM"})
        r = multiuser_client.get("/api/bookmarks")
        assert len(r.get_json()) == 1

        # reader 看不到 admin 的书签
        login(multiuser_client, "readpass")
        r = multiuser_client.get("/api/bookmarks")
        assert len(r.get_json()) == 0


# ════════════════════════════════════════════════
# save_bookmarks 异常处理
# ════════════════════════════════════════════════
class TestSaveBookmarksError:
    def test_save_bookmarks_handles_io_error(self, client, temp_dir, monkeypatch):
        """save_bookmarks 写入失败时不应崩溃。"""
        import file_browser
        # 模拟 open() 抛出 IOError
        original_open = open
        def mock_open(path, *args, **kwargs):
            if "bookmarks" in str(path) and "w" in str(args):
                raise IOError("disk full")
            return original_open(path, *args, **kwargs)
        monkeypatch.setattr("builtins.open", mock_open)
        # 调用不应抛异常
        file_browser.save_bookmarks([{"path": "/test", "name": "x"}])
        # 通过 — 没有抛出异常即为成功

[中文](API.md) | **English**

# API Documentation

> Back to [README](../README_EN.md)

All `/api/*` endpoints (except login and check-auth) require authentication. Unauthenticated requests return `401`.

---

## Authentication

| Method | Path | Description | Request Body |
|--------|------|-------------|--------------|
| POST | `/api/login` | Login (rate limited: 10 attempts/min/IP) | `{"password":"xxx"}` |
| GET | `/api/check-auth` | Check login status | - |

---

## Browsing

| Method | Path | Parameters | Description |
|--------|------|------------|-------------|
| GET | `/api/drives` | - | Get disk/drive list |
| GET | `/api/list` | `path`, `sort`(name/size/ctime/mtime), `order`(asc/desc), `filter_type`, `filter_ext` | List directory contents |
| GET | `/api/info` | `path` | File/directory detailed info |
| GET | `/api/folder-size` | `path` | Calculate folder size (recursive, 30s timeout) |

---

## Search

| Method | Path | Parameters | Description |
|--------|------|------------|-------------|
| GET | `/api/search` | `path`, `q`, `regex`(0/1) | Search by filename (supports regex) |
| GET | `/api/search-content` | `path`, `q`, `regex`(0/1) | Search file contents (supports regex) |

---

## Preview & Download

| Method | Path | Parameters/Body | Description |
|--------|------|-----------------|-------------|
| GET | `/api/file` | `path` | Get text file content |
| GET | `/api/raw` | `path` | Return raw file (images/videos, etc.) |
| GET | `/api/download` | `path` | Download single file |
| GET | `/api/download-folder` | `path` | Package folder as zip download |
| POST | `/api/batch-download` | `{"paths":[...]}` | Batch package download |
| GET | `/api/zip-list` | `path` | List ZIP file contents |

---

## File Management

| Method | Path | Request Body | Description |
|--------|------|--------------|-------------|
| POST | `/api/upload` | FormData: `path` + `files` | Upload files (supports multiple) |
| POST | `/api/mkdir` | `{"path":"parent_dir","name":"name"}` | Create folder |
| POST | `/api/mkfile` | `{"path":"parent_dir","name":"filename","content":"initial content"}` | Create file |
| POST | `/api/delete` | `{"path":"path","recursive":false}` | Delete (recursive=true for non-empty folders) |
| POST | `/api/rename` | `{"path":"original_path","name":"new_name"}` | Rename |
| POST | `/api/save-file` | `{"path":"path","content":"content"}` | Save edit (auto .bak backup) |
| POST | `/api/copy` | `{"src":"source_path","dest_dir":"target_directory"}` | Copy file/folder |
| POST | `/api/move` | `{"src":"source_path","dest_dir":"target_directory"}` | Move file/folder |
| POST | `/api/extract` | `{"path":"zip_path","dest_dir":"extract_directory"}` | Extract ZIP file |

---

## Sharing

| Method | Path | Body/Parameters | Description |
|--------|------|-----------------|-------------|
| POST | `/api/share` | `{"path":"file_path","expires":3600}` | Generate temporary share link (60s ~ 24h) |
| GET | `/share/<token>` | - | Download file via token (**no login required**, returns 410 when expired) |

---

## Other

| Method | Path | Request Body | Description |
|--------|------|--------------|-------------|
| GET | `/api/clipboard` | - | Get clipboard content |
| POST | `/api/clipboard` | `{"text":"content"}` | Set clipboard |
| GET | `/api/bookmarks` | - | Get bookmark list |
| POST | `/api/bookmarks` | `{"path":"path","name":"name"}` | Add bookmark |
| DELETE | `/api/bookmarks` | `{"path":"path"}` | Delete bookmark |

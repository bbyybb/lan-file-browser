[中文](API.md) | **English**

# API Documentation

> Back to [README](../README_EN.md)

All `/api/*` endpoints (except login, check-auth, and logout) require authentication. Unauthenticated requests return `401`.

### Common Response Format

- Success: Returns JSON data with HTTP status `200`
- Failure: Returns `{"error": "error message"}` with status `400`/`401`/`403`/`404`/`410`/`429`/`500`
- Error messages are automatically returned in Chinese or English based on client language preference
- Internal server errors (`500`) return a generic message `{"error": "Internal server error"}` (Chinese: `"内部服务器错误"`) without exposing internal implementation details
- All responses include a `Content-Security-Policy` security header to restrict resource loading origins and prevent XSS and other injection attacks
- **CSRF Protection**: All POST requests (except `/api/login`) must include the `X-Requested-With: XMLHttpRequest` custom header, otherwise `403` is returned

---

## Authentication

| Method | Path | Description | Request Body |
|--------|------|-------------|--------------|
| POST | `/api/login` | Login (rate limited: 10 attempts/min/IP) | `{"password":"xxx"}` |
| GET | `/api/check-auth` | Check login status | - |
| POST | `/api/logout` | Logout (clears session and cookie) | `{}` |

**Response examples:**

```jsonc
// POST /api/login success (token is sent via Set-Cookie, not in response body)
{"ok": true}
// In multi-user mode, user and role are also returned:
{"ok": true, "user": "admin", "role": "admin"}

// POST /api/login failure
{"ok": false, "error": "Wrong password"}   // 401

// GET /api/check-auth
{"need_auth": true, "logged_in": true, "read_only": false, "role": "admin"}

// POST /api/logout
{"ok": true}
```

---

## Browsing

| Method | Path | Parameters | Description |
|--------|------|------------|-------------|
| GET | `/api/drives` | - | Get disk/drive list |
| GET | `/api/list` | `path`, `sort`(name/size/ctime/mtime), `order`(asc/desc), `filter_type`, `filter_ext` | List directory contents |
| GET | `/api/info` | `path` | File/directory detailed info |
| GET | `/api/folder-size` | `path` | Calculate folder size (recursive, 30s timeout) |

**Response examples:**

```jsonc
// GET /api/drives
[{"path": "C:\\", "name": "C:\\"}, {"path": "D:\\", "name": "D:\\"}]

// GET /api/list?path=D:/docs&sort=name&order=asc
{
  "path": "D:/docs",
  "parent": "D:/",
  "items": [
    {"name": "readme.txt", "path": "D:/docs/readme.txt", "is_dir": false,
     "size": 1234, "size_str": "1.2 KB", "modified": "2026-03-01 10:30",
     "created": "2026-02-15 09:00", "mtime": 1740000000, "ctime": 1739000000,
     "type": "text", "ext": ".txt", "icon": "📝"}
  ]
}

// GET /api/folder-size?path=D:/docs
{"size": 13107200, "size_str": "12.5 MB"}
```

---

## Search

| Method | Path | Parameters | Description |
|--------|------|------------|-------------|
| GET | `/api/search` | `path`, `q`, `regex`(0/1) | Search by filename (supports regex) |
| GET | `/api/search-content` | `path`, `q`, `regex`(0/1) | Search file contents (supports regex) |

**Response examples:**

```jsonc
// GET /api/search?path=D:/docs&q=readme
{
  "results": [
    {"name": "readme.txt", "path": "D:/docs/readme.txt", "is_dir": false,
     "size_str": "1.2 KB", "modified": "2026-03-01 10:30",
     "type": "text", "icon": "📝", "dir": "D:/docs"}
  ],
  "total": 1
}

// GET /api/search-content?path=D:/docs&q=hello
{
  "results": [
    {"name": "readme.txt", "path": "D:/docs/readme.txt", "dir": "D:/docs",
     "size_str": "1.2 KB", "type": "text", "icon": "📝",
     "matches": [
       {"line": 3, "text": "Hello, welcome to LAN File Browser!"}
     ]}
  ],
  "total": 1,
  "files_scanned": 15
}
```

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

**Response examples:**

```jsonc
// GET /api/file?path=D:/docs/readme.txt
{"content": "File text content...", "ext": "txt", "size": "1.2 KB"}

// GET /api/zip-list?path=D:/docs/archive.zip
{
  "items": [
    {"name": "inside.txt", "size": "128 B", "is_dir": false, "compressed": "96 B"},
    {"name": "subdir/", "size": "0 B", "is_dir": true, "compressed": "0 B"}
  ],
  "count": 2
}

// POST /api/batch-download  (returns zip stream, Content-Type: application/zip)
// GET /api/download         (returns file stream, Content-Disposition: attachment)
// GET /api/download-folder  (returns zip stream)
// GET /api/raw              (returns raw file, Content-Type auto-detected)
```

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

**Response examples:**

```jsonc
// POST /api/upload (FormData upload)
{"saved": ["photo.jpg", "doc.pdf"], "errors": [], "count": 2}

// POST /api/mkdir
{"ok": true, "path": "D:/docs/new_folder"}

// POST /api/mkfile
{"ok": true, "path": "D:/docs/notes.txt"}

// POST /api/delete
{"ok": true}

// POST /api/rename
{"ok": true, "new_path": "D:/docs/renamed.txt"}

// POST /api/save-file (auto .bak backup)
{"ok": true, "size": "2.5 KB", "backup": "readme.txt.bak"}

// POST /api/copy
{"ok": true, "dest": "D:/backup/readme.txt"}

// POST /api/move
{"ok": true, "dest": "D:/backup/readme.txt"}

// POST /api/extract
{"ok": true}
```

---

## Sharing

| Method | Path | Body/Parameters | Description |
|--------|------|-----------------|-------------|
| POST | `/api/share` | `{"path":"file_path","expires":3600}` | Generate temporary share link (60s ~ 24h) |
| GET | `/share/<token>` | - | Download file via token (**no login required**, returns 410 when expired) |

**Response examples:**

```jsonc
// POST /api/share
{"ok": true, "token": "aBcDeFgH12345678", "url": "/share/aBcDeFgH12345678", "expires_in": 3600}

// GET /share/<token> (returns file stream, Content-Disposition: attachment)
// Token expired: 410 Gone
// Token not found: 404 Not Found
```

---

## Other

| Method | Path | Request Body | Description |
|--------|------|--------------|-------------|
| GET | `/api/clipboard` | - | Get clipboard content |
| POST | `/api/clipboard` | `{"text":"content"}` | Set clipboard |
| GET | `/api/bookmarks` | - | Get bookmark list |
| POST | `/api/bookmarks` | `{"path":"path","name":"name"}` | Add bookmark |
| DELETE | `/api/bookmarks` | `{"path":"path"}` | Delete bookmark |

**Response examples:**

```jsonc
// GET /api/clipboard
{"text": "Shared text content", "updated": "2026-03-30 14:30:00"}

// POST /api/clipboard
{"ok": true}

// GET /api/bookmarks
[{"path": "D:/docs", "name": "Documents", "created": "2026-03-30 14:00"}]

// POST /api/bookmarks
{"ok": true}

// DELETE /api/bookmarks
{"ok": true}
```

> **Multi-user mode note**: Clipboard data is isolated per user — each user can only read and write their own clipboard content. Bookmark data is also stored independently per user, so different users' bookmarks do not interfere with each other.

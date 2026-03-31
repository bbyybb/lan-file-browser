[中文](API.md) | **English**

# API Documentation

> Back to [README](../README_EN.md)

All `/api/*` endpoints (except login, check-auth, and logout) require authentication. Unauthenticated requests return `401`.

### Common Response Format

- Success: Returns JSON data with HTTP status `200`
- Failure: Returns `{"error": "error message"}` with status `400`/`401`/`403`/`404`/`409`/`410`/`429`/`500`
- `409` indicates a name conflict (during copy/move/extract), response includes `"conflict": true`
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
| POST | `/api/upload` | FormData: `path` + `files` + `relativePaths`(optional) + `conflict`(optional) | Upload files (supports multiple files and folder upload) |
| POST | `/api/mkdir` | `{"path":"parent_dir","name":"name"}` | Create folder |
| POST | `/api/mkfile` | `{"path":"parent_dir","name":"filename","content":"initial content"}` | Create file |
| POST | `/api/delete` | `{"path":"path","recursive":false,"stream":false}` | Delete (recursive=true for non-empty folders, stream=true for streaming progress) |
| POST | `/api/rename` | `{"path":"original_path","name":"new_name"}` | Rename |
| POST | `/api/save-file` | `{"path":"path","content":"content"}` | Save edit (auto .bak backup) |
| POST | `/api/copy` | `{"src":"source_path","dest_dir":"target_dir","conflict":"...","stream":false}` | Copy file/folder (stream=true for streaming progress) |
| POST | `/api/move` | `{"src":"source_path","dest_dir":"target_dir","conflict":"...","stream":false}` | Move file/folder (stream=true for streaming progress) |
| POST | `/api/extract` | `{"path":"zip_path","dest_dir":"extract_dir","conflict":"...","stream":false}` | Extract ZIP file (stream=true for streaming progress) |
| POST | `/api/upload-init` | `{"filename":"name","size":number,"path":"target_dir"}` | Initialize chunked upload (files ≥5MB) |
| POST | `/api/upload-chunk` | FormData: `upload_id` + `index` + `chunk` | Upload a single chunk (5MB/chunk) |
| POST | `/api/upload-complete` | `{"upload_id":"ID","conflict":"..."}` | Merge chunks and complete upload |
| POST | `/api/upload-cancel` | `{"upload_id":"ID"}` | Cancel chunked upload (clean up temp files) |
| GET | `/api/upload-status` | `upload_id` | Query chunked upload progress |

> **`conflict` parameter** (applies to copy / move / upload / extract):
> - Not provided (default): returns `409` when a name conflict is detected, prompting the user to choose
> - `"overwrite"`: replace the existing file/folder
> - `"rename"`: auto-rename (keep both, e.g. `file_copy1.txt`)
> - `"skip"`: skip, do not perform the operation
>
> For upload, `conflict` defaults to `"rename"` (backward compatible).

> **`stream` parameter** (applies to copy / move / delete / extract):
> - Not provided or `false` (default): returns JSON result after operation completes
> - `true`: returns a streaming response with `Content-Type: application/x-ndjson` (Newline Delimited JSON), one JSON object per line, pushing progress in real time

### Streaming Progress Response

When `"stream": true` is set in the request, the server returns an NDJSON (Newline Delimited JSON) streaming response, with one JSON object per line. Available for `/api/copy`, `/api/move`, `/api/delete`, and `/api/extract`.

**Response headers:**
```
Content-Type: application/x-ndjson
Transfer-Encoding: chunked
```

**Progress message format:**

```jsonc
// Large file copy/move — byte-level progress
{"type": "progress", "current": 471859200, "total": 1073741824, "percent": 44, "speed": "125.3 MB/s"}

// Recursive delete — file count progress
{"type": "progress", "current": 150, "total": 300, "percent": 50}

// ZIP extraction — file count progress
{"type": "progress", "current": 75, "total": 200, "percent": 38}

// Batch operations — file index + per-file progress
{"type": "progress", "file_index": 3, "file_total": 10, "current": 5242880, "total": 10485760, "percent": 50}

// Operation complete
{"type": "complete", "ok": true, "dest": "D:/backup/readme.txt"}

// Operation failed
{"type": "error", "error": "Target directory does not exist"}
```

**Usage example (JavaScript):**

```javascript
const response = await fetch('/api/copy', {
  method: 'POST',
  headers: {'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest'},
  body: JSON.stringify({src: 'D:/large-file.zip', dest_dir: 'E:/backup', stream: true})
});
const reader = response.body.getReader();
const decoder = new TextDecoder();
let buffer = '';
while (true) {
  const {done, value} = await reader.read();
  if (done) break;
  buffer += decoder.decode(value, {stream: true});
  const lines = buffer.split('\n');
  buffer = lines.pop();
  for (const line of lines) {
    if (line.trim()) {
      const msg = JSON.parse(line);
      if (msg.type === 'progress') {
        console.log(`Progress: ${msg.percent}%`);
      }
    }
  }
}
```

**Response examples:**

```jsonc
// POST /api/upload (FormData upload)
// Standard upload: FormData contains path (target directory), files (file list), conflict (optional: overwrite/rename/skip, default: rename)
// Folder upload: additionally includes relativePaths (JSON array of relative paths, e.g. ["dir/a.txt", "dir/sub/b.txt"])
//                Server auto-creates subdirectories and preserves directory structure
{"saved": ["photo.jpg", "doc.pdf"], "skipped": [], "errors": [], "count": 2}

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

// POST /api/copy — no conflict
{"ok": true, "dest": "D:/backup/readme.txt"}

// POST /api/copy — name conflict (no conflict param, returns 409)
// 409: {"error": "A file/folder with the same name already exists", "conflict": true, "name": "readme.txt"}

// POST /api/copy — conflict=rename
{"ok": true, "dest": "D:/backup/readme_copy1.txt"}

// POST /api/copy — conflict=skip
{"ok": true, "skipped": true, "dest": "D:/backup/readme.txt"}

// POST /api/move (conflict param same as copy)
{"ok": true, "dest": "D:/backup/readme.txt"}

// POST /api/extract — no conflict
{"ok": true}

// POST /api/extract — name conflict (no conflict param, returns 409)
// 409: {"error": "...", "conflict": true, "files": ["inside.txt", "data.csv"], "total": 2}
```

### Chunked Resumable Upload

Large files (≥5MB) automatically use chunked upload with 5MB per chunk. Supports pause/resume/cancel operations and recovery after network interruptions. Temporary files are auto-cleaned after 24 hours.

**Upload flow:** `upload-init` → multiple `upload-chunk` → `upload-complete`

| Method | Path | Body/Parameters | Description |
|--------|------|-----------------|-------------|
| POST | `/api/upload-init` | `{"filename":"largefile.zip","size":52428800,"path":"D:/uploads"}` | Initialize upload, returns `upload_id` and chunk info |
| POST | `/api/upload-chunk` | FormData: `upload_id`(upload ID) + `index`(chunk index, 0-based) + `chunk`(chunk file data) | Upload a single chunk |
| POST | `/api/upload-complete` | `{"upload_id":"abc123","conflict":"rename"}` | Merge all chunks, complete upload |
| POST | `/api/upload-cancel` | `{"upload_id":"abc123"}` | Cancel upload, clean up uploaded temp chunks |
| GET | `/api/upload-status` | `upload_id=abc123` | Query uploaded chunks list and progress |

**Response examples:**

```jsonc
// POST /api/upload-init
// Request: {"filename": "largefile.zip", "size": 52428800, "path": "D:/uploads"}
{"upload_id": "abc123def456", "chunk_size": 5242880, "total_chunks": 10}

// POST /api/upload-chunk (FormData: upload_id + index + chunk)
{"ok": true, "index": 0}

// POST /api/upload-complete
// Request: {"upload_id": "abc123def456", "conflict": "rename"}
{"ok": true, "path": "D:/uploads/largefile.zip", "size": "50.0 MB"}

// POST /api/upload-cancel
// Request: {"upload_id": "abc123def456"}
{"ok": true}

// GET /api/upload-status?upload_id=abc123def456
{"upload_id": "abc123def456", "filename": "largefile.zip", "size": 52428800, "chunk_size": 5242880, "total_chunks": 10, "uploaded_chunks": [0, 1, 2, 3], "completed": false}
```

> **Note**: All chunked upload endpoints require authentication and the CSRF header. Temporary chunk files are stored in a server-side temp directory and auto-cleaned after 24 hours if not completed.

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

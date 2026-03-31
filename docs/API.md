**中文** | [English](API_EN.md)

# API 接口文档

> 返回 [README](../README.md)

所有 `/api/*` 接口（除 login、check-auth、logout 外）均需登录后才能访问，未登录返回 `401`。

### 通用响应格式

- 成功：返回 JSON 数据，HTTP 状态码 `200`
- 失败：返回 `{"error": "错误信息"}`，状态码为 `400`/`401`/`403`/`404`/`409`/`410`/`429`/`500`
- `409` 表示同名冲突（复制/移动/解压时），响应包含 `"conflict": true` 标记
- 错误消息根据客户端语言偏好自动返回中文或英文
- 服务器内部错误（`500`）返回通用错误消息 `{"error": "内部服务器错误"}`（英文：`"Internal server error"`），不暴露内部实现细节
- 所有响应包含 `Content-Security-Policy` 安全头，限制资源加载来源，防范 XSS 等注入攻击
- **CSRF 保护**：所有 POST 请求（除 `/api/login` 外）须携带 `X-Requested-With: XMLHttpRequest` 自定义请求头，否则返回 `403`

---

## 认证

| 方法 | 路径 | 说明 | 请求体 |
|------|------|------|--------|
| POST | `/api/login` | 登录（限速 10次/分钟/IP） | `{"password":"xxx"}` |
| GET | `/api/check-auth` | 检查登录状态 | - |
| POST | `/api/logout` | 登出（清除 session 和 cookie） | `{}` |

**响应示例：**

```jsonc
// POST /api/login 成功（token 通过 Set-Cookie 发送，不在响应体中）
{"ok": true}
// 多用户模式下还会返回 user 和 role:
{"ok": true, "user": "admin", "role": "admin"}

// POST /api/login 失败
{"ok": false, "error": "密码错误"}   // 401

// GET /api/check-auth
{"need_auth": true, "logged_in": true, "read_only": false, "role": "admin"}

// POST /api/logout
{"ok": true}
```

---

## 浏览

| 方法 | 路径 | 参数 | 说明 |
|------|------|------|------|
| GET | `/api/drives` | - | 获取磁盘列表 |
| GET | `/api/list` | `path`, `sort`(name/size/ctime/mtime), `order`(asc/desc), `filter_type`, `filter_ext` | 列出目录内容 |
| GET | `/api/info` | `path` | 文件/目录详细信息 |
| GET | `/api/folder-size` | `path` | 计算文件夹大小（递归，30 秒超时） |

**响应示例：**

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

## 搜索

| 方法 | 路径 | 参数 | 说明 |
|------|------|------|------|
| GET | `/api/search` | `path`, `q`, `regex`(0/1) | 按文件名搜索（支持正则） |
| GET | `/api/search-content` | `path`, `q`, `regex`(0/1) | 搜索文件内部文字（支持正则） |

**响应示例：**

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

## 预览与下载

| 方法 | 路径 | 参数/请求体 | 说明 |
|------|------|------------|------|
| GET | `/api/file` | `path` | 获取文本文件内容 |
| GET | `/api/raw` | `path` | 返回原始文件（图片/视频等） |
| GET | `/api/download` | `path` | 下载单个文件 |
| GET | `/api/download-folder` | `path` | 将文件夹打包为 zip 下载 |
| POST | `/api/batch-download` | `{"paths":[...]}` | 批量打包下载 |
| GET | `/api/zip-list` | `path` | 列出 ZIP 文件内容 |

**响应示例：**

```jsonc
// GET /api/file?path=D:/docs/readme.txt
{"content": "文件文本内容...", "ext": "txt", "size": "1.2 KB"}

// GET /api/zip-list?path=D:/docs/archive.zip
{
  "items": [
    {"name": "inside.txt", "size": "128 B", "is_dir": false, "compressed": "96 B"},
    {"name": "subdir/", "size": "0 B", "is_dir": true, "compressed": "0 B"}
  ],
  "count": 2
}

// POST /api/batch-download  （返回 zip 文件流，Content-Type: application/zip）
// GET /api/download         （返回文件流，Content-Disposition: attachment）
// GET /api/download-folder  （返回 zip 文件流）
// GET /api/raw              （返回原始文件，Content-Type 自动匹配）
```

---

## 文件管理

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| POST | `/api/upload` | FormData: `path` + `files` + `relativePaths`(可选) + `conflict`(可选) | 上传文件（支持多文件、目录上传） |
| POST | `/api/mkdir` | `{"path":"父目录","name":"名称"}` | 新建文件夹 |
| POST | `/api/mkfile` | `{"path":"父目录","name":"文件名","content":"初始内容"}` | 新建文件 |
| POST | `/api/delete` | `{"path":"路径","recursive":false,"stream":false}` | 删除（recursive=true 递归删除非空文件夹，stream=true 流式进度） |
| POST | `/api/rename` | `{"path":"原路径","name":"新名"}` | 重命名 |
| POST | `/api/save-file` | `{"path":"路径","content":"内容"}` | 保存编辑（自动 .bak 备份） |
| POST | `/api/copy` | `{"src":"源路径","dest_dir":"目标目录","conflict":"...","stream":false}` | 复制文件/文件夹（stream=true 流式进度） |
| POST | `/api/move` | `{"src":"源路径","dest_dir":"目标目录","conflict":"...","stream":false}` | 移动文件/文件夹（stream=true 流式进度） |
| POST | `/api/extract` | `{"path":"zip路径","dest_dir":"解压目录","conflict":"...","stream":false}` | 解压 ZIP 文件（stream=true 流式进度） |
| POST | `/api/upload-init` | `{"filename":"文件名","size":数字,"path":"目标目录"}` | 初始化分片上传（文件≥5MB） |
| POST | `/api/upload-chunk` | FormData: `upload_id` + `index` + `chunk` | 上传单个分片（5MB/片） |
| POST | `/api/upload-complete` | `{"upload_id":"上传ID","conflict":"..."}` | 合并分片完成上传 |
| POST | `/api/upload-cancel` | `{"upload_id":"上传ID"}` | 取消分片上传（清理临时文件） |
| GET | `/api/upload-status` | `upload_id` | 查询分片上传进度 |

> **`conflict` 参数**（适用于 copy / move / upload / extract）：
> - 不传（默认）：检测到同名冲突时返回 `409`，前端弹窗让用户选择
> - `"overwrite"`：覆盖已有文件/文件夹
> - `"rename"`：自动重命名（保留两者，如 `file_copy1.txt`）
> - `"skip"`：跳过，不执行操作
>
> upload 的 `conflict` 默认值为 `"rename"`（向后兼容）。

> **`stream` 参数**（适用于 copy / move / delete / extract）：
> - 不传或 `false`（默认）：操作完成后一次性返回 JSON 结果
> - `true`：返回 `Content-Type: application/x-ndjson` 的流式响应（Newline Delimited JSON），每行一个 JSON 对象，实时推送操作进度

### 流式进度响应

当请求中设置 `"stream": true` 时，服务器返回 NDJSON（Newline Delimited JSON）格式的流式响应，每行一个 JSON 对象。适用于 `/api/copy`、`/api/move`、`/api/delete`、`/api/extract` 四个接口。

**响应头：**
```
Content-Type: application/x-ndjson
Transfer-Encoding: chunked
```

**进度消息格式：**

```jsonc
// 大文件复制/移动 — 字节级进度
{"type": "progress", "current": 471859200, "total": 1073741824, "percent": 44, "speed": "125.3 MB/s"}

// 递归删除 — 文件计数进度
{"type": "progress", "current": 150, "total": 300, "percent": 50}

// ZIP 解压 — 文件计数进度
{"type": "progress", "current": 75, "total": 200, "percent": 38}

// 批量操作 — 文件序号 + 单文件进度
{"type": "progress", "file_index": 3, "file_total": 10, "current": 5242880, "total": 10485760, "percent": 50}

// 操作完成
{"type": "complete", "ok": true, "dest": "D:/backup/readme.txt"}

// 操作失败
{"type": "error", "error": "目标目录不存在"}
```

**使用示例（JavaScript）：**

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
        console.log(`进度: ${msg.percent}%`);
      }
    }
  }
}
```

**响应示例：**

```jsonc
// POST /api/upload（FormData 上传）
// 普通上传：FormData 包含 path（目标目录）、files（文件列表）、conflict（可选: overwrite/rename/skip，默认 rename）
// 目录上传：额外包含 relativePaths（JSON 数组，与 files 一一对应的相对路径，如 ["dir/a.txt", "dir/sub/b.txt"]）
//          服务端将根据 relativePaths 自动创建子目录并保留目录结构
{"saved": ["photo.jpg", "doc.pdf"], "skipped": [], "errors": [], "count": 2}

// POST /api/mkdir
{"ok": true, "path": "D:/docs/新文件夹"}

// POST /api/mkfile
{"ok": true, "path": "D:/docs/notes.txt"}

// POST /api/delete
{"ok": true}

// POST /api/rename
{"ok": true, "new_path": "D:/docs/renamed.txt"}

// POST /api/save-file（自动创建 .bak 备份）
{"ok": true, "size": "2.5 KB", "backup": "readme.txt.bak"}

// POST /api/copy — 无冲突
{"ok": true, "dest": "D:/backup/readme.txt"}

// POST /api/copy — 同名冲突（未传 conflict 参数，返回 409）
// 409: {"error": "目标目录中已存在同名文件/文件夹", "conflict": true, "name": "readme.txt"}

// POST /api/copy — conflict=rename
{"ok": true, "dest": "D:/backup/readme_copy1.txt"}

// POST /api/copy — conflict=skip
{"ok": true, "skipped": true, "dest": "D:/backup/readme.txt"}

// POST /api/move（conflict 参数同 copy）
{"ok": true, "dest": "D:/backup/readme.txt"}

// POST /api/extract — 无冲突
{"ok": true}

// POST /api/extract — 同名冲突（未传 conflict 参数，返回 409）
// 409: {"error": "...", "conflict": true, "files": ["inside.txt", "data.csv"], "total": 2}
```

### 分片断点续传

大文件（≥5MB）自动启用分片上传，每片 5MB。支持暂停/继续/取消操作，网络中断后可恢复上传。临时文件 24 小时后自动清理。

**上传流程：** `upload-init` → 多次 `upload-chunk` → `upload-complete`

| 方法 | 路径 | 请求体/参数 | 说明 |
|------|------|------------|------|
| POST | `/api/upload-init` | `{"filename":"大文件.zip","size":52428800,"path":"D:/uploads"}` | 初始化上传，返回 `upload_id` 和分片信息 |
| POST | `/api/upload-chunk` | FormData: `upload_id`(上传ID) + `index`(分片序号，从0开始) + `chunk`(分片文件数据) | 上传单个分片 |
| POST | `/api/upload-complete` | `{"upload_id":"abc123","conflict":"rename"}` | 合并所有分片，完成上传 |
| POST | `/api/upload-cancel` | `{"upload_id":"abc123"}` | 取消上传，清理已上传的临时分片 |
| GET | `/api/upload-status` | `upload_id=abc123` | 查询已上传的分片列表和进度 |

**响应示例：**

```jsonc
// POST /api/upload-init
// 请求：{"filename": "大文件.zip", "size": 52428800, "path": "D:/uploads"}
{"upload_id": "abc123def456", "chunk_size": 5242880, "total_chunks": 10}

// POST /api/upload-chunk（FormData: upload_id + index + chunk）
{"ok": true, "index": 0}

// POST /api/upload-complete
// 请求：{"upload_id": "abc123def456", "conflict": "rename"}
{"ok": true, "path": "D:/uploads/大文件.zip", "size": "50.0 MB"}

// POST /api/upload-cancel
// 请求：{"upload_id": "abc123def456"}
{"ok": true}

// GET /api/upload-status?upload_id=abc123def456
{"upload_id": "abc123def456", "filename": "大文件.zip", "size": 52428800, "chunk_size": 5242880, "total_chunks": 10, "uploaded_chunks": [0, 1, 2, 3], "completed": false}
```

> **注意**：分片上传的所有接口均需登录认证和 CSRF Header。临时分片文件存储在服务端临时目录中，24 小时未完成的上传会被自动清理。

---

## 分享

| 方法 | 路径 | 请求体/参数 | 说明 |
|------|------|------------|------|
| POST | `/api/share` | `{"path":"文件路径","expires":3600}` | 生成临时分享链接（60s ~ 24h） |
| GET | `/share/<token>` | - | 通过 token 下载文件（**无需登录**，过期返回 410） |

**响应示例：**

```jsonc
// POST /api/share
{"ok": true, "token": "aBcDeFgH12345678", "url": "/share/aBcDeFgH12345678", "expires_in": 3600}

// GET /share/<token>（返回文件流，Content-Disposition: attachment）
// token 过期：410 Gone
// token 不存在：404 Not Found
```

---

## 其他

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| GET | `/api/clipboard` | - | 获取剪贴板内容 |
| POST | `/api/clipboard` | `{"text":"内容"}` | 设置剪贴板 |
| GET | `/api/bookmarks` | - | 获取书签列表 |
| POST | `/api/bookmarks` | `{"path":"路径","name":"名称"}` | 添加书签 |
| DELETE | `/api/bookmarks` | `{"path":"路径"}` | 删除书签 |

**响应示例：**

```jsonc
// GET /api/clipboard
{"text": "共享的文本内容", "updated": "2026-03-30 14:30:00"}

// POST /api/clipboard
{"ok": true}

// GET /api/bookmarks
[{"path": "D:/docs", "name": "文档", "created": "2026-03-30 14:00"}]

// POST /api/bookmarks
{"ok": true}

// DELETE /api/bookmarks
{"ok": true}
```

> **多用户模式说明**：剪贴板数据按用户隔离，每个用户只能读写自己的剪贴板内容。书签数据同样按用户独立存储，不同用户的收藏互不影响。

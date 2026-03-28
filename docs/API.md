**中文** | [English](API_EN.md)

# API 接口文档

> 返回 [README](../README.md)

所有 `/api/*` 接口（除 login、check-auth 外）均需登录后才能访问，未登录返回 `401`。

### 通用响应格式

- 成功：返回 JSON 数据，HTTP 状态码 `200`
- 失败：返回 `{"error": "错误信息"}`，状态码为 `400`/`401`/`403`/`404`/`410`/`429`/`500`
- 错误消息根据客户端语言偏好自动返回中文或英文

---

## 认证

| 方法 | 路径 | 说明 | 请求体 |
|------|------|------|--------|
| POST | `/api/login` | 登录（限速 10次/分钟/IP） | `{"password":"xxx"}` |
| GET | `/api/check-auth` | 检查登录状态 | - |

**响应示例：**

```jsonc
// POST /api/login 成功
{"ok": true, "token": "..."}

// POST /api/login 失败
{"error": "密码错误"}   // 403

// GET /api/check-auth
{"authenticated": true, "role": "admin"}
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
{"drives": ["C:\\", "D:\\"]}

// GET /api/list?path=D:/docs&sort=name&order=asc
{
  "path": "D:\\docs",
  "items": [
    {"name": "readme.txt", "is_dir": false, "size": "1.2 KB", "size_bytes": 1234,
     "mtime": "2026-03-01 10:30", "ctime": "2026-02-15 09:00", "type": "text", "ext": ".txt"}
  ]
}

// GET /api/folder-size?path=D:/docs
{"size": "12.5 MB", "size_bytes": 13107200}
```

---

## 搜索

| 方法 | 路径 | 参数 | 说明 |
|------|------|------|------|
| GET | `/api/search` | `path`, `q`, `regex`(0/1) | 按文件名搜索（支持正则） |
| GET | `/api/search-content` | `path`, `q`, `regex`(0/1) | 搜索文件内部文字（支持正则） |

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

---

## 文件管理

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| POST | `/api/upload` | FormData: `path` + `files` | 上传文件（支持多文件） |
| POST | `/api/mkdir` | `{"path":"父目录","name":"名称"}` | 新建文件夹 |
| POST | `/api/mkfile` | `{"path":"父目录","name":"文件名","content":"初始内容"}` | 新建文件 |
| POST | `/api/delete` | `{"path":"路径","recursive":false}` | 删除（recursive=true 递归删除非空文件夹） |
| POST | `/api/rename` | `{"path":"原路径","name":"新名"}` | 重命名 |
| POST | `/api/save-file` | `{"path":"路径","content":"内容"}` | 保存编辑（自动 .bak 备份） |
| POST | `/api/copy` | `{"src":"源路径","dest_dir":"目标目录"}` | 复制文件/文件夹 |
| POST | `/api/move` | `{"src":"源路径","dest_dir":"目标目录"}` | 移动文件/文件夹 |
| POST | `/api/extract` | `{"path":"zip路径","dest_dir":"解压目录"}` | 解压 ZIP 文件 |

---

## 分享

| 方法 | 路径 | 请求体/参数 | 说明 |
|------|------|------------|------|
| POST | `/api/share` | `{"path":"文件路径","expires":3600}` | 生成临时分享链接（60s ~ 24h） |
| GET | `/share/<token>` | - | 通过 token 下载文件（**无需登录**，过期返回 410） |

---

## 其他

| 方法 | 路径 | 请求体 | 说明 |
|------|------|--------|------|
| GET | `/api/clipboard` | - | 获取剪贴板内容 |
| POST | `/api/clipboard` | `{"text":"内容"}` | 设置剪贴板 |
| GET | `/api/bookmarks` | - | 获取书签列表 |
| POST | `/api/bookmarks` | `{"path":"路径","name":"名称"}` | 添加书签 |
| DELETE | `/api/bookmarks` | `{"path":"路径"}` | 删除书签 |

# Changelog / 更新日志

All notable changes to this project will be documented in this file.

本文件记录项目的所有重要变更。

The format is based on [Keep a Changelog](https://keepachangelog.com/).

---

## [v1.0.0] - 2026-04-07

### Added / 新增
- 密码保护（启动时自动生成 32 位随机密码） / Password protection (auto-generated 32-char random password)
- 访问日志记录，自动轮转（单文件最大 10MB，保留 5 份备份） / Access logging with auto-rotation (10MB per file, 5 backups)
- 文件上传功能 / File upload
- 批量文件打包下载 / Batch file ZIP download
- 文件内容搜索 / File content search
- 在线文本编辑器 / Online text editor
- Markdown 渲染（GFM + Mermaid 图表） / Markdown rendering (GFM + Mermaid diagrams)
- 代码语法高亮（40+ 语言） / Code syntax highlighting (40+ languages)
- 图片/视频/音频/PDF 在线预览 / Image/video/audio/PDF online preview
- 面包屑导航 / Breadcrumb navigation
- 目录白名单安全限制 / Directory whitelist (sandbox mode)
- 二维码快速扫码访问 / QR code for quick mobile access
- 交互式启动引导 / Interactive startup wizard
- 跨平台支持（Windows/macOS/Linux） / Cross-platform support (Windows/macOS/Linux)
- 中英双语界面 / Bilingual Chinese/English interface
- 多用户多密码模式（管理员 + 只读用户） / Multi-user multi-password mode (admin + read-only roles)
- 文件/文件夹复制与移动功能，可视化目录选择器 / File/folder copy & move with visual directory picker
- 批量操作（批量删除、批量移动、批量复制） / Batch operations (batch delete, move, copy)
- 文件夹整体打包下载 / Folder download as ZIP
- ZIP 文件在线预览与解压 / ZIP file preview and online extraction
- 临时分享链接（可自定义过期时间：5 分钟 / 30 分钟 / 1 小时 / 6 小时 / 12 小时 / 24 小时） / Temporary share links with custom expiration (5m / 30m / 1h / 6h / 12h / 24h)
- 视频字幕自动加载（.vtt/.srt/.ass） / Auto-load video subtitles (.vtt/.srt/.ass)
- Office 文件预览（docx/xlsx） / Office file preview (docx rendered as HTML, xlsx as table)
- 正则表达式搜索模式 / Regex search mode
- 多选模式一键全选/取消全选（文件和文件夹均支持） / Multi-select with select all/deselect all (files and folders)
- 网格/列表视图切换 / Grid/list view toggle
- 亮色/暗色主题切换 / Light/dark theme toggle
- 中/英语言切换 / Chinese/English language switch
- 阻止系统睡眠功能（跨平台） / Prevent system sleep (cross-platform)
- 共享剪贴板（手机-电脑文本互传，多用户隔离） / Shared clipboard (phone-PC text sharing, per-user isolation)
- 目录收藏/书签功能（多用户隔离） / Directory bookmark/favorites (per-user isolation)
- 只读模式（`--read-only`） / Read-only mode (`--read-only`)
- `--allow-sleep` 命令行参数 / `--allow-sleep` CLI argument
- 作者署名与资源完整性保护 / Author attribution and resource integrity protection
- 登出功能：`/api/logout` 接口 + 前端登出按钮 / Logout feature: `/api/logout` endpoint + frontend logout button
- CSRF 保护：所有 POST 请求通过 `X-Requested-With` Header 校验 / CSRF protection via `X-Requested-With` header validation
- 上传进度条：弹窗上传和拖拽上传均显示实时进度 / Upload progress bar for both dialog and drag-and-drop uploads
- 支持通过 `config.json` 配置文件设置参数 / Support `config.json` configuration file
- 可选 HTTPS 支持（`--ssl-cert` / `--ssl-key` 参数） / Optional HTTPS support via `--ssl-cert` / `--ssl-key` flags
- Content-Security-Policy (CSP) 安全响应头 / Content-Security-Policy (CSP) security headers
- 文件列表自动过滤系统隐藏文件 / Auto-filter system hidden files from directory listings
- 新增 80+ 种文本文件扩展名支持 / Added 80+ text file extension types
- 新增 40+ 种无扩展名文件名识别 / Added 40+ extensionless filename recognition
- 前端依赖库全部内置，离线无网络环境可正常使用 / All frontend vendor libraries bundled locally — fully functional offline
- DOMPurify XSS 净化库 / DOMPurify for XSS sanitization
- `_is_dangerous_regex()` ReDoS 防护 / `_is_dangerous_regex()` for ReDoS protection
- 安全响应头（`X-Content-Type-Options`、`X-Frame-Options`、`Referrer-Policy`） / Security headers via `@app.after_request`
- 扩展系统目录保护列表 / Extended protected system directory list
- `detect_encoding()` 编码检测函数，编辑保存文件时自动保留原始编码 / `detect_encoding()` function — file saves preserve original encoding
- Markdown 预览返回导航功能（支持多级历史栈） / Back navigation for Markdown preview with multi-level history stack
- GitHub Actions CI: 四平台自动构建可执行文件 / CI auto-build executables for Windows/macOS(Intel+Apple Silicon)/Linux
- Tag 触发自动发布到 GitHub Releases / Tag-triggered auto-release to GitHub Releases
- 复制/移动/删除/解压操作实时进度条 / Real-time progress bars for copy/move/delete/extract operations
- 大文件分片断点续传功能（≥5MB 自动启用，支持暂停/继续/取消） / Chunked resumable upload for large files (≥5MB, supports pause/resume/cancel)
- 目录上传功能：支持"选择文件夹"按钮和拖拽上传文件夹 / Folder upload: "Select Folder" button and drag-and-drop folder support
- 文件操作同名冲突对话框（覆盖/重命名保留两者/跳过） / File conflict dialog (Overwrite / Rename Keep Both / Skip)
- 批量下载和文件夹下载实时下载进度弹框 / Real-time progress dialog for batch/folder downloads
- 完整自动化测试套件（431 个测试用例） / Complete automated test suite (431 test cases)
- CI 多平台多 Python 版本矩阵测试 / CI multi-platform multi-Python version matrix testing
- 版本号集中管理（`__version__` 变量） / Centralized version management via `__version__`
- 线程安全锁保护共享状态 / Thread-safe locks for shared state
- `stop_server.bat/.sh` 停止服务器脚本 / Stop server scripts for Windows/macOS/Linux

[v1.0.0]: https://github.com/bbyybb/lan-file-browser/releases/tag/v1.0.0

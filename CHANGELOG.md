# Changelog / 更新日志

All notable changes to this project will be documented in this file.

本文件记录项目的所有重要变更。

The format is based on [Keep a Changelog](https://keepachangelog.com/).

---

## [v2.6.0] - 2026-03-31

### Added / 新增
- 复制/移动/删除/解压操作新增实时进度条，大文件显示字节级进度，批量操作显示文件计数 / Added real-time progress bars for copy/move/delete/extract operations with byte-level progress for large files and file count for batch operations
- 新增大文件分片断点续传功能，文件≥5MB自动启用分片上传(5MB/片)，支持暂停/继续/取消，网络中断后可恢复 / Added chunked resumable upload for large files (≥5MB, 5MB/chunk), supports pause/resume/cancel with network interruption recovery
- 新增 5 个分片上传 API: `/api/upload-init`、`/api/upload-chunk`、`/api/upload-complete`、`/api/upload-cancel`、`/api/upload-status` / Added 5 chunked upload API endpoints
- 新增 `pyproject.toml` 配置 pytest 和 coverage 工具 / Added `pyproject.toml` for pytest and coverage configuration
- 新增前端模板渲染测试 `test_frontend.py`（HTML 结构、工具栏、依赖库加载、安全函数、I18N 完整性、主题、核心函数） / Added frontend template tests `test_frontend.py` (HTML structure, toolbar, vendor loading, security functions, I18N completeness, theme, core functions)
- 新增访问日志系统测试 `test_logging.py`（日志配置、写入、fallback 机制、API 日志集成） / Added access log system tests `test_logging.py` (log setup, writing, fallback, API log integration)
- CI 测试步骤新增 pytest-cov 覆盖率报告（term-missing + HTML），Python 3.12 上传覆盖率报告为 artifact / CI test step now generates pytest-cov coverage reports (term-missing + HTML), uploads as artifact on Python 3.12
- 开发依赖新增 `pytest-cov>=4.0.0` / Added `pytest-cov>=4.0.0` to dev dependencies
- 新增目录上传功能：上传对话框新增"选择文件夹"按钮，拖拽上传支持拖入文件夹，自动保留完整目录结构 / Added folder upload: "Select Folder" button in upload dialog, drag-and-drop supports dropping folders, preserves full directory structure
- 后端 `api_upload` 新增可选 `relativePaths` 参数支持目录结构上传（含双重路径遍历安全校验） / Backend `api_upload` adds optional `relativePaths` parameter for directory structure upload (with double path-traversal security checks)
- 文件操作同名冲突对话框：复制/移动/解压操作遇到同名文件时弹出选项（覆盖 / 重命名保留两者 / 跳过），行为与操作系统一致 / File conflict dialog: copy/move/extract operations now prompt with options (Overwrite / Rename Keep Both / Skip) when a same-name file exists, matching OS behavior
- 批量复制/移动支持"应用到后续所有冲突"复选框，避免逐个确认 / Batch copy/move supports "Apply to all conflicts" checkbox to avoid per-file confirmation
- 上传对话框新增"文件已存在时"选项（重命名/覆盖/跳过） / Upload dialog adds "If file exists" option (Rename / Overwrite / Skip)
- ZIP 解压冲突检测：解压前检测目标目录是否有同名文件，有则弹窗让用户选择处理方式 / ZIP extract conflict detection: checks for existing files before extraction, prompts user to choose resolution
- CI 测试 Job 新增 Windows 和 macOS 平台矩阵，测试组合从 3 个增加到 5 个（ubuntu×3 + windows×1 + macOS×1） / CI test job now includes Windows and macOS platform matrix, test combinations increased from 3 to 5
- 测试用例总数从 237 增加到 431（含参数化展开） / Total test cases increased from 237 to 431 (including parameterized expansion)

### Changed / 变更
- 拖拽上传和按钮上传均升级为逐文件顺序上传，单个文件失败不影响其余文件 / Upgraded drag-and-drop and button upload to per-file sequential mode, single file failure won't affect others
- `/api/copy` 同名冲突从静默自动重命名改为默认返回 `409` + `conflict` 信息，新增 `conflict` 参数 / `/api/copy` conflict handling changed from silent auto-rename to returning `409` with conflict info, added `conflict` parameter (overwrite/rename/skip)
- `/api/move` 同名冲突从直接报错改为返回 `conflict` 详情信息，新增 `conflict` 参数 / `/api/move` conflict handling now returns conflict details, added `conflict` parameter
- `/api/upload` 新增 `conflict` 表单字段，默认 `rename`（向后兼容） / `/api/upload` added `conflict` form field, default: `rename` (backward compatible)
- `/api/extract` 新增 `conflict` 参数，默认检测冲突返回 `409` / `/api/extract` added `conflict` parameter, default: detect conflicts and return `409`
- 全选/反选功能现在同时选中文件和文件夹（之前仅选中文件），多选模式下点击文件夹切换选中状态而非进入目录 / Select All/Deselect All now includes both files and folders (previously files only); clicking a folder in multi-select mode toggles selection instead of navigating
- 批量下载和文件夹下载新增实时下载进度弹框（显示已下载/总大小），替代之前一闪而过的 toast 提示 / Batch download and folder download now show a real-time progress dialog (downloaded/total bytes) instead of a brief toast notification

### Fixed / 修复
- 修复复制/移动文件到自身所在目录时，选择"覆盖"会导致源文件被删除的致命 bug（`src == dest` 时覆盖降级为跳过） / Fixed critical bug where overwriting a file/folder copied/moved to its own directory would delete the source (`src == dest` overwrite now gracefully skips)
- 修复批量复制/移动中为每个文件选择不同冲突策略时计数不准和文件丢失的问题（重写为线性两阶段流程） / Fixed batch copy/move showing incorrect counts and losing files when choosing different conflict resolutions per file (rewritten to linear two-phase flow)
- 修复上传文件夹时以 `~$` 开头的 Office 临时文件（如 `~$report.docx`）被路径安全检查误拦截的问题 / Fixed folder upload incorrectly rejecting Office temp files starting with `~$` (e.g. `~$report.docx`) due to overly broad path traversal check
- 修复流式进度模式下复制/移动/删除/解压选择"重命名保留两者"等操作失败的 bug（`log_access` 在生成器中访问已关闭的 request 上下文），使用 `stream_with_context` 保持请求上下文 / Fixed streaming progress mode failing for copy/move/delete/extract operations (e.g. rename-keep-both) due to `log_access` accessing closed request context in generator; applied `stream_with_context` to preserve request context
- 修复上传过程中直接点击"取消"按钮无响应、弹框无法关闭的 bug（`XHR.abort()` 未触发 `onabort` 导致 Promise 永不 resolve） / Fixed upload cancel button not responding and dialog not closing when clicked directly (XHR abort event was not handled, causing Promise to never resolve)

---

## [v2.2.0] - 2026-03-30

### Added / 新增
- Markdown 预览新增返回导航功能：点击文档内链接跳转后，可通过返回按钮逐级回退（支持多级历史栈） / Added back navigation for Markdown preview: clicking linked documents shows a back button with multi-level history stack

### Fixed / 修复
- 修复 Markdown 预览中内嵌链接包含中文（或其他非 ASCII 字符）路径时提示"文件不存在"的 bug（添加 `decodeURIComponent` 解码） / Fixed Markdown preview inline links with Chinese/non-ASCII paths returning "file not found" (added `decodeURIComponent` decoding)
- 修复 Mermaid 图表在 macOS（Safari）上不显示文字的 bug（DOMPurify 误删 `<foreignObject>` 标签，改为信任 Mermaid strict 模式的安全输出） / Fixed Mermaid diagrams showing no text on macOS/Safari (DOMPurify stripped `<foreignObject>` tags; now trusts Mermaid's strict-mode safe output)
- 修复登录后不显示登出按钮的 bug（`doLogin` 成功后遗漏了显示逻辑，需刷新页面才能看到） / Fixed logout button not showing after login (`doLogin` success path missed showing the button; required page refresh to appear)

---

## [v2.1.2] - 2026-03-30

### Added / 新增
- 登出功能：后端 `/api/logout` 接口 + 前端登出按钮（需认证时自动显示） / Logout feature: `/api/logout` endpoint + frontend logout button (auto-shown when auth is required)
- CSRF 保护：所有 POST 请求通过 `X-Requested-With` 自定义 Header 校验，防御跨站请求伪造（`/api/login` 豁免） / CSRF protection via `X-Requested-With` custom header validation for all POST requests (login exempt)
- 分享链接支持自定义过期时间：前端新增 6 档选择（5 分钟 / 30 分钟 / 1 小时 / 6 小时 / 12 小时 / 24 小时） / Share link custom expiration: 6 options (5m / 30m / 1h / 6h / 12h / 24h)
- 上传进度条：弹窗上传和拖拽上传均显示实时进度（百分比 + 已上传/总大小） / Upload progress bar for both dialog and drag-and-drop uploads (percentage + bytes transferred)
- Flask `SECRET_KEY` 显式设置为 `secrets.token_hex(32)` / Explicitly set Flask `SECRET_KEY` via `secrets.token_hex(32)`
- 新增登出、CSRF 保护、分享链接过期时间的单元测试（11 个新测试用例，总计 212 个） / Added unit tests for logout, CSRF protection, and share link expiration (11 new test cases, 212 total)
- 支持通过 `config.json` 配置文件设置参数（优先级低于命令行参数） / Support `config.json` configuration file (lower priority than CLI arguments)
- 可选 HTTPS 支持（`--ssl-cert` / `--ssl-key` 参数） / Optional HTTPS support via `--ssl-cert` / `--ssl-key` flags
- 多用户模式下剪贴板和书签按用户隔离 / Clipboard and bookmarks isolated per user in multi-user mode
- Content-Security-Policy (CSP) 安全响应头 / Content-Security-Policy (CSP) security headers
- 文件列表自动过滤系统隐藏文件（`.DS_Store`、`Thumbs.db`、`desktop.ini` 等） / Auto-filter system hidden files from directory listings
- 新增 80+ 种文本文件扩展名支持 / Added 80+ text file extension types (CoffeeScript, Fortran, Pascal, COBOL, Ada, Solidity, GLSL/HLSL/WGSL, Elm, PureScript, etc.)
- 新增 40+ 种无扩展名文件名识别 / Added 40+ extensionless filename recognition (Jenkinsfile, Containerfile, go.mod, Pipfile, etc.)
- 前端依赖库全部内置到 `static/vendor/`，**离线无网络环境也可正常使用所有功能** / All frontend vendor libraries bundled locally — **fully functional offline** (Markdown, code highlighting, Mermaid, Office preview)
- 完整自动化测试套件（212 个测试用例） / Complete automated test suite (212 test cases) covering all API endpoints, utilities, and CLI
- CI 添加多 Python 版本矩阵测试（3.8 / 3.11 / 3.12） / CI multi-Python version matrix testing (3.8 / 3.11 / 3.12)
- 访问日志自动轮转（单文件最大 10MB，保留 5 份备份） / Access log auto-rotation (10MB per file, 5 backups)
- 版本号集中管理（`__version__` 变量） / Centralized version management via `__version__` variable
- 明确取消上传文件大小限制 / Explicitly removed upload file size limit (`MAX_CONTENT_LENGTH = None`)
- 新增线程安全锁保护共享状态 / Thread-safe locks for shared state (`user_sessions`, `login_attempts`, `share_tokens`)
- 新增 `THIRD_PARTY_LICENSES` 文件 / Added `THIRD_PARTY_LICENSES` for all vendor library licenses
- 新增 `static/vendor/VERSIONS.txt` 追踪前端依赖版本号 / Added `static/vendor/VERSIONS.txt` tracking frontend dependency versions
- 新增 CLI 参数测试 / Added CLI argument tests (`tests/test_cli.py`)
- 新增 DOMPurify 3.2.4 XSS 净化库 / Added DOMPurify 3.2.4 for XSS sanitization of Markdown/DOCX/XLSX/Mermaid previews
- Mermaid 安全级别从 `loose` 改为 `strict` / Mermaid security level changed from `loose` to `strict`
- 新增 `_is_dangerous_regex()` ReDoS 防护 / Added `_is_dangerous_regex()` for enhanced ReDoS protection
- 新增安全响应头（`X-Content-Type-Options`、`X-Frame-Options`、`Referrer-Policy`） / Added security headers via `@app.after_request`
- 扩展系统目录保护列表 / Extended protected system directory list (all Windows drive letters, Linux `/boot`, `/home`, `/opt`, etc.)
- `stop_server.bat/.sh` 已加入打包配置 / Stop scripts bundled in PyInstaller spec
- 新增 `detect_encoding()` 编码检测函数，编辑保存文件时自动保留原始编码（不再强制转为 UTF-8） / Added `detect_encoding()` function — file saves now preserve original encoding instead of forcing UTF-8
- 新增中文编码与中文文件名测试（21 个用例：编码检测、编码保留、中文文件名 CRUD、中文内容搜索） / Added Chinese encoding and filename tests (21 cases: encoding detection, encoding preservation, Chinese filename CRUD, Chinese content search)
- 新增降序排列文件夹在前的回归测试 / Added regression tests for folders-always-first in descending sort order
- API 文档补充搜索、预览下载、文件管理、分享、其他 5 个板块的响应示例（中英双语同步） / Added response examples for Search, Preview & Download, File Management, Sharing, and Other sections in API docs (both CN and EN)
- 测试用例总数从 212 增加到 237 / Total test cases increased from 212 to 237

### Fixed / 修复
- 修复 `sanitizeHTML` 在 DOMPurify 不可用时直接返回原始 HTML 的 XSS 风险（改为 `eh()` 转义） / Fixed XSS risk in `sanitizeHTML` fallback when DOMPurify unavailable (now uses `eh()` escaping)
- 修复前端文件详情中 `info.size`/`info.ext`/`info.type`/`info.modified` 未经 HTML 转义直接插入 `innerHTML` 的问题 / Fixed file detail info fields not HTML-escaped before innerHTML insertion
- 修复 `esc()` 函数未转义反引号的问题（防止模板字符串注入） / Fixed `esc()` function not escaping backticks (prevents template literal injection)
- 修复 `api_batch_download` 函数中 `try/with` 块缩进不一致（2 空格 → 4 空格） / Fixed inconsistent indentation in `api_batch_download` (2-space → 4-space)
- 整理分散在文件中间的 `import hashlib` 和 `import random` 到文件顶部 / Moved scattered `import hashlib` and `import random` to file top
- 修复前端 `innerHTML` 中 `data.error` 未转义的 XSS 漏洞 / Fixed XSS vulnerability in frontend error message rendering (added `eh()` escaping)
- 修复 `/api/raw` 路由中路径前缀检查可被绕过的问题 / Fixed path prefix bypass in `/api/raw` route
- 统一 ReDoS 检测为调用 `_is_dangerous_regex()` / Unified ReDoS detection via `_is_dangerous_regex()`
- 修复 API 文档与实际代码不一致的问题 / Fixed API documentation inconsistencies
- 修复 GUIDE 文档中文件类型列表不完整的问题 / Fixed incomplete file type list in GUIDE docs
- 修复 `stop_server.bat` 端口匹配不精确可能误杀其他进程的问题 / Fixed imprecise port matching in `stop_server.bat`
- 修复大文件打包下载内存溢出风险（改用 SpooledTemporaryFile） / Fixed memory overflow risk for large batch downloads (now uses SpooledTemporaryFile)
- 修复 `scripts/build-release.sh` 中变量定义前引用的 bug / Fixed variable-before-definition bug in `scripts/build-release.sh`
- 修复 `file_browser.spec` 去重逻辑失效 / Fixed dedup logic failure in `file_browser.spec`
- 修复主函数中缩进不一致 / Fixed indentation inconsistency in main function
- 修复 `api_info` 异常时泄露系统路径 / Fixed system path leakage in `api_info` error responses
- 修复 `stop_server.sh` 在 macOS 上 `grep -P` 不可用 / Fixed `grep -P` unavailability on macOS in `stop_server.sh`
- 修复 `.spec` 在 Windows 上路径去重失效 / Fixed path dedup failure on Windows in `.spec` files
- 修复 `.gitignore` 规则与跟踪文件冲突 / Fixed `.gitignore` rules conflicting with tracked files
- 修复降序排列时文件夹未始终排在文件前面的 bug / Fixed folders not always appearing before files in descending sort order
- 修复 `stop_server.sh` 无条件输出"停止成功"（现在先验证进程是否真正终止） / Fixed `stop_server.sh` unconditionally reporting success (now verifies process termination)
- 修复 `GUIDE_EN.md` 末尾 API 链接文本与目标不一致 / Fixed inconsistent API link text in `GUIDE_EN.md`

### Changed / 变更
- `_FILE_TYPE_MAP` 和 `_TEXT_FILENAMES` 提升为模块级常量 / Promoted `_FILE_TYPE_MAP` and `_TEXT_FILENAMES` to module-level constants (performance)
- 受保护目录黑名单扩展覆盖更多系统目录 / Extended protected directory blacklist across all platforms
- `clipboard_data` 增加线程安全保护 / Added thread-safe locking to `clipboard_data`
- `save_bookmarks()` 增加异常处理 / Added try/except to `save_bookmarks()` to prevent service disruption
- 移除 Office 预览的 100MB 大小限制 / Removed 100MB size limit for Office file previews
- API 异常不再返回内部错误详情（安全增强） / API errors no longer expose internal details (security hardening)
- 编码检测链去除冗余的 `gb2312`（已被 `gb18030` 超集覆盖） / Removed redundant `gb2312` from encoding detection chain (`gb18030` is a superset)
- `GIT_COMMIT.md` 加入 `.gitignore`（作者私用文件不再提交） / Added `GIT_COMMIT.md` to `.gitignore` (author-only file)
- `requirements-dev.txt` 中 `pyinstaller` 添加版本上限 `<7.0.0` / Added version ceiling `<7.0.0` for `pyinstaller` in `requirements-dev.txt`
- `stop_server.bat` 改为先优雅终止后强制终止 / `stop_server.bat` now attempts graceful shutdown before force kill
- `seal.py` 改为原子写入 / `seal.py` now uses atomic file writes
- Flask 版本约束改为 `>=2.0.0,<4.0.0` / Flask version constraint changed to `>=2.0.0,<4.0.0`
- `SECURITY.md` 版本号改为动态描述 / `SECURITY.md` version info made dynamic
- `.gitignore` 新增 `.env` 忽略规则 / Added `.env` / `.env.*` to `.gitignore`
- CHANGELOG.md 全部版本条目改为中英双语格式 / CHANGELOG.md entries converted to bilingual (Chinese / English) format
- 更新 API 文档：新增 `/api/logout` 端点和 CSRF Header 要求说明 / Updated API docs: added `/api/logout` endpoint and CSRF header requirement
- 更新 SECURITY.md / README / GUIDE / CONTRIBUTING 文档同步新功能说明 / Updated SECURITY.md / README / GUIDE / CONTRIBUTING docs to reflect new features
- 测试框架新增 `CSRFClient` 测试客户端，自动为 POST 请求附加 CSRF Header / Test framework: added `CSRFClient` that auto-attaches CSRF header to POST requests

---

## [v2.1.1] - 2026-03-26

### Added / 新增
- GitHub Actions CI: auto-build executables for Windows/macOS(Intel+Apple Silicon)/Linux / 自动构建四平台可执行文件
- CI attribution integrity check / CI 打赏文件完整性校验
- Tag-triggered auto-release to GitHub Releases / Tag 触发自动发布到 Releases 页面
- Linux x86_64 executable build support / 新增 Linux x86_64 可执行文件构建

---

## [v2.1] - 2026-03-11

### Added / 新增
- 多用户多密码模式（管理员 + 只读用户） / Multi-user multi-password mode (admin + read-only roles)
- 文件/文件夹复制与移动功能，可视化目录选择器 / File/folder copy & move with visual directory picker
- 批量操作（批量删除、批量移动、批量复制） / Batch operations (batch delete, move, copy)
- 文件夹整体打包下载 / Folder download as ZIP
- ZIP 文件在线预览与解压 / ZIP file preview and online extraction
- 临时分享链接（1 小时有效，无需登录） / Temporary share links (1-hour expiry, no login required)
- 视频字幕自动加载（.vtt/.srt/.ass） / Auto-load video subtitles (.vtt/.srt/.ass)
- Office 文件预览（docx/xlsx） / Office file preview (docx rendered as HTML, xlsx as table)
- 正则表达式搜索模式 / Regex search mode
- 多选模式一键全选/取消全选 / Multi-select with select all/deselect all
- 网格/列表视图切换 / Grid/list view toggle
- 亮色/暗色主题切换 / Light/dark theme toggle
- 中/英语言切换 / Chinese/English language switch
- 阻止系统睡眠功能（跨平台） / Prevent system sleep (cross-platform)
- 共享剪贴板（手机-电脑文本互传） / Shared clipboard (phone-PC text sharing)
- 目录收藏/书签功能 / Directory bookmark/favorites
- 只读模式（`--read-only`） / Read-only mode (`--read-only`)
- `--allow-sleep` 命令行参数 / `--allow-sleep` CLI argument
- 作者署名与资源完整性保护 / Author attribution and resource integrity protection

### Improved / 改进
- 登录速率限制加强安全性 / Enhanced security with login rate limiting
- 系统关键目录保护（防止误删） / System directory protection (prevent accidental deletion)
- 文件名搜索支持不区分大小写 / Case-insensitive filename search
- 移动端触屏交互优化 / Mobile touch interaction improvements

### Fixed / 修复
- Windows 控制台 UTF-8 编码问题 / Windows console UTF-8 encoding issue
- ZIP 归档路径在 Windows 上的反斜杠问题 / ZIP archive backslash path issue on Windows
- JS 转义函数对换行符的处理 / JS escape function newline handling

---

## [v2.0] - 2026-02-01

### Added / 新增
- 密码保护（启动时自动生成 32 位随机密码） / Password protection (auto-generated 32-char random password)
- 访问日志记录 / Access logging
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

---

## [v1.0] - 2026-01-01

### Added / 新增
- 初始版本 / Initial release
- 基本文件浏览功能 / Basic file browsing
- 文件下载 / File download

[v2.6.0]: https://github.com/bbyybb/lan-file-browser/compare/v2.2.0...v2.6.0
[v2.2.0]: https://github.com/bbyybb/lan-file-browser/compare/v2.1.2...v2.2.0
[v2.1.2]: https://github.com/bbyybb/lan-file-browser/compare/v2.1.1...v2.1.2
[v2.1.1]: https://github.com/bbyybb/lan-file-browser/compare/v2.1...v2.1.1
[v2.1]: https://github.com/bbyybb/lan-file-browser/compare/v2.0...v2.1
[v2.0]: https://github.com/bbyybb/lan-file-browser/compare/v1.0...v2.0
[v1.0]: https://github.com/bbyybb/lan-file-browser/releases/tag/v1.0

# Changelog / 更新日志

All notable changes to this project will be documented in this file.

本文件记录项目的所有重要变更。

The format is based on [Keep a Changelog](https://keepachangelog.com/).

---

## [v2.1.1] - 2026-03-26

### Added / 新增
- GitHub Actions CI: auto-build executables for Windows/macOS(Intel+ARM)/Linux / 自动构建四平台可执行文件
- CI attribution integrity check / CI 打赏文件完整性校验
- Tag-triggered auto-release to GitHub Releases / Tag 触发自动发布到 Releases 页面
- Linux x86_64 executable build support / 新增 Linux x86_64 可执行文件构建

---

## [v2.1] - 2026-03-11

### Added / 新增
- 多用户多密码模式（管理员 + 只读用户）
- 文件/文件夹复制与移动功能，可视化目录选择器
- 批量操作（批量删除、批量移动、批量复制）
- 文件夹整体打包下载
- ZIP 文件在线预览与解压
- 临时分享链接（1 小时有效，无需登录）
- 视频字幕自动加载（.vtt/.srt/.ass）
- Office 文件预览（docx 渲染为 HTML，xlsx 渲染为表格）
- 正则表达式搜索模式
- 多选模式一键全选/取消全选
- 网格/列表视图切换
- 亮色/暗色主题切换
- 中/英语言切换
- 阻止系统睡眠功能（跨平台）
- 共享剪贴板（手机-电脑文本互传）
- 目录收藏/书签功能
- 只读模式（`--read-only`）
- `--allow-sleep` 命令行参数
- 作者署名与资源完整性保护

### Improved / 改进
- 登录速率限制加强安全性
- 系统关键目录保护（防止误删）
- 文件名搜索支持不区分大小写
- 移动端触屏交互优化

### Fixed / 修复
- Windows 控制台 UTF-8 编码问题
- ZIP 归档路径在 Windows 上的反斜杠问题
- JS 转义函数对换行符的处理

---

## [v2.0] - 2026-02-01

### Added / 新增
- 密码保护（启动时自动生成 32 位随机密码）
- 访问日志记录
- 文件上传功能
- 批量文件打包下载
- 文件内容搜索
- 在线文本编辑器
- Markdown 渲染（GFM + Mermaid 图表）
- 代码语法高亮（40+ 语言）
- 图片/视频/音频/PDF 在线预览
- 面包屑导航
- 目录白名单安全限制
- 二维码快速扫码访问
- 交互式启动引导
- 跨平台支持（Windows/macOS/Linux）
- 中英双语界面

---

## [v1.0] - 2026-01-01

### Added / 新增
- 初始版本
- 基本文件浏览功能
- 文件下载

[v2.1.1]: https://github.com/bbyybb/lan-file-browser/compare/v2.1...v2.1.1
[v2.1]: https://github.com/bbyybb/lan-file-browser/compare/v2.0...v2.1
[v2.0]: https://github.com/bbyybb/lan-file-browser/compare/v1.0...v2.0
[v1.0]: https://github.com/bbyybb/lan-file-browser/releases/tag/v1.0

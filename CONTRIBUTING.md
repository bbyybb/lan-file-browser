**中文** | [English](#contributing-english)

# 贡献指南

感谢你对 LAN File Browser 的关注！欢迎提交 Issue 和 Pull Request。

## 如何贡献

### 报告 Bug

1. 先搜索 [已有 Issue](https://github.com/bbyybb/lan-file-browser/issues) 确认是否已被报告
2. 使用 [Bug 报告模板](https://github.com/bbyybb/lan-file-browser/issues/new?template=bug_report.md) 提交
3. 尽量提供完整的环境信息和复现步骤

### 提出功能建议

1. 先搜索已有 Issue 确认是否已被建议
2. 使用 [功能建议模板](https://github.com/bbyybb/lan-file-browser/issues/new?template=feature_request.md) 提交
3. 描述清楚使用场景和期望行为

### 提交代码

1. Fork 本仓库
2. 创建特性分支：`git checkout -b feature/your-feature`
3. 提交改动：`git commit -m "Add: your feature description"`
4. 推送分支：`git push origin feature/your-feature`
5. 创建 Pull Request

### 代码规范

- **单文件架构**：所有后端 + 前端代码在 `file_browser.py` 中，请勿拆分
- **编码**：所有文件使用 UTF-8 编码
- **兼容性**：确保代码在 Python 3.8+ 和 Windows/macOS/Linux 上都能运行
- **依赖**：尽量不引入新的第三方依赖（当前仅依赖 Flask）
- **双语**：如果修改了用户可见的文本，请同时更新中文和英文

### 文档贡献

文档同样重要！如果你发现文档有错误或可以改进，欢迎提交 PR：

- `README.md` / `README_EN.md` — 项目说明
- `docs/GUIDE.md` / `docs/GUIDE_EN.md` — 使用指南
- `docs/API.md` / `docs/API_EN.md` — API 文档
- `docs/BEGINNER.md` / `docs/BEGINNER_EN.md` — 入门教程

## 开发环境

```bash
# 克隆仓库
git clone https://github.com/bbyybb/lan-file-browser.git
cd lan-file-browser

# 安装依赖
pip install flask

# 启动开发
python file_browser.py
```

## 许可证

提交贡献即表示你同意你的代码以 [MIT 许可证](LICENSE) 发布。

---

<a id="contributing-english"></a>

# Contributing (English)

Thank you for your interest in LAN File Browser! Issues and Pull Requests are welcome.

## How to Contribute

### Report Bugs

1. Search [existing Issues](https://github.com/bbyybb/lan-file-browser/issues) first to check if it's already reported
2. Use the [Bug Report template](https://github.com/bbyybb/lan-file-browser/issues/new?template=bug_report.md)
3. Provide complete environment information and reproduction steps

### Suggest Features

1. Search existing Issues first to check if it's already suggested
2. Use the [Feature Request template](https://github.com/bbyybb/lan-file-browser/issues/new?template=feature_request.md)
3. Clearly describe the use case and expected behavior

### Submit Code

1. Fork this repository
2. Create a feature branch: `git checkout -b feature/your-feature`
3. Commit changes: `git commit -m "Add: your feature description"`
4. Push the branch: `git push origin feature/your-feature`
5. Create a Pull Request

### Code Guidelines

- **Single-file architecture**: All backend + frontend code lives in `file_browser.py` — do not split it
- **Encoding**: All files use UTF-8 encoding
- **Compatibility**: Ensure code works on Python 3.8+ and Windows/macOS/Linux
- **Dependencies**: Avoid introducing new third-party dependencies (currently only Flask)
- **Bilingual**: If modifying user-visible text, update both Chinese and English

### Documentation

Documentation contributions are equally valued! If you find errors or room for improvement:

- `README.md` / `README_EN.md` — Project description
- `docs/GUIDE.md` / `docs/GUIDE_EN.md` — Usage guide
- `docs/API.md` / `docs/API_EN.md` — API documentation
- `docs/BEGINNER.md` / `docs/BEGINNER_EN.md` — Beginner tutorial

## Development Setup

```bash
# Clone the repository
git clone https://github.com/bbyybb/lan-file-browser.git
cd lan-file-browser

# Install dependencies
pip install flask

# Start development
python file_browser.py
```

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).

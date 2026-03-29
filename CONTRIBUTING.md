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

## 分支策略与合并流程

### 分支保护

`main` 分支受保护，**不允许**直接 push：

- 所有改动必须通过 Pull Request (PR) 合并
- PR 需要通过 CI 检查（构建 + 打赏文件完整性校验）
- 禁止强制推送（force push）和删除 `main` 分支

> 外部贡献者 clone 或 fork 后**无法直接 push** 到本仓库，必须提 PR 由维护者审核。

### 合并流程

**外部贡献者：**

```bash
# 1. Fork 仓库（GitHub 页面点击 Fork）

# 2. 克隆你的 fork
git clone https://github.com/你的用户名/lan-file-browser.git
cd lan-file-browser

# 3. 创建特性分支
git checkout -b feature/your-feature

# 4. 开发、测试
python file_browser.py -y   # 确认功能正常

# 5. 提交并推送到你的 fork
git add -A
git commit -m "Add: your feature description"
git push origin feature/your-feature

# 6. 到 GitHub 页面创建 Pull Request（从你的分支 → 本仓库 main）

# 7. 等待 CI 通过 + 维护者审核 → 合并
```

**维护者（项目作者）：**

```bash
# 日常开发也走分支，不直接改 main
git checkout -b fix/some-bug
# ...开发...
git push origin fix/some-bug
# 在 GitHub 创建 PR → CI 通过后合并

# 发布版本时
git checkout main
git pull origin main
git tag v2.x.x
git push origin v2.x.x    # 触发 CI 自动构建和发布
```

### PR 合并方式

推荐使用 **Squash and merge**（将多个 commit 压缩为一个），保持 `main` 分支历史清晰。

## 开发环境

```bash
# 克隆仓库
git clone https://github.com/bbyybb/lan-file-browser.git
cd lan-file-browser

# 安装依赖（含测试工具和 PyInstaller 构建工具）
pip install -r requirements-dev.txt

# 启动开发
python file_browser.py

# 运行自动化测试（提交前请确保全部通过）
pytest tests/ -v
```

> 开发依赖包含：Flask（运行时）、pytest（测试）、PyInstaller（构建可执行文件）。
> 测试文件按功能模块组织在 `tests/` 目录下，命名规范为 `test_*.py`。
> **注意**：项目启用了 CSRF 保护，所有 POST 请求须携带 `X-Requested-With: XMLHttpRequest` 请求头。测试中已通过 `conftest.py` 中的 `CSRFClient` 自动处理。手动测试 API 时请确保附带此请求头。

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

## Branch Strategy & Merge Workflow

### Branch Protection

The `main` branch is protected — **direct pushes are not allowed**:

- All changes must be merged via Pull Request (PR)
- PRs must pass CI checks (build + attribution integrity check)
- Force push and deletion of `main` branch are prohibited

> External contributors **cannot push directly** to this repository after cloning or forking. PRs must be submitted and reviewed by maintainers.

### Merge Workflow

**External contributors:**

```bash
# 1. Fork the repository (click Fork on GitHub)

# 2. Clone your fork
git clone https://github.com/YOUR_USERNAME/lan-file-browser.git
cd lan-file-browser

# 3. Create a feature branch
git checkout -b feature/your-feature

# 4. Develop and test
python file_browser.py -y   # verify it works

# 5. Commit and push to your fork
git add -A
git commit -m "Add: your feature description"
git push origin feature/your-feature

# 6. Create a Pull Request on GitHub (your branch → this repo's main)

# 7. Wait for CI to pass + maintainer review → merge
```

**Maintainers (project author):**

```bash
# Use branches for daily development, never commit directly to main
git checkout -b fix/some-bug
# ...develop...
git push origin fix/some-bug
# Create PR on GitHub → merge after CI passes

# Release workflow
git checkout main
git pull origin main
git tag v2.x.x
git push origin v2.x.x    # triggers CI auto-build and release
```

### PR Merge Strategy

**Squash and merge** is recommended — squashes multiple commits into one to keep `main` branch history clean.

## Development Setup

```bash
# Clone the repository
git clone https://github.com/bbyybb/lan-file-browser.git
cd lan-file-browser

# Install dependencies (including test tools and PyInstaller build tool)
pip install -r requirements-dev.txt

# Start development
python file_browser.py

# Run automated tests (please ensure all pass before submitting)
pytest tests/ -v
```

> Dev dependencies include: Flask (runtime), pytest (testing), PyInstaller (building executables).
> Test files are organized by feature module in the `tests/` directory, following the `test_*.py` naming convention.
> **Note**: The project has CSRF protection enabled. All POST requests must include the `X-Requested-With: XMLHttpRequest` header. Tests handle this automatically via `CSRFClient` in `conftest.py`. When manually testing APIs, make sure to include this header.

## License

By contributing, you agree that your contributions will be licensed under the [MIT License](LICENSE).

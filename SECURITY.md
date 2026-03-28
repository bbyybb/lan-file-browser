**中文** | [English](#security-policy-english)

# 安全策略

## 支持的版本

| 版本 | 支持状态 |
|------|---------|
| v2.1.1 (最新) | ✅ 支持 |
| < v2.1.1 | ❌ 不再支持 |

建议始终使用 [最新版本](https://github.com/bbyybb/lan-file-browser/releases/latest)。

## 报告安全漏洞

如果你发现了安全漏洞，**请不要**通过公开的 Issue 提交。

请通过以下方式私密报告：

1. **GitHub 私密漏洞报告**（推荐）：前往 [Security Advisories](https://github.com/bbyybb/lan-file-browser/security/advisories/new) 提交
2. **邮件**：在 GitHub 个人资料页找到联系方式

请在报告中包含：
- 漏洞的详细描述
- 复现步骤
- 潜在影响
- 如果有的话，建议的修复方案

我会在收到报告后尽快回复并处理。

## 安全设计说明

本项目是一个**局域网文件浏览工具**，设计用于可信网络环境。请注意：

- 使用 HTTP 明文传输，**不适合**暴露到公网
- 密码通过 HTTP 明文传输，仅作为局域网内的基本访问控制
- 详细的安全机制和最佳实践请参见 [README 安全说明](README.md#安全说明)

---

<a id="security-policy-english"></a>

# Security Policy (English)

## Supported Versions

| Version | Status |
|---------|--------|
| v2.1.1 (latest) | ✅ Supported |
| < v2.1.1 | ❌ No longer supported |

Always use the [latest version](https://github.com/bbyybb/lan-file-browser/releases/latest).

## Reporting a Vulnerability

If you discover a security vulnerability, **please do not** report it via public Issues.

Please report privately through:

1. **GitHub Private Vulnerability Reporting** (recommended): Go to [Security Advisories](https://github.com/bbyybb/lan-file-browser/security/advisories/new)
2. **Email**: Find contact information on the GitHub profile page

Please include in your report:
- Detailed description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix, if any

I will respond and address the report as soon as possible.

## Security Design Notes

This project is a **LAN file browsing tool** designed for trusted network environments. Please note:

- Uses HTTP plaintext transmission, **not suitable** for public internet exposure
- Passwords are transmitted in plaintext over HTTP, serving only as basic access control within LAN
- For detailed security mechanisms and best practices, see [README Security Section](README_EN.md#security)

**中文** | [English](#security-policy-english)

# 安全策略

## 支持的版本

| 版本 | 支持状态 |
|------|---------|
| 最新版本 | ✅ 支持 |
| 旧版本 | ❌ 不再支持 |

安全修复仅应用于最新版本。建议始终使用 [最新版本](https://github.com/bbyybb/lan-file-browser/releases/latest)。

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

- 默认使用 HTTP 明文传输，**不适合**暴露到公网；支持可选 HTTPS（通过 `--ssl-cert` / `--ssl-key` 参数启用）
- 密码通过 HTTP 明文传输（除非启用 HTTPS），仅作为局域网内的基本访问控制
- 前端预览内容经过 DOMPurify XSS 净化，Mermaid 使用 strict 安全级别；错误消息通过 `eh()` 函数进行 HTML 转义防止 XSS
- 所有响应包含安全头（`Content-Security-Policy`、`X-Content-Type-Options`、`X-Frame-Options`、`Referrer-Policy`）
- 正则搜索具有 ReDoS 危险模式检测
- POST 请求通过 `X-Requested-With` 自定义请求头校验防御 CSRF 攻击（登录接口豁免）
- 详细的安全机制和最佳实践请参见 [README 安全说明](README.md#安全说明)

---

<a id="security-policy-english"></a>

# Security Policy (English)

## Supported Versions

| Version | Status |
|---------|--------|
| Latest | ✅ Supported |
| Older versions | ❌ No longer supported |

Security fixes are only applied to the latest version. Always use the [latest version](https://github.com/bbyybb/lan-file-browser/releases/latest).

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

- Uses HTTP plaintext transmission by default, **not suitable** for public internet exposure; optional HTTPS supported (via `--ssl-cert` / `--ssl-key` flags)
- Passwords are transmitted in plaintext over HTTP (unless HTTPS is enabled), serving only as basic access control within LAN
- Frontend preview content is sanitized with DOMPurify; Mermaid uses strict security level; error messages are HTML-escaped via `eh()` function to prevent XSS
- All responses include security headers (`Content-Security-Policy`, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`)
- Regex search includes ReDoS dangerous pattern detection
- POST requests are protected against CSRF via `X-Requested-With` custom header validation (login endpoint is exempt)
- For detailed security mechanisms and best practices, see [README Security Section](README_EN.md#security)

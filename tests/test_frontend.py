# -*- coding: utf-8 -*-
"""
前端模板渲染与内嵌 JavaScript 测试。

通过 Flask test client 获取 GET / 渲染后的 HTML，验证：
- HTML 核心结构（登录页、主应用、工具栏、预览框等）
- 工具栏按钮完整性
- 前端依赖库加载路径
- 安全相关 JS 函数（eh/esc/sanitizeHTML/CSRF fetch 封装）
- 暗色/亮色主题支持
- I18N 国际化完整性（zh/en 键一致性、data-i18n 引用有效性）
- 模板变量渲染（server_lang）
"""
import os
import re
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import file_browser
from tests.conftest import _patch_app


# ────────────────────────────────────────────────
# Helper：获取渲染后的 HTML 文本
# ────────────────────────────────────────────────
@pytest.fixture
def html(client):
    """获取首页 HTML 文本（UTF-8 解码）。"""
    resp = client.get("/")
    assert resp.status_code == 200
    return resp.data.decode("utf-8")


# ════════════════════════════════════════════════════════════
# HTML 核心结构
# ════════════════════════════════════════════════════════════
class TestHTMLStructure:
    """验证 HTML 页面包含所有关键 DOM 元素。"""

    def test_returns_200_html(self, client):
        """首页返回 200 且 Content-Type 为 text/html。"""
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.content_type

    def test_has_doctype(self, html):
        """HTML 以 DOCTYPE 声明开头。"""
        assert "<!DOCTYPE html>" in html

    def test_has_login_page(self, html):
        """包含登录页容器。"""
        assert 'id="loginPage"' in html

    def test_has_main_app(self, html):
        """包含主应用容器。"""
        assert 'id="mainApp"' in html

    def test_has_toolbar(self, html):
        """包含工具栏。"""
        assert 'id="toolbar"' in html

    def test_has_content_area(self, html):
        """包含文件列表内容区。"""
        assert 'id="content"' in html

    def test_has_preview_modal(self, html):
        """包含预览模态框及其 body。"""
        assert 'id="modal"' in html
        assert 'id="modalBody"' in html

    def test_has_dialog(self, html):
        """包含通用对话框及其 body。"""
        assert 'id="dialog"' in html
        assert 'id="dialogBody"' in html

    def test_has_search_input(self, html):
        """包含搜索输入框。"""
        assert 'id="searchInput"' in html

    def test_has_breadcrumb(self, html):
        """包含面包屑导航。"""
        assert 'id="breadcrumb"' in html

    def test_has_status_bar(self, html):
        """包含状态栏文本。"""
        assert 'id="statusText"' in html

    def test_has_drop_overlay(self, html):
        """包含拖拽上传覆盖层。"""
        assert 'id="dropOverlay"' in html

    def test_has_toast(self, html):
        """包含 toast 提示元素。"""
        assert 'id="toast"' in html or "toast" in html.lower()

    def test_has_login_form_elements(self, html):
        """登录页包含密码输入框和登录按钮。"""
        assert 'id="loginPwd"' in html
        assert "doLogin()" in html

    def test_has_author_footer(self, html):
        """包含作者 footer。"""
        assert 'id="authorFooter"' in html


# ════════════════════════════════════════════════════════════
# 工具栏按钮
# ════════════════════════════════════════════════════════════
class TestToolbarButtons:
    """验证工具栏包含所有功能按钮。"""

    @pytest.mark.parametrize("i18n_key", [
        "upload", "mkdir", "mkfile", "select", "selectAll",
        "batchDl", "batchDel2", "batchMove", "batchCopy",
        "clipboard", "bookmarks",
    ])
    def test_toolbar_i18n_buttons(self, html, i18n_key):
        """工具栏按钮的 data-i18n 属性完整。"""
        assert f'data-i18n="{i18n_key}"' in html

    def test_has_theme_button(self, html):
        """主题切换按钮存在。"""
        assert 'id="themeBtn"' in html

    def test_has_lang_button(self, html):
        """语言切换按钮存在。"""
        assert 'id="langBtn"' in html

    def test_has_grid_view_button(self, html):
        """网格视图切换按钮存在。"""
        assert 'id="gridViewBtn"' in html

    def test_has_logout_button(self, html):
        """登出按钮存在。"""
        assert 'id="logoutBtn"' in html

    def test_has_bookmark_add_button(self, html):
        """收藏当前目录按钮存在。"""
        assert 'id="bmAddBtn"' in html


# ════════════════════════════════════════════════════════════
# 前端依赖库加载路径
# ════════════════════════════════════════════════════════════
class TestVendorDependencies:
    """验证所有前端第三方库的 script/link 标签正确引用。"""

    @pytest.mark.parametrize("lib_file", [
        "marked.min.js",
        "highlight.min.js",
        "mermaid.min.js",
        "qrcode.min.js",
        "purify.min.js",
        "mammoth.browser.min.js",
        "xlsx.full.min.js",
    ])
    def test_vendor_script_tag(self, html, lib_file):
        """JavaScript 依赖库的 script 标签存在。"""
        assert f"/static/vendor/{lib_file}" in html

    def test_highlight_css(self, html):
        """代码高亮 CSS 主题引用存在。"""
        assert "/static/vendor/github-dark.min.css" in html


# ════════════════════════════════════════════════════════════
# 安全相关 JS 函数
# ════════════════════════════════════════════════════════════
class TestSecurityFunctions:
    """验证前端安全函数和 CSRF 保护机制存在。"""

    def test_eh_function(self, html):
        """HTML 实体转义函数 eh() 已定义。"""
        assert "function eh(" in html

    def test_esc_function(self, html):
        """路径转义函数 esc() 已定义。"""
        assert "function esc(" in html

    def test_sanitize_html_function(self, html):
        """HTML 净化函数 sanitizeHTML() 已定义。"""
        assert "function sanitizeHTML(" in html

    def test_dompurify_usage(self, html):
        """sanitizeHTML 使用 DOMPurify.sanitize 进行净化。"""
        assert "DOMPurify.sanitize" in html

    def test_fetch_csrf_wrapper(self, html):
        """全局 fetch 包装器为 POST 请求附加 X-Requested-With 头。"""
        assert "X-Requested-With" in html
        assert "XMLHttpRequest" in html

    def test_xhr_upload_csrf_header(self, html):
        """xhrUpload 函数设置了 CSRF 保护头。"""
        assert "function xhrUpload(" in html or "xhrUpload" in html
        assert 'xhr.setRequestHeader("X-Requested-With"' in html


# ════════════════════════════════════════════════════════════
# 主题支持
# ════════════════════════════════════════════════════════════
class TestThemeSupport:
    """验证暗色/亮色主题切换系统。"""

    def test_dark_theme_css_variables(self, html):
        """暗色主题 CSS 变量定义存在。"""
        assert ":root {" in html or ":root{" in html
        assert "--bg:" in html
        assert "--text:" in html

    def test_light_theme_css_variables(self, html):
        """亮色主题 CSS 变量定义存在。"""
        assert '[data-theme="light"]' in html

    def test_toggle_theme_function(self, html):
        """主题切换函数已定义。"""
        assert "function toggleTheme()" in html

    def test_theme_localstorage(self, html):
        """主题状态持久化到 localStorage。"""
        assert 'localStorage.getItem("fb_theme")' in html
        assert 'localStorage.setItem("fb_theme"' in html


# ════════════════════════════════════════════════════════════
# I18N 国际化
# ════════════════════════════════════════════════════════════

def _extract_i18n_keys(html, lang):
    """从 HTML 中提取指定语言的 I18N 翻译键集合。

    Args:
        html: 渲染后的 HTML 文本
        lang: "zh" 或 "en"

    Returns:
        set: 翻译键集合
    """
    # I18N 对象格式: const I18N={zh:{key1:"val",...},en:{key2:"val",...}};
    # 找到 lang:{...} 的内容块
    pattern = lang + r":\{(.+?)\}(?:\s*\}|\s*,\s*(?:en|zh))"
    match = re.search(pattern, html, re.DOTALL)
    if not match:
        return set()
    block = match.group(1)
    # 提取所有 key:"..." 形式
    # 键名仅出现在块开头或逗号后（可能跨行有空白），由 ASCII 字母/数字/下划线组成
    keys = re.findall(r'(?:^|,)\s*([a-zA-Z_][a-zA-Z0-9_]*):"', block)
    return set(keys)


class TestI18N:
    """验证国际化翻译系统的完整性。"""

    def test_i18n_object_defined(self, html):
        """I18N 对象已定义。"""
        assert "const I18N={" in html or "const I18N =" in html

    def test_apply_lang_function(self, html):
        """applyLang 函数已定义。"""
        assert "function applyLang(" in html

    def test_toggle_lang_function(self, html):
        """toggleLang 函数已定义。"""
        assert "function toggleLang()" in html

    def test_server_lang_variable(self, html):
        """模板变量 _serverLang 已渲染。"""
        assert "const _serverLang=" in html or 'const _serverLang="' in html

    def test_i18n_zh_en_key_parity(self, html):
        """中英文翻译键完全一致（捕获漏翻译）。"""
        zh_keys = _extract_i18n_keys(html, "zh")
        en_keys = _extract_i18n_keys(html, "en")
        assert len(zh_keys) > 50, "zh 翻译键数量过少，可能提取失败"
        assert len(en_keys) > 50, "en 翻译键数量过少，可能提取失败"
        missing_in_en = zh_keys - en_keys
        missing_in_zh = en_keys - zh_keys
        assert not missing_in_en, f"zh 有但 en 缺少的键: {missing_in_en}"
        assert not missing_in_zh, f"en 有但 zh 缺少的键: {missing_in_zh}"

    def test_data_i18n_attributes_have_translations(self, html):
        """HTML 中所有 data-i18n 属性引用的键在 I18N 中都有定义。"""
        zh_keys = _extract_i18n_keys(html, "zh")
        assert len(zh_keys) > 50, "zh 翻译键数量过少，可能提取失败"
        # 提取所有 data-i18n="xxx" 属性值
        used_keys = set(re.findall(r'data-i18n="(\w+)"', html))
        assert len(used_keys) > 10, "data-i18n 属性数量过少，可能提取失败"
        missing = used_keys - zh_keys
        assert not missing, f"HTML 使用了但 I18N.zh 中缺少的键: {missing}"

    def test_data_i18n_ph_attributes_have_translations(self, html):
        """HTML 中所有 data-i18n-ph 属性引用的键在 I18N 中都有定义。"""
        zh_keys = _extract_i18n_keys(html, "zh")
        used_keys = set(re.findall(r'data-i18n-ph="(\w+)"', html))
        if used_keys:
            missing = used_keys - zh_keys
            assert not missing, f"HTML 使用了但 I18N.zh 中缺少的 placeholder 键: {missing}"

    def test_data_i18n_title_attributes_have_translations(self, html):
        """HTML 中所有 data-i18n-title 属性引用的键在 I18N 中都有定义。"""
        zh_keys = _extract_i18n_keys(html, "zh")
        used_keys = set(re.findall(r'data-i18n-title="(\w+)"', html))
        if used_keys:
            missing = used_keys - zh_keys
            assert not missing, f"HTML 使用了但 I18N.zh 中缺少的 title 键: {missing}"

    def test_data_i18n_opt_attributes_have_translations(self, html):
        """HTML 中所有 data-i18n-opt 属性引用的键在 I18N 中都有定义。"""
        zh_keys = _extract_i18n_keys(html, "zh")
        used_keys = set(re.findall(r'data-i18n-opt="(\w+)"', html))
        if used_keys:
            missing = used_keys - zh_keys
            assert not missing, f"HTML 使用了但 I18N.zh 中缺少的 option 键: {missing}"


# ════════════════════════════════════════════════════════════
# 模板变量渲染
# ════════════════════════════════════════════════════════════
class TestServerLangRendering:
    """验证后端模板变量在前端正确渲染。"""

    def test_server_lang_auto_default(self, html):
        """默认 server_lang 渲染为 "auto"。"""
        assert '"auto"' in html or "'auto'" in html

    def test_server_lang_zh(self, temp_dir, monkeypatch):
        """设置 SERVER_LANG=zh 后模板正确渲染。"""
        _patch_app(monkeypatch, temp_dir)
        file_browser.app.config["SERVER_LANG"] = "zh"
        with file_browser.app.test_client() as c:
            resp = c.get("/")
            page = resp.data.decode("utf-8")
            assert '_serverLang="zh"' in page

    def test_server_lang_en(self, temp_dir, monkeypatch):
        """设置 SERVER_LANG=en 后模板正确渲染。"""
        _patch_app(monkeypatch, temp_dir)
        file_browser.app.config["SERVER_LANG"] = "en"
        with file_browser.app.test_client() as c:
            resp = c.get("/")
            page = resp.data.decode("utf-8")
            assert '_serverLang="en"' in page


# ════════════════════════════════════════════════════════════
# 前端关键功能函数
# ════════════════════════════════════════════════════════════
class TestCoreFunctions:
    """验证前端关键 JavaScript 函数已定义。"""

    @pytest.mark.parametrize("func_name", [
        "doLogin",
        "doLogout",
        "loadPath",
        "fetchList",
        "renderFileList",
        "updateBreadcrumb",
        "previewFile",
        "toggleEdit",
        "saveFile",
        "showUpload",
        "showMkdir",
        "showMkfile",
        "deleteConfirm",
        "renamePrompt",
        "showClipboard",
        "showBookmarks",
        "toggleSelectMode",
        "batchDownload",
        "batchDelete",
        "toggleGridView",
        "showShareDialog",
    ])
    def test_function_defined(self, html, func_name):
        """前端关键函数已定义。"""
        assert f"function {func_name}(" in html or f"{func_name}=" in html

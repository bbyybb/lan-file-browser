# -*- coding: utf-8 -*-
"""
防休眠功能单元测试。
覆盖 Windows / macOS / Linux 三个平台分支的 prevent_sleep_start 和 prevent_sleep_stop。
"""

import sys
import os
import unittest
from unittest.mock import patch, MagicMock

# 确保可以导入项目根目录下的 file_browser 模块
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

import file_browser


class TestPreventSleepWindows(unittest.TestCase):
    """Windows 平台防休眠测试"""

    def setUp(self):
        """每个测试前重置全局状态"""
        file_browser._sleep_inhibit_process = None

    @patch('sys.platform', 'win32')
    def test_start_calls_set_thread_execution_state(self):
        """验证 start 调用了 SetThreadExecutionState(0x80000001)"""
        mock_ctypes = MagicMock()
        with patch.dict('sys.modules', {'ctypes': mock_ctypes}):
            file_browser.prevent_sleep_start()
            mock_ctypes.windll.kernel32.SetThreadExecutionState.assert_called_once_with(
                0x80000000 | 0x00000001
            )

    @patch('sys.platform', 'win32')
    def test_stop_calls_reset(self):
        """验证 stop 调用了 SetThreadExecutionState(0x80000000) 进行重置"""
        mock_ctypes = MagicMock()
        with patch.dict('sys.modules', {'ctypes': mock_ctypes}):
            file_browser.prevent_sleep_stop()
            mock_ctypes.windll.kernel32.SetThreadExecutionState.assert_called_once_with(
                0x80000000
            )

    @patch('sys.platform', 'win32')
    def test_start_returns_true_on_success(self):
        """验证正常情况下 start 返回 True"""
        mock_ctypes = MagicMock()
        with patch.dict('sys.modules', {'ctypes': mock_ctypes}):
            result = file_browser.prevent_sleep_start()
            self.assertTrue(result)

    @patch('sys.platform', 'win32')
    def test_start_returns_false_on_error(self):
        """验证 ctypes 抛异常时 start 返回 False"""
        mock_ctypes = MagicMock()
        mock_ctypes.windll.kernel32.SetThreadExecutionState.side_effect = OSError("模拟错误")
        with patch.dict('sys.modules', {'ctypes': mock_ctypes}):
            result = file_browser.prevent_sleep_start()
            self.assertFalse(result)


class TestPreventSleepMacOS(unittest.TestCase):
    """macOS 平台防休眠测试"""

    def setUp(self):
        """每个测试前重置全局状态"""
        file_browser._sleep_inhibit_process = None

    @patch('sys.platform', 'darwin')
    @patch('subprocess.Popen')
    def test_start_calls_caffeinate(self, mock_popen):
        """验证 start 调用了包含 caffeinate 的命令"""
        mock_popen.return_value = MagicMock()
        file_browser.prevent_sleep_start()
        # 获取实际调用参数
        args, kwargs = mock_popen.call_args
        cmd = args[0]
        self.assertIn('caffeinate', cmd)

    @patch('sys.platform', 'darwin')
    @patch('subprocess.Popen')
    def test_stop_terminates_process(self, mock_popen):
        """验证 stop 对子进程调用了 terminate()"""
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        # 先启动以设置 _sleep_inhibit_process
        file_browser.prevent_sleep_start()
        # 再停止
        file_browser.prevent_sleep_stop()
        mock_process.terminate.assert_called_once()

    @patch('sys.platform', 'darwin')
    @patch('subprocess.Popen', side_effect=OSError("模拟错误"))
    def test_start_returns_false_on_error(self, mock_popen):
        """验证 Popen 抛异常时 start 返回 False"""
        result = file_browser.prevent_sleep_start()
        self.assertFalse(result)


class TestPreventSleepLinux(unittest.TestCase):
    """Linux 平台防休眠测试"""

    def setUp(self):
        """每个测试前重置全局状态"""
        file_browser._sleep_inhibit_process = None

    @patch('sys.platform', 'linux')
    @patch('subprocess.Popen')
    def test_start_calls_systemd_inhibit(self, mock_popen):
        """验证 start 调用了包含 systemd-inhibit 的命令"""
        mock_popen.return_value = MagicMock()
        file_browser.prevent_sleep_start()
        args, kwargs = mock_popen.call_args
        cmd = args[0]
        self.assertIn('systemd-inhibit', cmd)

    @patch('sys.platform', 'linux')
    @patch('subprocess.Popen')
    def test_stop_terminates_process(self, mock_popen):
        """验证 stop 对子进程调用了 terminate()"""
        mock_process = MagicMock()
        mock_popen.return_value = mock_process
        # 先启动以设置 _sleep_inhibit_process
        file_browser.prevent_sleep_start()
        # 再停止
        file_browser.prevent_sleep_stop()
        mock_process.terminate.assert_called_once()

    @patch('sys.platform', 'linux')
    @patch('subprocess.Popen', side_effect=OSError("模拟错误"))
    def test_start_returns_false_on_error(self, mock_popen):
        """验证 Popen 抛异常时 start 返回 False"""
        result = file_browser.prevent_sleep_start()
        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()

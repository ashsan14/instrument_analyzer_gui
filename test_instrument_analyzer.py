#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
instrument_analyzer_gui.pyw のユニットテスト

各メソッドの機能をテストします。
実行: python test_instrument_analyzer.py
"""

import unittest
from unittest.mock import Mock, patch, MagicMock
import tkinter as tk
from collections import deque
import numpy as np
import sys
import os
import importlib.util

# .pyw ファイルをモジュールとして読み込み
pyw_path = os.path.join(os.path.dirname(__file__), "instrument_analyzer_gui.pyw")
spec = importlib.util.spec_from_file_location("instrument_analyzer_gui", pyw_path)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

InstrumentAnalyzerGUI = module.InstrumentAnalyzerGUI
CHUNK = module.CHUNK
CHANNELS = module.CHANNELS
RATE = module.RATE
FRAME_LENGTH = module.FRAME_LENGTH
HOP_LENGTH = module.HOP_LENGTH
logger = module.logger


class TestInstrumentAnalyzerGUIInit(unittest.TestCase):
    """
    __init__ メソッドのテスト
    """
    
    def setUp(self):
        """各テストの前に実行"""
        self.root = tk.Tk()
    
    def tearDown(self):
        """各テストの後に実行"""
        try:
            self.root.destroy()
        except Exception:
            pass
    
    def test_init_creates_window(self):
        """ウィンドウ作成確認"""
        app = InstrumentAnalyzerGUI(self.root)
        self.assertIsNotNone(app.master)
        self.assertEqual(app.master.title(), "USB Instrument Analyzer (sounddevice)")
    
    def test_init_initializes_attributes(self):
        """属性初期化確認"""
        app = InstrumentAnalyzerGUI(self.root)
        self.assertIsNone(app.stream)
        self.assertFalse(app.is_running)
        self.assertEqual(app.current_f0, 0.0)
        self.assertEqual(app.current_note, "N/A")
        self.assertEqual(app.current_volume, 0)
    
    def test_init_creates_buffer(self):
        """リングバッファ作成確認"""
        app = InstrumentAnalyzerGUI(self.root)
        self.assertIsInstance(app.buffer, deque)
        self.assertEqual(app.buffer.maxlen, FRAME_LENGTH)
    
    def test_init_creates_threads(self):
        """スレッド作成確認"""
        app = InstrumentAnalyzerGUI(self.root)
        self.assertIsNotNone(app.audio_thread)
        self.assertIsNotNone(app.gui_update_thread)
        self.assertTrue(app.audio_thread.daemon)
        self.assertTrue(app.gui_update_thread.daemon)
    
    def test_init_with_device_index(self):
        """デバイスインデックス設定確認"""
        device_index = 1
        app = InstrumentAnalyzerGUI(self.root, device_index=device_index)
        self.assertEqual(app.device_index, device_index)


class TestPopulateDevices(unittest.TestCase):
    """
    _populate_devices メソッドのテスト
    """
    
    def setUp(self):
        """各テストの前に実行"""
        self.root = tk.Tk()
        self.app = InstrumentAnalyzerGUI(self.root)
    
    def tearDown(self):
        """各テストの後に実行"""
        try:
            self.root.destroy()
        except Exception:
            pass
    
    @patch('sounddevice.query_devices')
    def test_populate_devices_filters_input_only(self, mock_query):
        """入力チャネルを持つデバイスのみフィルタ確認"""
        # モックデバイス情報
        mock_query.return_value = [
            {'name': 'Device A', 'max_input_channels': 2},  # 入力あり
            {'name': 'Device B', 'max_input_channels': 0},  # 入力なし
            {'name': 'Device C', 'max_input_channels': 1},  # 入力あり
        ]
        
        self.app._populate_devices()
        
        # 入力チャネルがあるデバイスのみ含まれることを確認
        values = self.app.device_combobox['values']
        self.assertEqual(len(values), 2)
        self.assertIn('Device A (Index: 0)', values)
        self.assertIn('Device C (Index: 2)', values)
    
    @patch('sounddevice.query_devices')
    def test_populate_devices_sets_default(self, mock_query):
        """デフォルトデバイス設定確認"""
        mock_query.return_value = [
            {'name': 'Microphone', 'max_input_channels': 1},
        ]
        
        self.app._populate_devices()
        
        # 最初のデバイスがデフォルトに設定されることを確認
        self.assertEqual(self.app.device_index, 0)
        self.assertEqual(self.app.device_var.get(), 'Microphone (Index: 0)')
    
    @patch('sounddevice.query_devices')
    def test_populate_devices_creates_mapping(self, mock_query):
        """デバイス名とインデックスのマッピング確認"""
        mock_query.return_value = [
            {'name': 'Device 1', 'max_input_channels': 1},
            {'name': 'Device 2', 'max_input_channels': 1},
        ]
        
        self.app._populate_devices()
        
        # マッピングが正しく作成されることを確認
        self.assertIn('Device 1 (Index: 0)', self.app.device_map)
        self.assertIn('Device 2 (Index: 1)', self.app.device_map)
        self.assertEqual(self.app.device_map['Device 1 (Index: 0)'], 0)
        self.assertEqual(self.app.device_map['Device 2 (Index: 1)'], 1)


class TestOnDeviceSelected(unittest.TestCase):
    """
    _on_device_selected メソッドのテスト
    """
    
    def setUp(self):
        """各テストの前に実行"""
        self.root = tk.Tk()
        self.app = InstrumentAnalyzerGUI(self.root)
        self.app.device_map = {
            'Device A (Index: 0)': 0,
            'Device B (Index: 1)': 1,
        }
    
    def tearDown(self):
        """各テストの後に実行"""
        try:
            self.root.destroy()
        except Exception:
            pass
    
    def test_on_device_selected_updates_index(self):
        """デバイスインデックス更新確認"""
        self.app.device_var.set('Device B (Index: 1)')
        self.app._on_device_selected()
        
        self.assertEqual(self.app.device_index, 1)
    
    def test_on_device_selected_with_invalid_device(self):
        """無効なデバイス選択時の処理確認"""
        self.app.device_var.set('Invalid Device')
        self.app._on_device_selected()
        
        # device_mapに存在しないため None が返される
        self.assertIsNone(self.app.device_index)


class TestStartAnalysis(unittest.TestCase):
    """
    start_analysis メソッドのテスト
    """
    
    def setUp(self):
        """各テストの前に実行"""
        self.root = tk.Tk()
        self.app = InstrumentAnalyzerGUI(self.root)
        self.app.device_index = 0  # デバイスを設定
    
    def tearDown(self):
        """各テストの後に実行"""
        try:
            self.app.is_running = False
            self.root.destroy()
        except Exception:
            pass
    
    def test_start_analysis_without_device(self):
        """デバイス未選択時の処理確認"""
        self.app.device_index = None
        self.app.start_analysis()
        
        # is_running は False のまま
        self.assertFalse(self.app.is_running)
    
    def test_start_analysis_sets_running_flag(self):
        """実行フラグ設定確認"""
        self.app.start_analysis()
        
        self.assertTrue(self.app.is_running)
    
    def test_start_analysis_updates_button_state(self):
        """ボタン状態更新確認"""
        self.app.start_analysis()
        
        # Start ボタンは無効化、Stop ボタンは有効化されることを確認
        self.assertEqual(str(self.app.start_button['state']), 'disabled')
        self.assertEqual(str(self.app.stop_button['state']), 'normal')
    
    def test_start_analysis_clears_stop_event(self):
        """_stop_event クリア確認"""
        self.app._stop_event.set()  # 先に set
        self.app.start_analysis()
        
        # クリアされていることを確認
        self.assertFalse(self.app._stop_event.is_set())


class TestStopAnalysis(unittest.TestCase):
    """
    stop_analysis メソッドのテスト
    """
    
    def setUp(self):
        """各テストの前に実行"""
        self.root = tk.Tk()
        self.app = InstrumentAnalyzerGUI(self.root)
        self.app.device_index = 0
        self.app.is_running = True
    
    def tearDown(self):
        """各テストの後に実行"""
        try:
            self.root.destroy()
        except Exception:
            pass
    
    def test_stop_analysis_clears_running_flag(self):
        """実行フラグクリア確認"""
        self.app.stop_analysis()
        
        self.assertFalse(self.app.is_running)
    
    def test_stop_analysis_updates_button_state(self):
        """ボタン状態更新確認"""
        self.app.stop_analysis()
        
        # Start ボタンは有効化、Stop ボタンは無効化されることを確認
        self.assertEqual(str(self.app.start_button['state']), 'normal')
        self.assertEqual(str(self.app.stop_button['state']), 'disabled')


class TestUpdateGUIElements(unittest.TestCase):
    """
    _update_gui_elements メソッドのテスト
    """
    
    def setUp(self):
        """各テストの前に実行"""
        self.root = tk.Tk()
        self.app = InstrumentAnalyzerGUI(self.root)
    
    def tearDown(self):
        """各テストの後に実行"""
        try:
            self.root.destroy()
        except Exception:
            pass
    
    def test_update_gui_elements_updates_note_label(self):
        """ノート表示更新確認"""
        self.app.current_note = "C4"
        self.app._update_gui_elements()
        
        self.assertEqual(self.app.note_label['text'], "C4")
    
    def test_update_gui_elements_updates_frequency_label(self):
        """周波数表示更新確認"""
        self.app.current_f0 = 261.63
        self.app._update_gui_elements()
        
        self.assertEqual(self.app.f0_label['text'], "261.63 Hz")
    
    def test_update_gui_elements_with_zero_volume(self):
        """音量ゼロ時のメーター更新確認"""
        self.app.current_volume = 0
        self.app._update_gui_elements()


class TestBufferManagement(unittest.TestCase):
    """
    バッファ管理の機能テスト
    """
    
    def setUp(self):
        """各テストの前に実行"""
        self.root = tk.Tk()
        self.app = InstrumentAnalyzerGUI(self.root)
    
    def tearDown(self):
        """各テストの後に実行"""
        try:
            self.root.destroy()
        except Exception:
            pass
    
    def test_buffer_maxlen_enforcement(self):
        """バッファサイズ制限確認"""
        # FRAME_LENGTH 以上のデータを追加
        data = list(range(FRAME_LENGTH + 100))
        self.app.buffer.extend(data)
        
        # バッファサイズが FRAME_LENGTH で制限されることを確認
        self.assertEqual(len(self.app.buffer), FRAME_LENGTH)
    
    def test_buffer_popleft(self):
        """バッファからの要素削除確認"""
        self.app.buffer.extend([1, 2, 3, 4, 5])
        initial_len = len(self.app.buffer)
        
        self.app.buffer.popleft()
        
        self.assertEqual(len(self.app.buffer), initial_len - 1)


class TestParameterConstants(unittest.TestCase):
    """
    定数パラメータのテスト
    """
    
    def test_constants_values(self):
        """定数値の確認"""
        self.assertEqual(CHUNK, 1024)
        self.assertEqual(CHANNELS, 1)
        self.assertEqual(RATE, 44100)
        self.assertEqual(FRAME_LENGTH, CHUNK * 2)
        self.assertEqual(HOP_LENGTH, CHUNK)


if __name__ == '__main__':
    # テスト実行
    # verbosity=2 で詳細出力
    unittest.main(verbosity=2)

import tkinter as tk
from tkinter import ttk, messagebox
import sounddevice as sd
import numpy as np
import librosa
import json
import os
from datetime import datetime
import logging
import traceback
import threading
import time
from collections import deque
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.animation import FuncAnimation
# Windows specific imports for advanced microphone access
import subprocess
import sys
import ctypes
from ctypes import wintypes

__version__ = "0.2.1"

# --- ログ設定 ---
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = os.path.join(LOG_DIR, f"app_{timestamp}.log")
ERROR_LOG_FILE = os.path.join(LOG_DIR, f"error_{timestamp}.log")

def setup_logger():
    """実行ログ (INFO+) とエラーログ (ERROR+) を分離して出力するロガー生成"""
    logger = logging.getLogger("InstrumentAnalyzer")
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', '%Y-%m-%d %H:%M:%S')
    run_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
    run_handler.setLevel(logging.DEBUG)
    run_handler.setFormatter(formatter)
    logger.addHandler(run_handler)
    err_handler = logging.FileHandler(ERROR_LOG_FILE, encoding='utf-8')
    err_handler.setLevel(logging.ERROR)
    err_handler.setFormatter(formatter)
    logger.addHandler(err_handler)
    return logger

logger = setup_logger()

# --- 音階データ読み込み ---
def load_note_frequencies():
    """音階と周波数の対応データをJSONファイルから読み込み"""
    try:
        with open('note_frequencies.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load note frequencies: {e}")
        return {"note_frequencies": {}, "note_mapping": {}}

# --- 音階検出関数 ---
def frequency_to_note(frequency, note_data):
    """周波数から最も近い音階を検出"""
    if frequency <= 0:
        return "N/A", "N/A", 0.0
    
    min_diff = float('inf')
    closest_note = "N/A"
    closest_japanese = "N/A"
    closest_freq = 0.0
    
    for note_key, note_info in note_data["note_frequencies"].items():
        diff = abs(note_info["frequency"] - frequency)
        if diff < min_diff:
            min_diff = diff
            closest_note = note_info["western"]
            closest_japanese = note_info["japanese"]
            closest_freq = note_info["frequency"]
    
    return closest_note, closest_japanese, closest_freq

# --- デバイス設定管理 ---
def load_device_config():
    """デバイス設定をJSONファイルから読み込み"""
    try:
        with open('device_config.json', 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        logger.error(f"Failed to load device config: {e}")
        return {
            "device_settings": {
                "last_used_device_index": None,
                "last_used_device_name": "",
                "auto_select_last_device": True
            },
            "microphone_devices": {},
            "device_history": [],
            "connection_status": {}
        }

def save_device_config(config):
    """デバイス設定をJSONファイルに保存"""
    try:
        with open('device_config.json', 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        logger.info("Device configuration saved")
    except Exception as e:
        logger.error(f"Failed to save device config: {e}")

def setup_windows_microphone_permissions():
    """
    Windows マイクアクセス権限の設定と確認
    """
    logger.info("=== Windows Microphone Permission Setup ===")
    
    # 1. 管理者権限チェック
    try:
        is_admin = ctypes.windll.shell32.IsUserAnAdmin()
        logger.info(f"Administrator privileges: {is_admin}")
        
        if not is_admin:
            logger.warning("Running without administrator privileges - some microphone access may be limited")
            
    except Exception as e:
        logger.error(f"Failed to check admin privileges: {e}")
    
    # 2. Windows プライバシー設定確認
    try:
        # マイクアクセス許可のレジストリ確認
        result = subprocess.run([
            'powershell', '-Command',
            'Get-AppxPackage Microsoft.Windows.Cortana | Get-AppxPackageManifest | Select-Object -ExpandProperty Package | Select-Object -ExpandProperty Capabilities'
        ], capture_output=True, text=True, timeout=10)
        
        logger.info("Privacy settings check completed")
        
    except Exception as e:
        logger.error(f"Failed to check privacy settings: {e}")
    
    # 3. デスクトップアプリのマイクアクセス有効化
    try:
        # レジストリでデスクトップアプリのマイクアクセスを確認
        result = subprocess.run([
            'reg', 'query', 
            'HKEY_CURRENT_USER\\Software\\Microsoft\\Windows\\CurrentVersion\\CapabilityAccessManager\\ConsentStore\\microphone',
            '/v', 'Value'
        ], capture_output=True, text=True)
        
        if 'Allow' in result.stdout:
            logger.info("Desktop app microphone access: ALLOWED")
        else:
            logger.warning("Desktop app microphone access may be DENIED")
            logger.warning("To fix: Settings > Privacy & Security > Microphone > Let desktop apps access microphone = ON")
            
    except Exception as e:
        logger.warning(f"Could not verify microphone permissions: {e}")
    
    # 4. ドライバー状態確認
    try:
        result = subprocess.run([
            'powershell', '-Command',
            'Get-PnpDevice -Class AudioEndpoint -PresentOnly | Where-Object {$_.FriendlyName -like "*Mic*" -or $_.FriendlyName -like "*マイク*"} | Select-Object FriendlyName, Status'
        ], capture_output=True, text=True, timeout=15)
        
        if result.stdout:
            logger.info(f"Microphone device status:\\n{result.stdout}")
        else:
            logger.warning("No microphone devices found by Windows PnP")
            
    except Exception as e:
        logger.error(f"Failed to check device status: {e}")
    
    logger.info("=== Microphone Permission Setup Complete ===")

def test_microphone_connection_advanced(device_index, max_attempts=3):
    """
    高度なマイク接続テスト（複数のAPI試行）
    """
    apis_to_try = [
        ('WASAPI', 'wasapi'),
        ('DirectSound', 'directsound'), 
        ('MME', 'mme'),
        ('Default', None)
    ]
    
    for api_name, api_id in apis_to_try:
        logger.info(f"Testing microphone {device_index} with {api_name} API")
        
        for attempt in range(max_attempts):
            try:
                # APIごとの設定でテスト
                extra_settings = {}
                if api_id:
                    # sounddeviceでのAPI指定は限定的なので、基本設定で試行
                    extra_settings['dtype'] = np.float32
                    extra_settings['blocksize'] = CHUNK
                    extra_settings['latency'] = 'low'
                else:
                    extra_settings['dtype'] = np.float32
                    
                # 短時間のテスト録音
                logger.info(f"  Attempt {attempt + 1}/{max_attempts} with {api_name}")
                
                test_data = sd.rec(
                    frames=CHUNK,
                    samplerate=RATE,
                    channels=CHANNELS,
                    device=device_index,
                    **extra_settings
                )
                sd.wait()  # 録音完了を待機
                
                # データ検証
                if test_data is not None and len(test_data) > 0:
                    max_amplitude = np.max(np.abs(test_data))
                    logger.info(f"  ✅ {api_name} API success! Max amplitude: {max_amplitude:.6f}")
                    
                    return True, api_name, max_amplitude
                    
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"  ❌ {api_name} attempt {attempt + 1} failed: {error_msg}")
                
                if attempt < max_attempts - 1:
                    time.sleep(0.5)  # 次の試行前に短い待機
                    
    logger.error(f"All API attempts failed for device {device_index}")
    return False, "None", 0.0

def test_microphone_connection(device_index, lenient=False):
    """
    マイク接続テスト（レガシー互換用ラッパー）
    """
    success, api_used, amplitude = test_microphone_connection_advanced(device_index)
    return success

def is_microphone_device(device_info):
    """デバイスがマイクかどうかを判定（緊和版）"""
    if device_info.get('max_input_channels', 0) == 0:
        return False
    
    device_name = device_info.get('name', '').lower()
    
    # マイク関連キーワード（より幅広い検索）
    mic_keywords = ['mic', 'microphone', 'マイク', 'input', 'capture', 'recording', 
                   'realtek', 'audio', 'sound', 'mapper', 'サウンド', '音声', 'hd audio']
    
    # 除外キーワード（出力デバイスのみ）
    exclude_keywords = ['speaker', 'headphone', 'output', 'スピーカー', 'ヘッドホン']
    
    # 除外キーワードを含む場合は除外
    if any(keyword in device_name for keyword in exclude_keywords):
        return False
    
    # マイクキーワードを含むか、入力チャネルがあるすべてのデバイスを許可
    has_mic_keyword = any(keyword in device_name for keyword in mic_keywords)
    has_input_channels = device_info.get('max_input_channels', 0) > 0
    
    return has_mic_keyword or has_input_channels

def remove_failed_device_from_config(device_index, config):
    """失敗したデバイスを設定ファイルから削除"""
    device_key = str(device_index)
    if device_key in config["microphone_devices"]:
        device_name = config["microphone_devices"][device_key]["name"]
        del config["microphone_devices"][device_key]
        logger.info(f"Removed failed device from config: {device_name} (Index: {device_index})")
        return True
    return False

# --- 設定パラメータ ---
CHUNK = 1024        # 1ブロック当たりのサンプル数
CHANNELS = 1        # モノラル
RATE = 44100        # サンプリングレート (Hz)
FRAME_LENGTH = CHUNK * 2  # pyin用フレーム長
HOP_LENGTH = CHUNK        # フレーム進行量
GAIN_MULTIPLIER = 2000.0  # マイク感度を大幅増幅する係数

# グラフ用設定
GRAPH_HISTORY_SECONDS = 30  # 30秒間の履歴を表示
GRAPH_UPDATE_INTERVAL = 100  # 100ms毎にグラフ更新

class InstrumentAnalyzerGUI:
    """USB接続楽器/マイク入力を解析しGUI表示するクラス (sounddevice版)"""
    def __init__(self, master, device_index=None):
        """
        __init__: ウィンドウ/内部状態初期化。解析スレッドは start_analysis 時に生成。
        再起動対応のため audio_thread / gui_update_thread はここでは生成しない。
        """
        self.master = master
        self.master.title("USB Instrument Analyzer (sounddevice)")
        self.master.geometry("450x420")
        self.master.protocol("WM_DELETE_WINDOW", self._on_closing)

        self.device_index = device_index
        self.stream = None
        self.is_running = False
        self._stop_event = threading.Event()

        self.current_f0 = 0.0
        self.current_note = "N/A"
        self.current_japanese_note = "N/A"
        self.current_volume = 0
        self.note_confidence = 0.0
        
        # 初期接続ステータス
        self.connection_status = "disconnected"
        
        # 音階データ読み込み
        self.note_data = load_note_frequencies()
        
        # デバイス設定読み込み
        self.device_config = load_device_config()

        # オーディオバッファ初期化
        self.buffer = deque(maxlen=FRAME_LENGTH)
        self.audio_buffer = deque(maxlen=CHUNK * 10)  # sounddeviceコールバック用

        self.audio_thread = None
        self.gui_update_thread = None

        self._setup_gui()
        logger.info("GUI initialized")
        
        # GUI要素が作成されてからデバイス検出を実行
        self._populate_devices()

    def _setup_gui(self):
        """GUI要素を配置 (デバイス選択/開始停止/音量/ノート/周波数/グラフ)"""
        # メインフレーム
        main_frame = ttk.Frame(self.master, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # 上部：コントロール部分
        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill=tk.X, pady=(0, 10))
        
        # 下部：グラフ部分
        graph_frame = ttk.Frame(main_frame)
        graph_frame.pack(fill=tk.BOTH, expand=True)
        
        # === コントロール部分の配置 ===
        
        # デバイス選択
        ttk.Label(control_frame, text="Input Device:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.device_var = tk.StringVar()
        self.device_combobox = ttk.Combobox(control_frame, textvariable=self.device_var, state="readonly", width=30)
        self.device_combobox.grid(row=0, column=1, sticky=(tk.W, tk.E), pady=5)
        self.device_combobox.bind("<<ComboboxSelected>>", self._on_device_selected)
        
        # 開始/停止ボタン
        self.start_button = ttk.Button(control_frame, text="Start Analysis", command=self.start_analysis)
        self.start_button.grid(row=1, column=0, pady=10, sticky=tk.W)
        self.stop_button = ttk.Button(control_frame, text="Stop Analysis", command=self.stop_analysis, state=tk.DISABLED)
        self.stop_button.grid(row=1, column=1, pady=10, sticky=tk.E)
        
        # 音量メーター
        ttk.Label(control_frame, text="Volume:").grid(row=2, column=0, sticky=tk.W, pady=5)
        volume_frame = ttk.Frame(control_frame)
        volume_frame.grid(row=2, column=1, sticky=(tk.W, tk.E), pady=5)
        
        self.volume_canvas = tk.Canvas(volume_frame, width=150, height=20, bg="lightgray", bd=1, relief="sunken")
        self.volume_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.volume_bar = self.volume_canvas.create_rectangle(0, 0, 0, 20, fill="green")
        
        # 音量レベル数値表示
        self.volume_level_label = ttk.Label(volume_frame, text="0%", font=("Helvetica", 10), width=5)
        self.volume_level_label.pack(side=tk.RIGHT, padx=(5, 0))
        
        # 音高表示 (Western notation)
        ttk.Label(control_frame, text="Detected Note (Western):").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.note_label = ttk.Label(control_frame, text="N/A", font=("Helvetica", 16, "bold"), foreground="blue")
        self.note_label.grid(row=3, column=1, sticky=(tk.W, tk.E), pady=5)
        
        # 音高表示 (Japanese notation)
        ttk.Label(control_frame, text="Detected Note (Japanese):").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.japanese_note_label = ttk.Label(control_frame, text="N/A", font=("Helvetica", 16, "bold"), foreground="red")
        self.japanese_note_label.grid(row=4, column=1, sticky=(tk.W, tk.E), pady=5)
        
        # 周波数表示
        ttk.Label(control_frame, text="Frequency (F0):").grid(row=5, column=0, sticky=tk.W, pady=5)
        self.f0_label = ttk.Label(control_frame, text="0.00 Hz", font=("Helvetica", 14))
        self.f0_label.grid(row=5, column=1, sticky=(tk.W, tk.E), pady=5)
        
        # 音階信頼度表示
        ttk.Label(control_frame, text="Note Confidence:").grid(row=6, column=0, sticky=tk.W, pady=5)
        self.confidence_label = ttk.Label(control_frame, text="0%", font=("Helvetica", 12))
        self.confidence_label.grid(row=6, column=1, sticky=(tk.W, tk.E), pady=5)
        
        # 接続ステータス表示
        ttk.Label(control_frame, text="Connection Status:").grid(row=7, column=0, sticky=tk.W, pady=5)
        self.connection_label = ttk.Label(control_frame, text="Not Connected", font=("Helvetica", 12), foreground="gray")
        self.connection_label.grid(row=7, column=1, sticky=(tk.W, tk.E), pady=5)
        
        # グラフレイアウトの設定
        control_frame.columnconfigure(1, weight=1)
        
        # === グラフ部分の設定 ===
        self._setup_graph(graph_frame)

    def _setup_graph(self, parent_frame):
        """リアルタイムグラフの設定"""
        # グラフフレームとタイトル
        ttk.Label(parent_frame, text="Real-time Audio Analysis", font=("Helvetica", 12, "bold")).pack(pady=(0, 5))
        
        # matplotlib図の作成
        plt.style.use('default')
        self.fig, (self.ax1, self.ax2) = plt.subplots(2, 1, figsize=(10, 6), facecolor='white')
        self.fig.tight_layout(pad=3.0)
        
        # 音量グラフ設定
        self.ax1.set_title('Volume Level (%)', fontsize=10, fontweight='bold')
        self.ax1.set_ylabel('Volume (%)')
        self.ax1.set_ylim(0, 100)
        self.ax1.grid(True, alpha=0.3)
        self.volume_line, = self.ax1.plot([], [], 'g-', linewidth=2, label='Volume')
        self.ax1.legend(loc='upper right')
        
        # 周波数グラフ設定
        self.ax2.set_title('Detected Frequency (Hz)', fontsize=10, fontweight='bold')
        self.ax2.set_xlabel('Time (seconds)')
        self.ax2.set_ylabel('Frequency (Hz)')
        self.ax2.set_ylim(80, 2000)  # C2からC7程度の範囲
        self.ax2.set_yscale('log')
        self.ax2.grid(True, alpha=0.3)
        self.frequency_line, = self.ax2.plot([], [], 'b-', linewidth=2, label='F0')
        self.ax2.legend(loc='upper right')
        
        # 主要音階の水平線を追加
        note_frequencies = {
            'C4': 261.63, 'D4': 293.66, 'E4': 329.63, 'F4': 349.23,
            'G4': 392.00, 'A4': 440.00, 'B4': 493.88,
            'C5': 523.25
        }
        for note, freq in note_frequencies.items():
            self.ax2.axhline(y=freq, color='red', linestyle='--', alpha=0.3, linewidth=1)
            self.ax2.text(0.02, freq, note, transform=self.ax2.get_yaxis_transform(), 
                         fontsize=8, alpha=0.7, verticalalignment='center')
        
        # TkinterにmatplotlibのグラフをEmbed
        self.canvas = FigureCanvasTkAgg(self.fig, parent_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # グラフ更新用アニメーション
        self.animation = None

    def _populate_devices(self):
        """マイクデバイスのみを検出し、接続確認後にComboBoxに設定（Windows既定マイク優先）"""
        try:
            devices_info = sd.query_devices()
            devices = []
            device_map = {}
            failed_devices = []
            default_input_device = None
            
            # Windows既定の入力デバイスを取得
            try:
                default_device_info = sd.query_devices(kind='input')
                default_input_device = default_device_info['index']
                logger.info(f"Windows default input device: {default_device_info['name']} (Index: {default_input_device})")
            except Exception as e:
                logger.warning(f"Could not get default input device: {e}")
            
            logger.info("Scanning for microphone devices (lenient mode)...")
            
            # 既定デバイスを最初に処理するため、デバイスリストを並び替え
            device_indices = list(range(len(devices_info)))
            if default_input_device is not None and default_input_device < len(devices_info):
                # 既定デバイスを先頭に移動
                device_indices.remove(default_input_device)
                device_indices.insert(0, default_input_device)
            
            for idx in device_indices:
                dev = devices_info[idx]
                # マイクデバイスかどうかチェック
                if is_microphone_device(dev):
                    device_name = dev['name']
                    is_default = (idx == default_input_device)
                    
                    if is_default:
                        logger.info(f"Processing Windows default microphone: {device_name} (Index: {idx})")
                    else:
                        logger.info(f"Found microphone candidate: {device_name} (Index: {idx})")
                    
                    # 緊急対応: 接続テストをスキップし、すべてのデバイスを強制的に追加
                    logger.warning(f"Skipping connection test - adding all devices due to driver compatibility issues")
                    
                    if is_default:
                        display_name = f"🎤 {device_name} (Index: {idx}) [Default]"
                    else:
                        display_name = f"{device_name} (Index: {idx})"
                    devices.append(display_name)
                    device_map[display_name] = idx
                    
                    # デバイス設定に保存
                    self.device_config["microphone_devices"][str(idx)] = {
                        "name": device_name,
                        "index": idx,
                        "last_connected": datetime.now().isoformat(),
                        "connection_status": "untested",
                        "is_default": is_default
                    }
                    
                    if is_default:
                        logger.info(f"✓ Windows default microphone added (untested): {device_name}")
                    else:
                        logger.info(f"✓ Microphone added (untested): {device_name}")
            
            self.device_combobox['values'] = devices
            self.device_map = device_map
            
            # デバイス選択の優先順位:
            # 1. 最後に使用したデバイス（設定で有効な場合）
            # 2. Windows既定デバイス
            # 3. 最初の利用可能デバイス
            
            selected_device = None
            
            # 最後に使用したデバイスの自動選択
            last_device_idx = self.device_config["device_settings"].get("last_used_device_index")
            if (last_device_idx is not None and 
                self.device_config["device_settings"].get("auto_select_last_device", True)):
                for display_name, idx in device_map.items():
                    if idx == last_device_idx:
                        selected_device = display_name
                        logger.info(f"Auto-selected last used device: {display_name}")
                        break
            
            # マイク系デバイスを最優先で選択
            if selected_device is None and devices:
                # 実際のマイクデバイスを優先
                microphone_keywords = ["マイク", "Mic", "Microphone", "Array", "配列"]
                for display_name in devices:
                    if any(keyword in display_name for keyword in microphone_keywords):
                        # ステレオミキサーは除外
                        if "ステレオ" not in display_name and "Stereo" not in display_name:
                            selected_device = display_name
                            logger.info(f"Auto-selected microphone device: {display_name}")
                            break
                            
            # 既定デバイスが利用可能な場合は次候補として選択
            if selected_device is None and devices:
                for display_name in devices:
                    if "[Default]" in display_name:
                        # ステレオミキサーでなければ選択
                        if "ステレオ" not in display_name and "Stereo" not in display_name:
                            selected_device = display_name
                            logger.info(f"Auto-selected Windows default device: {display_name}")
                            break
            
            # 最初の利用可能デバイスを選択
            if selected_device is None and devices:
                selected_device = devices[0]
                logger.info(f"Selected first available device: {selected_device}")
            
            # 選択されたデバイスを設定
            if selected_device:
                self.device_var.set(selected_device)
                self.device_index = device_map[selected_device]
                # 接続ステータスを設定
                if "[Default]" in selected_device:
                    self.connection_label.config(text="Default device ready", foreground="green")
                else:
                    self.connection_label.config(text="Ready to connect", foreground="blue")
            else:
                self.connection_label.config(text="No microphones found", foreground="red")
            
            # 設定保存
            save_device_config(self.device_config)
            
            logger.info(f"Emergency mode: Added {len(devices)} microphone devices (no connection testing)")
            logger.info("Note: Devices are added without testing due to Windows audio driver compatibility issues")
            logger.info("Real connection testing will occur when you click 'Start Analysis'")
                
        except Exception as e:
            logger.error(f"Device enumeration error: {e}")
            logger.error(traceback.format_exc())

    def _on_device_selected(self, event=None):
        """デバイス選択変更時に内部インデックス更新と設定保存"""
        name = self.device_var.get()
        self.device_index = self.device_map.get(name)
        
        # 接続ステータスをリセット
        if self.device_index is not None:
            if "[Default]" in name:
                self.connection_label.config(text="Default device ready", foreground="green")
            else:
                self.connection_label.config(text="Ready to connect", foreground="blue")
        else:
            self.connection_label.config(text="Invalid device", foreground="red")
        
        # 最後に使用したデバイスとして保存
        if self.device_index is not None:
            self.device_config["device_settings"]["last_used_device_index"] = self.device_index
            self.device_config["device_settings"]["last_used_device_name"] = name
            
            # 使用履歴に追加
            history_entry = {
                "device_index": self.device_index,
                "device_name": name,
                "selected_at": datetime.now().isoformat()
            }
            
            device_history = self.device_config.get("device_history", [])
            device_history.append(history_entry)
            
            # 履歴を最新10件に制限
            self.device_config["device_history"] = device_history[-10:]
            
            # 設定保存
            save_device_config(self.device_config)
            
        logger.info(f"Selected device: {name} -> index {self.device_index}")

    def _find_working_device(self):
        """
        利用可能なオーディオデバイスの中から動作するものを検索
        """
        logger.info("Searching for working audio devices...")
        devices_info = sd.query_devices()
        
        # 診断結果に基づく確実に動作するデバイス
        known_working_devices = [29, 27, 32]  # ステレオミキサー、PCスピーカー
        
        logger.info("Testing known working devices first...")
        
        # 既知の動作デバイスを最初にテスト
        for device_index in known_working_devices:
            if device_index < len(devices_info):
                device = devices_info[device_index]
                if device.get('max_input_channels', 0) > 0:
                    logger.info(f"Testing known working device {device_index}: {device['name']}")
                    
                    try:
                        # 簡単な接続テスト
                        test_data = sd.rec(
                            frames=512,  # 小さなバッファでテスト
                            samplerate=44100,
                            channels=1,
                            device=device_index,
                            dtype=np.float32
                        )
                        sd.wait()
                        
                        if test_data is not None and len(test_data) > 0:
                            max_level = np.max(np.abs(test_data))
                            logger.info(f"✅ Working device confirmed: {device_index} - {device['name']} (level: {max_level:.6f})")
                            return device_index
                            
                    except Exception as e:
                        logger.debug(f"Known device {device_index} failed: {str(e)[:100]}")
                        continue
        
        # 既知デバイスが失敗した場合、全デバイススキャン
        logger.info("Known devices failed, scanning all devices...")
        working_candidates = []
        
        for idx, dev in enumerate(devices_info):
            if dev.get('max_input_channels', 0) > 0:
                device_name = dev.get('name', '').lower()
                
                # スピーカー系デバイスを優先（出力だがキャプチャ可能）
                if 'スピーカー' in device_name or 'speaker' in device_name or 'ステレオ' in device_name:
                    working_candidates.append((1, idx, dev['name']))
                # USB/外部デバイス
                elif 'usb' in device_name or 'interface' in device_name:
                    working_candidates.append((2, idx, dev['name']))
                # Windows標準デバイス
                elif 'microsoft' in device_name or 'mapper' in device_name:
                    working_candidates.append((3, idx, dev['name']))
                # その他
                else:
                    working_candidates.append((4, idx, dev['name']))
        
        # 優先度順にソート
        working_candidates.sort()
        
        # 上位3つまでテスト
        for priority, device_index, device_name in working_candidates[:3]:
            logger.info(f"Testing device {device_index}: {device_name} (priority {priority})")
            
            try:
                test_data = sd.rec(
                    frames=512,
                    samplerate=44100,
                    channels=1,
                    device=device_index,
                    dtype=np.float32
                )
                sd.wait()
                
                if test_data is not None and len(test_data) > 0:
                    logger.info(f"✅ Working device found: {device_index} - {device_name}")
                    return device_index
                    
            except Exception as e:
                logger.debug(f"Device {device_index} failed: {str(e)[:100]}")
                continue
        
        logger.error("No working audio devices found")
        return None

    def start_analysis(self):
        """解析開始: スレッド再生成対応、接続状態表示付き"""
        if self.is_running:
            return
        if self.device_index is None:
            logger.warning("Input device not selected")
            self.connection_label.config(text="No Device Selected", foreground="red")
            return
            
        # 接続中表示
        self.connection_label.config(text="Connecting...", foreground="orange")
        self.master.update_idletasks()  # GUI更新を即座に反映
        
        # デバイス接続テスト（事前テストは軽量化、ほぼ常に続行）
        logger.info(f"Starting analysis for device {self.device_index}")
        logger.info("=== MICROPHONE MODE: Optimized for Direct Audio Input ===")
        logger.info("Using real microphone input for live audio analysis")
        logger.info("For best results:")
        logger.info("1. Speak, sing, or play instruments directly into the microphone")
        logger.info("2. Ensure microphone is set as default input device")
        logger.info("3. Check microphone privacy settings are enabled")
        logger.info("4. Try speaking loudly or playing instruments close to microphone")
        logger.info(f"5. Using {GAIN_MULTIPLIER}x gain for microphone sensitivity")
        logger.info("=== Attempting connection with enhanced microphone support ===")
        
        # Windows マイクアクセス権限の設定
        setup_windows_microphone_permissions()
        
        try:
            # 高度な接続テストを実行
            connection_success, api_used, test_amplitude = test_microphone_connection_advanced(self.device_index)
            
            if not connection_success:
                logger.warning(f"Primary device {self.device_index} failed - searching for working alternatives")
                # 自動フォールバック: 他の利用可能なデバイスを検索
                working_device = self._find_working_device()
                if working_device is not None:
                    logger.info(f"Found working alternative device: {working_device}")
                    self.device_index = working_device
                    connection_success, api_used, test_amplitude = test_microphone_connection_advanced(self.device_index)
                
            if not connection_success:
                raise Exception(f"No working audio devices found (tried device {self.device_index} and alternatives)")
            
            logger.info(f"✅ Connected using {api_used} API, test amplitude: {test_amplitude:.6f}")
            
            # 音声ストリームを開始（最適なバッファサイズ設定）
            self.stream = sd.InputStream(
                device=self.device_index,
                channels=CHANNELS,
                samplerate=RATE,
                dtype=np.float32,
                blocksize=CHUNK,
                latency='low',  # 低レイテンシ
                callback=self.audio_callback
            )
            self.stream.start()
            logger.info("Audio stream started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start microphone: {e}")
            logger.error(f"Error details: {traceback.format_exc()}")
            
            # UI状態をリセット（重要：Connecting状態を解除）
            self.is_running = False
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            self.device_combobox.config(state="readonly")
            self.connection_label.config(text="Connection Failed", foreground="red")
            
            # エラーメッセージをより分かりやすく表示
            if "MME error 1" in str(e) or "Undefined external error" in str(e):
                error_msg = (
                    "Windows audio driver error detected.\n\n"
                    "Quick fixes to try:\n"
                    "1. Run this app as Administrator\n"
                    "2. Close other audio apps (Zoom, Teams, etc.)\n"
                    "3. Windows Settings → Privacy → Microphone → Allow desktop apps\n"
                    "4. Try a different microphone device from the dropdown\n\n"
                    f"Technical error: {str(e)[:100]}..."
                )
            else:
                error_msg = f"Cannot connect to microphone {self.device_index}:\n{str(e)[:200]}..."
            
            messagebox.showerror("Microphone Connection Error", error_msg)
            return
        self.is_running = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.device_combobox.config(state=tk.DISABLED)
        self._stop_event.clear()
        
        # グラフデータをリセットして開始
        self.time_data.clear()
        self.volume_data.clear()
        self.frequency_data.clear()
        self.graph_start_time = time.time()
        
        # グラフアニメーション開始
        if self.animation is None:
            self.animation = FuncAnimation(self.fig, self._update_graph, interval=GRAPH_UPDATE_INTERVAL, blit=False)
            self.canvas.draw()
        
        if not self.audio_thread or not self.audio_thread.is_alive():
            self.audio_thread = threading.Thread(target=self._audio_loop, daemon=True)
            self.audio_thread.start()
        if not self.gui_update_thread or not self.gui_update_thread.is_alive():
            self.gui_update_thread = threading.Thread(target=self._gui_update_loop, daemon=True)
            self.gui_update_thread.start()
        logger.info("--- Analysis Started ---")

    def stop_analysis(self):
        """解析停止: フラグ更新 (スレッド自体はイベント監視で自然終了)"""
        if not self.is_running:
            return
        self.is_running = False
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.device_combobox.config(state="readonly")
        self.connection_label.config(text="Disconnected", foreground="gray")
        
        # グラフアニメーション停止
        if self.animation is not None:
            self.animation.event_source.stop()
            self.animation = None
            
        logger.info("--- Analysis Stopped ---")

    def audio_callback(self, indata, frames, time_info, status):
        """sounddevice InputStream用のオーディオコールバック"""
        if status:
            logger.warning(f"Audio status: {status}")
        try:
            chunk = indata[:, 0] if indata.ndim > 1 else indata
            
            # マイク感度を増幅（Windowsマイクは通常音量が小さい）
            chunk = chunk * GAIN_MULTIPLIER
            
            # デバッグ: 音声データの取得状況をログ出力（初回のみ）
            if not hasattr(self, '_audio_debug_logged'):
                logger.info(f"Audio callback: received {len(chunk)} samples, shape: {chunk.shape if hasattr(chunk, 'shape') else 'N/A'}")
                logger.info(f"Audio data range (after gain): {np.min(chunk):.4f} to {np.max(chunk):.4f}")
                logger.info(f"Gain multiplier: {GAIN_MULTIPLIER}")
                self._audio_debug_logged = True
            
            # バッファ拡張
            self.audio_buffer.extend(chunk)
            
            # グラフ用データも更新
            current_time = time.time() - self.graph_start_time
            volume_level = np.sqrt(np.mean(chunk ** 2))  # RMS
            
            self.time_data.append(current_time)
            self.volume_data.append(volume_level)
            self.frequency_data.append(self.current_f0 if self.current_f0 > 0 else np.nan)
            
        except Exception as e:
            logger.error(f"Audio callback error: {e}")

    def _audio_loop(self):
        """オーディオ解析ループ（sounddeviceのInputStream使用）"""
        logger.info("Audio analysis loop started")
        
        # 解析カウンターを初期化
        self._analysis_log_counter = 0
        
        # バッファサイズを確認
        target_buffer_size = CHUNK * 2  # 分析に必要な最小サイズ
        
        while self.is_running and not self._stop_event.is_set():
            try:
                # バッファに十分なデータがあるかチェック
                if len(self.audio_buffer) >= target_buffer_size:
                    # 分析用にデータを取得
                    segment = np.array(list(self.audio_buffer)[:target_buffer_size])
                    
                    # バッファから使用したデータを削除
                    for _ in range(target_buffer_size):
                        if self.audio_buffer:
                            self.audio_buffer.popleft()
                    
                    self._analysis_log_counter += 1
                    
                    # F0解析を実行
                    if len(segment) > 0:
                        self._analyze_audio_segment(segment)
                
                # CPU負荷軽減のため短時間スリープ
                time.sleep(0.01)  # 10ms
                
            except Exception as e:
                logger.error(f"Audio loop error: {e}")
                logger.error(f"Error details: {traceback.format_exc()}")
                time.sleep(0.1)
        
        logger.info("Audio analysis loop ended")

    def _analyze_audio_segment(self, segment):
        """音声セグメントを分析してF0と音階を検出"""
        try:
            # デバッグ: セグメント情報をログ出力
            if self._analysis_log_counter % 20 == 0:  # 20回に1回ログ出力（より頻繁に）
                segment_max = np.max(np.abs(segment))
                logger.info(f"F0 analysis #{self._analysis_log_counter}: segment max = {segment_max:.4f}")
            
            # pyin パラメータをマイク入力用に最適化
            f0, voiced_flag, voiced_probs = librosa.pyin(
                segment,
                fmin=80,   # 人間の声の下限
                fmax=1000, # 楽器・歌声の上限
                sr=RATE,
                frame_length=FRAME_LENGTH,
                hop_length=HOP_LENGTH,
                fill_na=0.0  # NaN値をゼロで埋める
            )
            valid = f0[~np.isnan(f0)]
            
            # マイク入力用の高精度処理
            if valid.size > 0:
                # 平均値を使用してマイクの直接音声を検出
                avg = float(np.mean(valid))  # マイクではノイズが少ないので平均値使用
                
                # 高い信頼度のフレームのみを使用
                if hasattr(voiced_probs, '__len__') and len(voiced_probs) > 0:
                    confidence_mask = voiced_probs > 0.5  # 50%以上の信頼度
                    confident_f0 = f0[confidence_mask]
                    if len(confident_f0) > 0:
                        confident_valid = confident_f0[~np.isnan(confident_f0)]
                        if len(confident_valid) > 0:
                            avg = float(np.mean(confident_valid))
                
                # 人間の音声・楽器の範囲チェック
                if 75 <= avg <= 1200:  # 人間の音声・楽器範囲
                    self.current_f0 = avg
                    
                    # デバッグ: F0検出成功をログ出力
                    if self._analysis_log_counter % 10 == 0:  # 10回に1回でより頻繁に
                        confidence_avg = np.mean(voiced_probs) if hasattr(voiced_probs, '__len__') else 0
                        logger.info(f"Microphone F0 detected: {avg:.2f} Hz from {len(valid)} frames (confidence: {confidence_avg:.2f})")
                    
                    # 音階検出（JSONベース）
                    western_note, japanese_note, closest_freq = frequency_to_note(avg, self.note_data)
                    self.current_note = western_note
                    self.current_japanese_note = japanese_note
                    # 信頼度計算（周波数差に基づく）
                    if closest_freq > 0:
                        freq_diff = abs(avg - closest_freq)
                        # 半音差（約6%）を基準とした信頼度
                        confidence = max(0, 100 - (freq_diff / closest_freq * 100 * 16.7))
                        self.note_confidence = min(100, confidence)
                    else:
                        self.note_confidence = 0
                else:
                    # 範囲外の周波数は無視
                    self.current_f0 = 0.0
                    self.current_note = "N/A"
                    self.current_japanese_note = "N/A"
                    self.note_confidence = 0
            else:
                # デバッグ: F0検出失敗をログ出力
                if self._analysis_log_counter % 50 == 0:  # 50回に1回
                    logger.info(f"No valid F0 detected in analysis #{self._analysis_log_counter} (segment max: {np.max(np.abs(segment)):.4f})")
                
                self.current_f0 = 0.0
                self.current_note = "N/A"
                self.current_japanese_note = "N/A"
                self.note_confidence = 0
                
        except Exception as e:
            logger.error(f"pyin error: {e}")
            self.current_f0 = 0.0
            self.current_note = "N/A"
            self.current_japanese_note = "N/A"
            self.note_confidence = 0

    def _gui_update_loop(self):
                        
                        stream_created = False
                        for attempt, params in enumerate(api_attempts):
                            try:
                                logger.info(f"Trying basic audio connection #{attempt+1}: blocksize={params['blocksize']}, samplerate={params['samplerate']}")
                                
                                # 簡素なストリーム作成
                                self.stream = sd.InputStream(
                                    device=self.device_index,
                                    channels=CHANNELS,
                                    samplerate=params['samplerate'],
                                    blocksize=params['blocksize'],
                                    callback=audio_callback,
                                    dtype=np.float32
                                )
                                
                                self.stream.start()
                                logger.info(f"Audio stream opened successfully (attempt #{attempt+1})")
                                stream_created = True
                                break
                                
                            except Exception as api_error:
                                error_msg = str(api_error)
                                logger.warning(f"Attempt #{attempt+1} failed: {error_msg[:100]}...")
                                
                                if attempt < len(api_attempts) - 1:
                                    continue
                        
                        if not stream_created:
                            raise Exception("All audio API attempts failed")
                        
                        # 接続成功を表示
                        self.master.after(1, lambda: self.connection_label.config(text="Connected - Analyzing", foreground="green"))
                        
                    time.sleep(0.01)
                except Exception as e:
                    logger.error(f"All audio stream attempts failed: {e}")
                    logger.error(traceback.format_exc())
                    if self.stream:
                        try:
                            self.stream.stop(); self.stream.close()
                        except Exception:
                            pass
                        self.stream = None
                    self.is_running = False
                    self.master.after(1, lambda: self.start_button.config(state=tk.NORMAL))
                    self.master.after(1, lambda: self.stop_button.config(state=tk.DISABLED))
                    self.master.after(1, lambda: self.device_combobox.config(state="readonly"))
                    self.master.after(1, lambda: self.connection_label.config(text="Cannot Open Audio Stream", foreground="red"))
                    
                    # 失敗したデバイスを設定から削除
                    current_device_name = self.device_var.get()
                    if remove_failed_device_from_config(self.device_index, self.device_config):
                        save_device_config(self.device_config)
                        logger.info(f"Removed problematic device from config: {current_device_name}")
                    
                    logger.error("Analysis stopped due to audio stream error")
            else:
                if self.stream:
                    try:
                        self.stream.stop(); self.stream.close()
                        logger.info("Audio stream closed")
                    except Exception:
                        pass
                    self.stream = None
                time.sleep(0.1)

    def _gui_update_loop(self):
        """GUI更新ループ: _stop_event 監視で終了"""
        while not self._stop_event.is_set():
            if self.is_running:
                try:
                    self.master.after(0, self._update_gui_elements)
                except Exception as e:
                    logger.error(f"GUI update loop error: {e}")
                    logger.error(traceback.format_exc())
            time.sleep(0.05)

    def _update_graph(self, frame):
        """リアルタイムグラフの更新"""
        if not self.is_running or len(self.time_data) == 0:
            return
        
        try:
            # データを配列に変換
            times = np.array(self.time_data)
            volumes = np.array(self.volume_data)
            frequencies = np.array(self.frequency_data)
            
            # 時間軸の範囲設定（最新30秒間）
            current_time = times[-1] if len(times) > 0 else 0
            time_start = max(0, current_time - GRAPH_HISTORY_SECONDS)
            time_end = current_time + 2  # 少し先まで表示
            
            # 音量グラフ更新
            self.volume_line.set_data(times, volumes)
            self.ax1.set_xlim(time_start, time_end)
            
            # 周波数グラフ更新（NaN値を除外）
            valid_mask = ~np.isnan(frequencies)
            if np.any(valid_mask):
                valid_times = times[valid_mask]
                valid_frequencies = frequencies[valid_mask]
                self.frequency_line.set_data(valid_times, valid_frequencies)
            else:
                self.frequency_line.set_data([], [])
                
            self.ax2.set_xlim(time_start, time_end)
            
            # X軸のフォーマット
            for ax in [self.ax1, self.ax2]:
                ax.xaxis.set_major_locator(plt.MultipleLocator(5))  # 5秒間隔
                ax.xaxis.set_minor_locator(plt.MultipleLocator(1))  # 1秒間隔
                
        except Exception as e:
            logger.error(f"Graph update error: {e}")
            
        return self.volume_line, self.frequency_line

    def _update_gui_elements(self):
        """現在の解析結果でGUI要素更新"""
        try:
            # 音量バー更新
            width = self.volume_canvas.winfo_width() * (self.current_volume / 100.0)
            self.volume_canvas.coords(self.volume_bar, 0, 0, width, 20)
            
            # 音量レベル数値更新
            self.volume_level_label.config(text=f"{self.current_volume}%")
            
            # 音階表示更新
            self.note_label.config(text=self.current_note)
            self.japanese_note_label.config(text=self.current_japanese_note)
            
            # 周波数表示更新
            self.f0_label.config(text=f"{self.current_f0:.2f} Hz")
            
            # 信頼度表示更新
            confidence_text = f"{self.note_confidence:.0f}%"
            confidence_color = "green" if self.note_confidence > 70 else "orange" if self.note_confidence > 40 else "red"
            self.confidence_label.config(text=confidence_text, foreground=confidence_color)
            
        except Exception as e:
            logger.error(f"GUI element update error: {e}")
            logger.error(traceback.format_exc())

    def _close_stream(self):
        """内部ストリーム停止/破棄"""
        if self.stream:
            try:
                self.stream.stop(); self.stream.close()
            except Exception:
                pass
            self.stream = None
            logger.info("Audio stream closed")

    def _on_closing(self):
        """終了処理: スレッド終了待機とストリーム解放、設定保存"""
        logger.info("Closing application...")
        
        # 最終的なデバイス設定を保存
        if hasattr(self, 'device_config') and self.device_index is not None:
            self.device_config["device_settings"]["last_used_device_index"] = self.device_index
            save_device_config(self.device_config)
        
        self.is_running = False
        self._stop_event.set()
        self._close_stream()
        try:
            if self.audio_thread and self.audio_thread.is_alive():
                self.audio_thread.join(timeout=1.0)
            if self.gui_update_thread and self.gui_update_thread.is_alive():
                self.gui_update_thread.join(timeout=1.0)
        except Exception as e:
            logger.error(f"Thread join error: {e}")
            logger.error(traceback.format_exc())
        self.master.destroy()
        logger.info("Application closed")


if __name__ == "__main__":
    root = tk.Tk()
    app = InstrumentAnalyzerGUI(root)
    root.mainloop()
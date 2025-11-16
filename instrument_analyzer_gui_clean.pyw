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

__version__ = "1.0.0"

# --- ログ設定 ---
LOG_DIR = "logs"
if not os.path.exists(LOG_DIR):
    os.makedirs(LOG_DIR)

timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = os.path.join(LOG_DIR, f"app_{timestamp}.log")

def setup_logger():
    """ログ設定を初期化"""
    logger = logging.getLogger("InstrumentAnalyzer")
    logger.setLevel(logging.DEBUG)
    formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', '%Y-%m-%d %H:%M:%S')
    
    file_handler = logging.FileHandler(LOG_FILE, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
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
        # デフォルトデータを返す
        return {
            "note_frequencies": {
                "C4": {"frequency": 261.63, "western": "C4", "japanese": "ド"},
                "D4": {"frequency": 293.66, "western": "D4", "japanese": "レ"},
                "E4": {"frequency": 329.63, "western": "E4", "japanese": "ミ"},
                "F4": {"frequency": 349.23, "western": "F4", "japanese": "ファ"},
                "G4": {"frequency": 392.00, "western": "G4", "japanese": "ソ"},
                "A4": {"frequency": 440.00, "western": "A4", "japanese": "ラ"},
                "B4": {"frequency": 493.88, "western": "B4", "japanese": "シ"}
            }
        }

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
            }
        }

def save_device_config(config):
    """デバイス設定をJSONファイルに保存"""
    try:
        with open('device_config.json', 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        logger.info("Device configuration saved")
    except Exception as e:
        logger.error(f"Failed to save device config: {e}")

# --- 設定パラメータ ---
CHUNK = 1024        # 1ブロック当たりのサンプル数
CHANNELS = 1        # モノラル
RATE = 44100        # サンプリングレート (Hz)
FRAME_LENGTH = CHUNK * 2  # pyin用フレーム長
HOP_LENGTH = CHUNK        # フレーム進行量
GAIN_MULTIPLIER = 10.0    # マイク感度増幅係数

# グラフ用設定
GRAPH_HISTORY_SECONDS = 30  # 30秒間の履歴を表示
GRAPH_UPDATE_INTERVAL = 100  # 100ms毎にグラフ更新

class InstrumentAnalyzerGUI:
    """USB接続楽器/マイク入力を解析しGUI表示するクラス"""
    
    def __init__(self, master, device_index=None):
        """初期化"""
        self.master = master
        self.master.title("Instrument Analyzer GUI")
        self.master.geometry("600x500")
        self.master.protocol("WM_DELETE_WINDOW", self._on_closing)

        # 音声処理関連
        self.device_index = device_index
        self.stream = None
        self.is_running = False
        self._stop_event = threading.Event()
        
        # 解析結果
        self.current_f0 = 0.0
        self.current_note = "N/A"
        self.current_japanese_note = "N/A"
        self.current_volume = 0
        self.note_confidence = 0.0
        
        # 音階データ読み込み
        self.note_data = load_note_frequencies()
        
        # デバイス設定読み込み
        self.device_config = load_device_config()

        # オーディオバッファ
        self.audio_buffer = deque(maxlen=CHUNK * 10)
        
        # グラフ用データ
        self.time_data = deque(maxlen=int(GRAPH_HISTORY_SECONDS * RATE / CHUNK))
        self.volume_data = deque(maxlen=int(GRAPH_HISTORY_SECONDS * RATE / CHUNK))
        self.frequency_data = deque(maxlen=int(GRAPH_HISTORY_SECONDS * RATE / CHUNK))
        self.graph_start_time = time.time()

        # スレッド
        self.audio_thread = None
        self.gui_update_thread = None

        self._setup_gui()
        self._populate_devices()
        logger.info("InstrumentAnalyzerGUI initialized successfully")

    def _setup_gui(self):
        """GUI要素を配置"""
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
        self.device_combobox = ttk.Combobox(control_frame, textvariable=self.device_var, 
                                           state="readonly", width=40)
        self.device_combobox.grid(row=0, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        self.device_combobox.bind("<<ComboboxSelected>>", self._on_device_selected)
        
        # 開始/停止ボタン
        self.start_button = ttk.Button(control_frame, text="Start Analysis", 
                                      command=self.start_analysis)
        self.start_button.grid(row=1, column=0, pady=10, sticky=tk.W)
        
        self.stop_button = ttk.Button(control_frame, text="Stop Analysis", 
                                     command=self.stop_analysis, state=tk.DISABLED)
        self.stop_button.grid(row=1, column=1, pady=10, sticky=tk.W)
        
        # 接続ステータス
        ttk.Label(control_frame, text="Status:").grid(row=1, column=2, sticky=tk.E, padx=(20, 5))
        self.connection_label = ttk.Label(control_frame, text="Ready", 
                                         font=("Helvetica", 10), foreground="blue")
        self.connection_label.grid(row=1, column=3, sticky=tk.W, pady=10)
        
        # 音量メーター
        ttk.Label(control_frame, text="Volume:").grid(row=2, column=0, sticky=tk.W, pady=5)
        
        volume_frame = ttk.Frame(control_frame)
        volume_frame.grid(row=2, column=1, columnspan=2, sticky=(tk.W, tk.E), pady=5)
        
        self.volume_canvas = tk.Canvas(volume_frame, width=200, height=20, 
                                      bg="lightgray", bd=1, relief="sunken")
        self.volume_canvas.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.volume_bar = self.volume_canvas.create_rectangle(0, 0, 0, 20, fill="green")
        
        self.volume_level_label = ttk.Label(volume_frame, text="0%", 
                                           font=("Helvetica", 10), width=5)
        self.volume_level_label.pack(side=tk.RIGHT, padx=(5, 0))
        
        # 検出された音階 (Western)
        ttk.Label(control_frame, text="Note (Western):").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.note_label = ttk.Label(control_frame, text="N/A", 
                                   font=("Helvetica", 16, "bold"), foreground="blue")
        self.note_label.grid(row=3, column=1, sticky=tk.W, pady=5)
        
        # 検出された音階 (Japanese)
        ttk.Label(control_frame, text="Note (Japanese):").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.japanese_note_label = ttk.Label(control_frame, text="N/A", 
                                            font=("Helvetica", 16, "bold"), foreground="red")
        self.japanese_note_label.grid(row=4, column=1, sticky=tk.W, pady=5)
        
        # 周波数表示
        ttk.Label(control_frame, text="Frequency:").grid(row=5, column=0, sticky=tk.W, pady=5)
        self.f0_label = ttk.Label(control_frame, text="0.00 Hz", font=("Helvetica", 14))
        self.f0_label.grid(row=5, column=1, sticky=tk.W, pady=5)
        
        # 信頼度表示
        ttk.Label(control_frame, text="Confidence:").grid(row=6, column=0, sticky=tk.W, pady=5)
        self.confidence_label = ttk.Label(control_frame, text="0%", font=("Helvetica", 12))
        self.confidence_label.grid(row=6, column=1, sticky=tk.W, pady=5)
        
        # グリッド設定
        control_frame.columnconfigure(1, weight=1)
        
        # === グラフ部分の設定 ===
        self._setup_graph(graph_frame)

    def _setup_graph(self, parent_frame):
        """リアルタイムグラフの設定"""
        ttk.Label(parent_frame, text="Real-time Audio Analysis", 
                 font=("Helvetica", 12, "bold")).pack(pady=(0, 5))
        
        # matplotlib図の作成
        self.fig, (self.ax1, self.ax2) = plt.subplots(2, 1, figsize=(8, 5))
        self.fig.tight_layout(pad=3.0)
        
        # 音量グラフ設定
        self.ax1.set_title('Volume Level (%)', fontsize=10)
        self.ax1.set_ylabel('Volume (%)')
        self.ax1.set_ylim(0, 100)
        self.ax1.grid(True, alpha=0.3)
        self.volume_line, = self.ax1.plot([], [], 'g-', linewidth=2)
        
        # 周波数グラフ設定
        self.ax2.set_title('Detected Frequency (Hz)', fontsize=10)
        self.ax2.set_xlabel('Time (seconds)')
        self.ax2.set_ylabel('Frequency (Hz)')
        self.ax2.set_ylim(80, 1000)
        self.ax2.grid(True, alpha=0.3)
        self.frequency_line, = self.ax2.plot([], [], 'b-', linewidth=2)
        
        # TkinterにmatplotlibのグラフをEmbed
        self.canvas = FigureCanvasTkAgg(self.fig, parent_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
        # グラフ更新用アニメーション
        self.animation = None

    def _populate_devices(self):
        """デバイスリストを取得してComboBoxに設定"""
        try:
            devices_info = sd.query_devices()
            devices = []
            device_map = {}
            
            logger.info("Scanning for audio input devices...")
            
            for idx, dev in enumerate(devices_info):
                if dev.get('max_input_channels', 0) > 0:
                    device_name = dev['name']
                    display_name = f"{device_name} (Index: {idx})"
                    devices.append(display_name)
                    device_map[display_name] = idx
                    logger.info(f"Found input device: {device_name} (Index: {idx})")
            
            self.device_combobox['values'] = devices
            self.device_map = device_map
            
            # デフォルトデバイスの選択
            if devices:
                # 最後に使用したデバイスがあれば選択
                last_device_idx = self.device_config["device_settings"].get("last_used_device_index")
                selected_device = None
                
                if last_device_idx is not None:
                    for display_name, idx in device_map.items():
                        if idx == last_device_idx:
                            selected_device = display_name
                            break
                
                # なければ最初のデバイスを選択
                if selected_device is None:
                    selected_device = devices[0]
                
                self.device_var.set(selected_device)
                self.device_index = device_map[selected_device]
                logger.info(f"Selected device: {selected_device}")
            else:
                self.connection_label.config(text="No input devices found", foreground="red")
                logger.warning("No input devices found")
                
        except Exception as e:
            logger.error(f"Device enumeration error: {e}")
            logger.error(traceback.format_exc())
            self.connection_label.config(text="Device scan failed", foreground="red")

    def _on_device_selected(self, event=None):
        """デバイス選択変更時の処理"""
        device_name = self.device_var.get()
        self.device_index = self.device_map.get(device_name)
        
        if self.device_index is not None:
            # 設定保存
            self.device_config["device_settings"]["last_used_device_index"] = self.device_index
            self.device_config["device_settings"]["last_used_device_name"] = device_name
            save_device_config(self.device_config)
            
            self.connection_label.config(text="Ready", foreground="blue")
            logger.info(f"Device selected: {device_name} (Index: {self.device_index})")
        else:
            self.connection_label.config(text="Invalid device", foreground="red")

    def start_analysis(self):
        """解析開始"""
        if self.is_running or self.device_index is None:
            return
            
        logger.info(f"Starting analysis for device index: {self.device_index}")
        
        try:
            # オーディオストリーム開始
            self.stream = sd.InputStream(
                device=self.device_index,
                channels=CHANNELS,
                samplerate=RATE,
                dtype=np.float32,
                blocksize=CHUNK,
                callback=self.audio_callback
            )
            self.stream.start()
            
            self.is_running = True
            self._stop_event.clear()
            
            # UI更新
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.device_combobox.config(state=tk.DISABLED)
            self.connection_label.config(text="Analyzing...", foreground="green")
            
            # データリセット
            self.audio_buffer.clear()
            self.time_data.clear()
            self.volume_data.clear()
            self.frequency_data.clear()
            self.graph_start_time = time.time()
            
            # スレッド開始
            self.audio_thread = threading.Thread(target=self._audio_loop, daemon=True)
            self.gui_update_thread = threading.Thread(target=self._gui_update_loop, daemon=True)
            
            self.audio_thread.start()
            self.gui_update_thread.start()
            
            # グラフアニメーション開始
            if self.animation is None:
                self.animation = FuncAnimation(self.fig, self._update_graph, 
                                             interval=GRAPH_UPDATE_INTERVAL, blit=False)
                self.canvas.draw()
            
            logger.info("Analysis started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start analysis: {e}")
            logger.error(traceback.format_exc())
            
            # UI状態リセット
            self.is_running = False
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            self.device_combobox.config(state="readonly")
            self.connection_label.config(text="Start failed", foreground="red")
            
            messagebox.showerror("Error", f"Failed to start audio analysis:\n{str(e)}")

    def stop_analysis(self):
        """解析停止"""
        if not self.is_running:
            return
            
        logger.info("Stopping analysis...")
        
        self.is_running = False
        self._stop_event.set()
        
        # ストリーム停止
        if self.stream:
            try:
                self.stream.stop()
                self.stream.close()
                self.stream = None
            except Exception as e:
                logger.error(f"Error stopping stream: {e}")
        
        # UI更新
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.device_combobox.config(state="readonly")
        self.connection_label.config(text="Stopped", foreground="blue")
        
        # グラフアニメーション停止
        if self.animation:
            self.animation.event_source.stop()
            self.animation = None
        
        logger.info("Analysis stopped")

    def audio_callback(self, indata, frames, time_info, status):
        """オーディオコールバック（sounddevice InputStream用）"""
        if status:
            logger.warning(f"Audio callback status: {status}")
        
        try:
            # モノラルデータに変換
            if indata.ndim > 1:
                audio_data = indata[:, 0]
            else:
                audio_data = indata.flatten()
            
            # 感度増幅
            audio_data = audio_data * GAIN_MULTIPLIER
            
            # バッファに追加
            self.audio_buffer.extend(audio_data)
            
            # 音量計算（RMS）
            volume = np.sqrt(np.mean(audio_data ** 2))
            self.current_volume = min(100, int(volume * 100))
            
        except Exception as e:
            logger.error(f"Audio callback error: {e}")

    def _audio_loop(self):
        """オーディオ解析ループ"""
        logger.info("Audio analysis loop started")
        
        while self.is_running and not self._stop_event.is_set():
            try:
                # バッファから分析用データを取得
                if len(self.audio_buffer) >= FRAME_LENGTH:
                    # 分析用データを取得
                    segment = np.array(list(self.audio_buffer)[:FRAME_LENGTH])
                    
                    # バッファクリア（重複を避ける）
                    for _ in range(min(len(self.audio_buffer), CHUNK)):
                        if self.audio_buffer:
                            self.audio_buffer.popleft()
                    
                    # 周波数解析
                    self._analyze_audio_segment(segment)
                    
                    # グラフデータ更新
                    current_time = time.time() - self.graph_start_time
                    self.time_data.append(current_time)
                    self.volume_data.append(self.current_volume)
                    self.frequency_data.append(self.current_f0 if self.current_f0 > 0 else np.nan)
                
                time.sleep(0.01)  # CPU負荷軽減
                
            except Exception as e:
                logger.error(f"Audio loop error: {e}")
                time.sleep(0.1)
        
        logger.info("Audio analysis loop ended")

    def _analyze_audio_segment(self, segment):
        """音声セグメントを分析してF0と音階を検出"""
        try:
            # pyin を使用してF0検出
            f0, voiced_flag, voiced_probs = librosa.pyin(
                segment,
                fmin=80,   # 低い音の下限
                fmax=1000, # 高い音の上限
                sr=RATE,
                frame_length=FRAME_LENGTH,
                hop_length=HOP_LENGTH,
                fill_na=0.0
            )
            
            # 有効なF0値の抽出
            valid_f0 = f0[~np.isnan(f0)]
            
            if len(valid_f0) > 0 and hasattr(voiced_probs, '__len__'):
                # 信頼度の高いフレームのみ使用
                confidence_mask = voiced_probs > 0.5
                confident_f0 = f0[confidence_mask]
                confident_valid = confident_f0[~np.isnan(confident_f0)]
                
                if len(confident_valid) > 0:
                    # 中央値を使用（ノイズに強い）
                    detected_f0 = float(np.median(confident_valid))
                    
                    # 人間の音声・楽器範囲チェック
                    if 75 <= detected_f0 <= 1200:
                        self.current_f0 = detected_f0
                        
                        # 音階検出
                        western_note, japanese_note, closest_freq = frequency_to_note(
                            detected_f0, self.note_data)
                        self.current_note = western_note
                        self.current_japanese_note = japanese_note
                        
                        # 信頼度計算
                        if closest_freq > 0:
                            freq_diff = abs(detected_f0 - closest_freq)
                            confidence = max(0, 100 - (freq_diff / closest_freq * 100 * 10))
                            self.note_confidence = min(100, confidence)
                        else:
                            self.note_confidence = 0
                    else:
                        # 範囲外の周波数
                        self.current_f0 = 0.0
                        self.current_note = "N/A"
                        self.current_japanese_note = "N/A"
                        self.note_confidence = 0
                else:
                    # 信頼度の高いフレームがない
                    self.current_f0 = 0.0
                    self.current_note = "N/A"
                    self.current_japanese_note = "N/A"
                    self.note_confidence = 0
            else:
                # 有効なF0が検出されない
                self.current_f0 = 0.0
                self.current_note = "N/A"
                self.current_japanese_note = "N/A"
                self.note_confidence = 0
                
        except Exception as e:
            logger.error(f"Audio analysis error: {e}")
            self.current_f0 = 0.0
            self.current_note = "N/A"
            self.current_japanese_note = "N/A"
            self.note_confidence = 0

    def _gui_update_loop(self):
        """GUI更新ループ"""
        while not self._stop_event.is_set():
            if self.is_running:
                try:
                    # GUI要素の更新をメインスレッドで実行
                    self.master.after(0, self._update_gui_elements)
                except Exception as e:
                    logger.error(f"GUI update error: {e}")
            time.sleep(0.05)  # 20Hz更新

    def _update_gui_elements(self):
        """GUI要素の更新"""
        try:
            # 音量バー更新
            if hasattr(self, 'volume_canvas') and self.volume_canvas.winfo_exists():
                width = self.volume_canvas.winfo_width() * (self.current_volume / 100.0)
                self.volume_canvas.coords(self.volume_bar, 0, 0, width, 20)
            
            # ラベル更新
            self.volume_level_label.config(text=f"{self.current_volume}%")
            self.note_label.config(text=self.current_note)
            self.japanese_note_label.config(text=self.current_japanese_note)
            self.f0_label.config(text=f"{self.current_f0:.2f} Hz")
            
            # 信頼度表示
            confidence_text = f"{self.note_confidence:.0f}%"
            if self.note_confidence > 70:
                confidence_color = "green"
            elif self.note_confidence > 40:
                confidence_color = "orange"
            else:
                confidence_color = "red"
            self.confidence_label.config(text=confidence_text, foreground=confidence_color)
            
        except Exception as e:
            logger.error(f"GUI element update error: {e}")

    def _update_graph(self, frame):
        """リアルタイムグラフの更新"""
        if not self.is_running or len(self.time_data) == 0:
            return self.volume_line, self.frequency_line
        
        try:
            # データを配列に変換
            times = np.array(list(self.time_data))
            volumes = np.array(list(self.volume_data))
            frequencies = np.array(list(self.frequency_data))
            
            # 時間軸の範囲設定
            if len(times) > 0:
                current_time = times[-1]
                time_start = max(0, current_time - GRAPH_HISTORY_SECONDS)
                time_end = current_time + 2
                
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
                
        except Exception as e:
            logger.error(f"Graph update error: {e}")
            
        return self.volume_line, self.frequency_line

    def _on_closing(self):
        """アプリケーション終了処理"""
        logger.info("Closing application...")
        
        # 解析停止
        self.stop_analysis()
        
        # スレッド終了待機
        try:
            if self.audio_thread and self.audio_thread.is_alive():
                self.audio_thread.join(timeout=1.0)
            if self.gui_update_thread and self.gui_update_thread.is_alive():
                self.gui_update_thread.join(timeout=1.0)
        except Exception as e:
            logger.error(f"Thread join error: {e}")
        
        # 設定保存
        if hasattr(self, 'device_config') and self.device_index is not None:
            self.device_config["device_settings"]["last_used_device_index"] = self.device_index
            save_device_config(self.device_config)
        
        self.master.destroy()
        logger.info("Application closed successfully")


if __name__ == "__main__":
    root = tk.Tk()
    app = InstrumentAnalyzerGUI(root)
    root.mainloop()
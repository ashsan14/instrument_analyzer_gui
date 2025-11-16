import pyaudio
import numpy as np
import librosa
import tkinter as tk
from tkinter import ttk
import threading
import time

__version__ = "0.1.0"

# --- 設定パラメータ ---
CHUNK = 1024        # 一度に処理するサンプル数
FORMAT = pyaudio.paInt16 # データ形式（16bit整数）
CHANNELS = 1        # モノラル
RATE = 44100        # サンプリングレート (Hz)

class InstrumentAnalyzerGUI:
    """
    USB接続された楽器からの音響入力を処理し、
    リアルタイムで解析結果をtkinter GUIに表示するクラス。
    """
    
    def __init__(self, master, device_index=None):
        self.master = master
        self.master.title("USB Instrument Analyzer")
        self.master.geometry("400x300")
        self.master.protocol("WM_DELETE_WINDOW", self._on_closing) # ウィンドウクローズ処理

        self.p = pyaudio.PyAudio()
        self.device_index = device_index
        self.stream = None
        self.is_running = False
        
        self.current_f0 = 0.0
        self.current_note = "N/A"
        self.current_volume = 0 # 0-100%

        # --- GUI要素のセットアップ ---
        self._setup_gui()
        
        # オーディオ処理を別スレッドで実行
        self.audio_thread = threading.Thread(target=self._audio_loop)
        self.audio_thread.daemon = True # メインスレッド終了時に一緒に終了
        
        # GUI更新を別スレッドで実行
        self.gui_update_thread = threading.Thread(target=self._gui_update_loop)
        self.gui_update_thread.daemon = True

    def _setup_gui(self):
        # フレーム
        main_frame = ttk.Frame(self.master, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)

        # デバイス選択
        ttk.Label(main_frame, text="Input Device:").grid(row=0, column=0, sticky=tk.W, pady=5)
        self.device_var = tk.StringVar()
        self.device_combobox = ttk.Combobox(main_frame, textvariable=self.device_var, state="readonly", width=30)
        self.device_combobox.grid(row=0, column=1, sticky=(tk.W, tk.E), pady=5)
        self.device_combobox.bind("<<ComboboxSelected>>", self._on_device_selected)
        self._populate_devices()

        # 開始/停止ボタン
        self.start_button = ttk.Button(main_frame, text="Start Analysis", command=self.start_analysis)
        self.start_button.grid(row=1, column=0, pady=10, sticky=tk.W)
        self.stop_button = ttk.Button(main_frame, text="Stop Analysis", command=self.stop_analysis, state=tk.DISABLED)
        self.stop_button.grid(row=1, column=1, pady=10, sticky=tk.E)

        # 音量メーター
        ttk.Label(main_frame, text="Volume:").grid(row=2, column=0, sticky=tk.W, pady=5)
        self.volume_canvas = tk.Canvas(main_frame, width=200, height=20, bg="lightgray", bd=1, relief="sunken")
        self.volume_canvas.grid(row=2, column=1, sticky=(tk.W, tk.E), pady=5)
        self.volume_bar = self.volume_canvas.create_rectangle(0, 0, 0, 20, fill="green")
        
        # 音高表示
        ttk.Label(main_frame, text="Detected Note:").grid(row=3, column=0, sticky=tk.W, pady=5)
        self.note_label = ttk.Label(main_frame, text="N/A", font=("Helvetica", 18, "bold"), foreground="blue")
        self.note_label.grid(row=3, column=1, sticky=(tk.W, tk.E), pady=5)

        ttk.Label(main_frame, text="Frequency (F0):").grid(row=4, column=0, sticky=tk.W, pady=5)
        self.f0_label = ttk.Label(main_frame, text="0.00 Hz", font=("Helvetica", 14))
        self.f0_label.grid(row=4, column=1, sticky=(tk.W, tk.E), pady=5)

        # グリッドレイアウトの設定
        main_frame.columnconfigure(1, weight=1)

    def _populate_devices(self):
        """利用可能な入力デバイスをComboBoxに表示します。"""
        devices = []
        device_map = {}
        info = self.p.get_host_api_info_by_index(0)
        numdevices = info.get('deviceCount')
        for i in range(0, numdevices):
            if (self.p.get_device_info_by_host_api_device_index(0, i).get('maxInputChannels')) > 0:
                dev_info = self.p.get_device_info_by_host_api_device_index(0, i)
                device_name = f"{dev_info.get('name')} (Index: {i})"
                devices.append(device_name)
                device_map[device_name] = i
        self.device_combobox['values'] = devices
        self.device_map = device_map # 名前とインデックスのマッピングを保存

        if self.device_index is not None:
            # 指定されたデバイスがあれば選択
            for name, idx in device_map.items():
                if idx == self.device_index:
                    self.device_var.set(name)
                    break
        elif devices:
            # デフォルトで最初のデバイスを選択
            self.device_var.set(devices[0])
            self.device_index = device_map[devices[0]]

    def _on_device_selected(self, event=None):
        """ComboBoxでデバイスが選択されたときに呼ばれます。"""
        selected_name = self.device_var.get()
        self.device_index = self.device_map.get(selected_name)
        print(f"Selected Device: {selected_name}, Index: {self.device_index}")

    def start_analysis(self):
        if self.is_running:
            return

        if self.device_index is None:
            print("Please select an input device first.")
            return

        self.is_running = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.device_combobox.config(state=tk.DISABLED) # 解析中はデバイス変更不可
        
        # スレッドが開始されていない場合のみ開始
        if not self.audio_thread.is_alive():
            self.audio_thread.start()
        if not self.gui_update_thread.is_alive():
            self.gui_update_thread.start()
        
        print("--- Analysis Started ---")

    def stop_analysis(self):
        if not self.is_running:
            return

        self.is_running = False
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.device_combobox.config(state="readonly") # 解析停止後はデバイス変更可能
        
        print("--- Analysis Stopped ---")

    def _audio_loop(self):
        """
        オーディオ入力と解析を別スレッドで実行するメインループ。
        """
        while True: # プログラム終了までスレッドを維持
            if self.is_running:
                try:
                    # ストリームが開始されていない場合のみ開始
                    if self.stream is None or not self.stream.is_active():
                        self.stream = self.p.open(format=FORMAT,
                                                channels=CHANNELS,
                                                rate=RATE,
                                                input=True,
                                                frames_per_buffer=CHUNK,
                                                input_device_index=self.device_index)
                        print(f"Audio stream opened on device index {self.device_index}")

                    # オーディオデータを読み込み
                    in_data = self.stream.read(CHUNK, exception_on_overflow=False)
                    audio_data = np.frombuffer(in_data, dtype=np.int16).astype(np.float32)
                    audio_data /= np.iinfo(np.int16).max # 正規化

                    # --- 解析 ---
                    # 音量（RMS値）
                    rms = np.sqrt(np.mean(audio_data**2))
                    self.current_volume = int(min(rms * 200, 100)) # 0-100%にマッピング

                    # 基本周波数 (F0) とノート名
                    f0, _, _ = librosa.pyin(audio_data, 
                                            fmin=librosa.note_to_hz('C2'), 
                                            fmax=librosa.note_to_hz('C7'), 
                                            sr=RATE, 
                                            frame_length=CHUNK*2) # pyinは長めのフレームが好ましい
                    
                    valid_f0 = f0[~np.isnan(f0)]
                    if valid_f0.size > 0:
                        average_f0 = np.mean(valid_f0)
                        self.current_f0 = average_f0
                        self.current_note = librosa.hz_to_note(average_f0, cents=True) # セント値も表示
                    else:
                        self.current_f0 = 0.0
                        self.current_note = "N/A"
                        
                except Exception as e:
                    print(f"Audio Processing Error: {e}")
                    self.current_f0 = 0.0
                    self.current_note = "N/A"
                    self.current_volume = 0
                    # エラーが発生したらストリームを停止して再試行可能にする
                    self._close_stream()
                    self.is_running = False
                    self.master.after(1, lambda: self.start_button.config(state=tk.NORMAL)) # GUIスレッドでボタン状態を更新
                    self.master.after(1, lambda: self.stop_button.config(state=tk.DISABLED))
                    self.master.after(1, lambda: self.device_combobox.config(state="readonly"))
                    print("Analysis stopped due to an error.")

            else: # is_running が False の場合
                if self.stream and self.stream.is_active():
                    self._close_stream()
                time.sleep(0.1) # スレッドがCPUを食いつぶさないように待機
            
            time.sleep(0.01) # 解析間隔

    def _gui_update_loop(self):
        """
        GUI要素を定期的に更新するループ。メインスレッドから安全に呼び出される。
        """
        while True:
            if self.is_running:
                self.master.after(0, self._update_gui_elements) # メインスレッドでGUI更新
            time.sleep(0.05) # GUI更新頻度

    def _update_gui_elements(self):
        """
        GUIの表示要素を更新します。
        """
        # 音量メーター更新
        bar_width = self.volume_canvas.winfo_width() * (self.current_volume / 100.0)
        self.volume_canvas.coords(self.volume_bar, 0, 0, bar_width, 20)
        
        # 音高と周波数更新
        self.note_label.config(text=self.current_note)
        self.f0_label.config(text=f"{self.current_f0:.2f} Hz")

    def _close_stream(self):
        """
        オーディオストリームを停止し、クローズします。
        """
        if self.stream:
            if self.stream.is_active():
                self.stream.stop_stream()
            self.stream.close()
            self.stream = None
            print("Audio stream closed.")

    def _on_closing(self):
        """
        ウィンドウが閉じられるときの処理。
        """
        print("Closing application...")
        self.is_running = False # オーディオスレッドに停止を指示
        self._close_stream() # ストリームを閉じる
        self.p.terminate() # PyAudioを終了
        self.master.destroy() # Tkinterウィンドウを破壊


if __name__ == "__main__":
    root = tk.Tk()
    app = InstrumentAnalyzerGUI(root)
    root.mainloop()
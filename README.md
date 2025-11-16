# Instrument Analyzer GUI

軽量なリアルタイム音響解析 GUI（tkinter）です。

主な機能
- USB 接続やマイクからの音声入力から音量（RMS）と基本周波数（F0）を推定して表示
- 検出ノート（ノート名とセント）を表示
- デバイス選択、開始/停止コントロール

依存関係
- Python 3.8+
- See `requirements.txt`

実行（Windows / PowerShell）
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install -r requirements.txt
pip install pipwin
pipwin install pyaudio
python instrument_analyzer_gui.pyw
```

ライセンス
- このリポジトリには `LICENSE` ファイルが含まれます。必要に応じて著作権者名と年を LICENSE 内で更新してください。

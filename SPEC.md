# Instrument Analyzer GUI — 仕様書

**概要**

- プロジェクト名: Instrument Analyzer GUI
- ファイル: `instrument_analyzer_gui.pyw`
- 目的: USB 接続の楽器（またはマイク）からのオーディオ入力を受け取り、リアルタイムで音量（RMS）、基本周波数（F0）および推定ノート名を表示するデスクトップ GUI アプリケーション。
- 実装言語: Python 3.x
- GUI: `tkinter`（`ttk` を利用）
- オーディオ入力: `PyAudio`
- ピッチ検出: `librosa.pyin`

**機能一覧**

- 入力デバイスの列挙と選択（ComboBox）
- 開始/停止ボタンでリアルタイム解析の制御
- 音量メーター（RMS を 0-100% にスケール）
- 検出ノート表示（ノート名とセント表記）
- 検出周波数（Hz）表示
- スレッド分離: オーディオ処理スレッドと GUI 更新スレッド

**アーキテクチャ / データフロー**

- アプリ起動 → `InstrumentAnalyzerGUI` インスタンス生成 → GUI 描画
- デバイス一覧を取得して `ComboBox` に表示
- ユーザーが Start を押すと `is_running=True`、オーディオスレッドと GUI 更新スレッド（daemon）を開始
- オーディオスレッドのループ:
  - PyAudio ストリームを開き `CHUNK` サンプルずつ読み取り
  - 読み取ったバッファを int16→float に正規化
  - RMS を計算して `current_volume` を更新
  - `librosa.pyin` を使って F0 を推定し `current_f0` / `current_note` を更新
  - 例外発生時はストリームを閉じ、GUI のボタン状態を復帰して解析を停止
- GUI 更新スレッドのループ:
  - 定期的に `master.after` でメインスレッドに `_update_gui_elements` を投げ、表示を更新

**主要パラメータ**

- `CHUNK = 1024` (読み取り単位サンプル数)
- `FORMAT = pyaudio.paInt16`
- `CHANNELS = 1` (モノラル)
- `RATE = 44100` (Hz)
- `librosa.pyin` の `fmin` = `C2`、`fmax` = `C7`、`frame_length` は `CHUNK * 2` としている（要注意）

**依存関係**

- Python 3.8+ 推奨
- numpy
- librosa
- soundfile (librosa の依存)
- pyaudio (Windows では `pipwin` 経由のインストール推奨)

**依存ライブラリのライセンス**

以下は本プロジェクトでインストールされる主要ライブラリと、それぞれのライセンス情報（代表的なライセンス名と公式リポジトリ／ドキュメントへの参照）です。実際に配布／商用利用する場合は、各ライブラリの配布パッケージ内 `LICENSE` や公式リポジトリで最新版ライセンスを必ず確認してください。

- `numpy` — BSD 3-Clause License
   - 参照: https://numpy.org/ (ソース/リポジトリにライセンス記載)
- `librosa` — ISC License
   - 参照: https://github.com/librosa/librosa
- `soundfile` (PySoundFile) — BSD-style (ライセンス表記を参照)
   - 参照: https://github.com/bastibe/python-soundfile
- `pyaudio` (PortAudio の Python バインディング) — PortAudio は MIT系（詳細は各パッケージの LICENSE を参照）
   - 参照: https://people.csail.mit.edu/hubert/pyaudio/ 及び https://portaudio.com/
- `pipwin` — MIT License（pipwin 自体は補助ツールであり、配布物のライセンスは個別に確認してください）
   - 参照: https://github.com/lepisma/pipwin

注意: 上記は 参考情報 です。実際の配布／再配布・商用利用の可否は各ライブラリの `LICENSE` ファイルの文言に従って判断してください。

**インストール手順（Windows / PowerShell）**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install --upgrade pip
pip install numpy librosa soundfile
pip install pipwin
pipwin install pyaudio
```

**実行方法**

```powershell
python c:\dev\PythonModule\instrument_analyzer_gui\instrument_analyzer_gui.pyw
```

**既知の問題と注意点**

1. フレーム長不整合（重要）
   - 現在の実装では `CHUNK`（=1024）分だけを読み取り、そのデータで `librosa.pyin` を `frame_length=CHUNK*2`（=2048）で呼び出しています。`frame_length` が入力バッファ長より長いと正しい解析が行えない可能性があります。ストリーミング用途ではフレームを蓄積するリングバッファ方式で `frame_length` 分を揃えてから pyin を呼ぶ必要があります。

2. 計算負荷
   - `librosa.pyin` は重めのアルゴリズムです。リアルタイム性を重視する場合は `aubio` の `pitch`、またはより軽量な YIN 実装等の利用を検討してください。

3. デバイス列挙の堅牢性
   - `get_host_api_info_by_index(0)` に依存しているため、ホストAPIのインデックスが異なる環境では正しく列挙できない可能性があります。`p.get_device_count()` と `p.get_device_info_by_index(i)` の利用が望ましいです。

4. 例外ハンドリング
   - 例外時にエラー内容のスタックトレースが出力されないため、デバッグ時に不便です。`traceback.print_exc()` の追加を推奨します。

5. スレッド停止の明示性
   - スレッドは daemon に設定されているためプロセス終了で止まるが、明示的な終了シーケンス（イベントフラグ + join）を実装するとより安全です。

**改善提案（優先度順）**

- 最優先: フレーム蓄積（リングバッファ）を導入し、`librosa.pyin` 呼び出し時の `frame_length` を安定化させる。
- 次点: pyin を置き換える軽量ピッチ検出の検討（例: `aubio`）。
- デバイス列挙を汎用化する修正。
- 例外ログ出力（traceback）を追加。
- GUI に解析パラメータ（frame_length, hop_length, fmin/fmax, sensitivity 等）を追加してユーザが調整可能にする。
- 結果をキュー経由で渡す設計にしてスレッド間の責務を明確化する。

**将来的な拡張案**

- 録音ログ機能（WAV 出力）
- 検出結果の時間的表示（波形上のマーカー、ログ）
- マルチチャネル入力対応
- 小節・楽器分類のための機械学習モデルとの連携

**ファイル**

- 実装ファイル: `instrument_analyzer_gui.pyw`
- 仕様書: `SPEC.md` (本ファイル)

**バージョン管理と変更履歴**

- 本プロジェクトは Git を用いたバージョン管理を想定しています。`SPEC.md` と実装コードの双方でバージョンを明記し、変更履歴は `CHANGELOG.md` に記録してください。
- 推奨ワークフロー（例）:
   1. 機能追加や修正を行う前にブランチを切る: `git checkout -b feature/describe-change`
   2. コードに対応する `__version__` を適宜更新（例: `0.1.1` → `0.1.2`）し、`SPEC.md` のバージョン表記と `CHANGELOG.md` に変更点を記載する。
   3. 変更をコミットして PR を作成・レビュー後に main にマージ。
   4. リリース時にはタグを作成: `git tag -a v0.1.2 -m "Release v0.1.2"` として、`git push --tags`。

- バージョニング方式: SemVer（MAJOR.MINOR.PATCH）を推奨します。
   - MAJOR: 互換性のない API 変更
   - MINOR: 後方互換のある機能追加
   - PATCH: バグ修正・軽微な改善

- 実装上の運用ルール（推奨）:
   - 実行コードのトップレベルに `__version__ = "0.x.y"` を配置し、リリース時に更新します。
   - `CHANGELOG.md` は必ず人間が読める要約（変更点、影響範囲、担当者）を記載します。
   - `SPEC.md` には現在のバージョンと最後に更新した日付を追記してください（本ファイル末尾の作成日を更新する運用でも可）。


---

作成日: 2025-11-16

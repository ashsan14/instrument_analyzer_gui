#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ロギング機能テストスクリプト
"""
import os
import sys
from instrument_analyzer_gui import logger, LOG_FILE, ERROR_LOG_FILE

print("=== ロギング機能テスト ===\n")

# テストメッセージを記録
logger.info("Test info message")
logger.warning("Test warning message")
logger.error("Test error message with traceback")

print(f"実行ログファイル: {LOG_FILE}")
print(f"エラーログファイル: {ERROR_LOG_FILE}\n")

print("=== 実行ログ内容 ===")
if os.path.exists(LOG_FILE):
    with open(LOG_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
        print(content if content else "(ファイルが空)")
else:
    print(f"ファイルが見つかりません: {LOG_FILE}")

print("\n=== エラーログ内容 ===")
if os.path.exists(ERROR_LOG_FILE):
    with open(ERROR_LOG_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
        print(content if content else "(ファイルが空)")
else:
    print(f"ファイルが見つかりません: {ERROR_LOG_FILE}")

print("\n=== ディレクトリ構成 ===")
logs_dir = "logs"
if os.path.exists(logs_dir):
    files = os.listdir(logs_dir)
    print(f"ログディレクトリ内のファイル:")
    for f in files:
        fpath = os.path.join(logs_dir, f)
        size = os.path.getsize(fpath)
        print(f"  - {f} ({size} bytes)")
else:
    print("ログディレクトリが存在しません")

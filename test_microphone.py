#!/usr/bin/env python3
"""マイクの基本動作テストスクリプト"""

import sounddevice as sd
import numpy as np
import time

def test_microphone():
    print("マイクテストを開始します...")
    
    # デバイス情報の表示
    print("\n利用可能な入力デバイス:")
    devices = sd.query_devices()
    for i, device in enumerate(devices):
        if device['max_input_channels'] > 0:
            print(f"  {i}: {device['name']} (入力チャネル: {device['max_input_channels']})")
    
    # デフォルトデバイスで簡単なテスト
    try:
        default_device = sd.query_devices(kind='input')
        print(f"\nデフォルトデバイス: {default_device['name']} (Index: {default_device['index']})")
        
        print("\n10秒間の音声取得テスト開始...")
        print("何か音を出してください...")
        
        # 音声データ収集
        duration = 10  # 10秒
        sample_rate = 44100
        
        def callback(indata, frames, time, status):
            if status:
                print(f"ステータス: {status}")
            
            # チャネル処理
            if indata.ndim > 1:
                audio_data = indata[:, 0]
            else:
                audio_data = indata
                
            # 基本統計
            rms = np.sqrt(np.mean(audio_data**2))
            max_val = np.max(np.abs(audio_data))
            
            # 10回に1回ログ出力
            if not hasattr(callback, 'counter'):
                callback.counter = 0
            callback.counter += 1
            
            if callback.counter % 10 == 0:
                print(f"RMS: {rms:.6f}, Max: {max_val:.6f}, Range: [{np.min(audio_data):.6f}, {np.max(audio_data):.6f}]")
        
        with sd.InputStream(device=default_device['index'], 
                          samplerate=sample_rate,
                          channels=1,
                          callback=callback):
            time.sleep(duration)
            
        print("テスト完了!")
        
    except Exception as e:
        print(f"エラー: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_microphone()
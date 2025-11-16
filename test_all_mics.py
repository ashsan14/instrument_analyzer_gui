#!/usr/bin/env python3
"""全デバイスのテストスクリプト"""

import sounddevice as sd
import numpy as np
import time

def test_all_microphones():
    print("全マイクデバイステストを開始します...")
    
    # デバイス情報の表示
    devices = sd.query_devices()
    input_devices = []
    for i, device in enumerate(devices):
        if device['max_input_channels'] > 0:
            input_devices.append((i, device))
    
    print(f"\n{len(input_devices)}個の入力デバイスをテストします:")
    
    working_devices = []
    
    for idx, device in input_devices:
        print(f"\nテスト中: {idx}: {device['name']}")
        try:
            # 短時間のテスト
            test_duration = 2  # 2秒
            sample_count = 0
            max_amplitude = 0
            
            def test_callback(indata, frames, time, status):
                nonlocal sample_count, max_amplitude
                if status:
                    print(f"  ステータス: {status}")
                
                # チャネル処理
                if indata.ndim > 1:
                    audio_data = indata[:, 0]
                else:
                    audio_data = indata
                
                sample_count += len(audio_data)
                current_max = np.max(np.abs(audio_data))
                max_amplitude = max(max_amplitude, current_max)
            
            with sd.InputStream(device=idx, 
                              samplerate=44100,
                              channels=1,
                              blocksize=512,
                              callback=test_callback):
                time.sleep(test_duration)
            
            print(f"  ✓ 成功: {sample_count}サンプル取得, 最大振幅: {max_amplitude:.6f}")
            working_devices.append((idx, device['name'], max_amplitude))
            
        except Exception as e:
            error_msg = str(e)
            if "MME error" in error_msg:
                print(f"  ✗ MME エラー: Windowsドライバー問題")
            elif "Invalid device" in error_msg:
                print(f"  ✗ 無効なデバイス")
            else:
                print(f"  ✗ エラー: {error_msg}")
    
    print(f"\n=== 結果 ===")
    if working_devices:
        print(f"動作するデバイス: {len(working_devices)}個")
        for idx, name, amplitude in working_devices:
            status = "音声検出中" if amplitude > 0.001 else "無音"
            print(f"  {idx}: {name} - {status} (振幅: {amplitude:.6f})")
        
        # 推奨デバイス
        best_device = max(working_devices, key=lambda x: x[2])
        print(f"\n推奨デバイス: {best_device[0]} - {best_device[1]}")
    else:
        print("動作するデバイスがありません。Windowsの音声設定を確認してください。")

if __name__ == "__main__":
    test_all_microphones()
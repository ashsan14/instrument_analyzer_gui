#!/usr/bin/env python3
"""音声検出の詳細診断ツール"""

import sounddevice as sd
import numpy as np
import time
import sys

def test_specific_device(device_index):
    """特定のデバイスで詳細テスト"""
    print(f"デバイス {device_index} の詳細テスト開始...")
    
    try:
        # デバイス情報取得
        device_info = sd.query_devices(device_index)
        print(f"デバイス名: {device_info['name']}")
        print(f"最大入力チャネル: {device_info['max_input_channels']}")
        print(f"デフォルトサンプルレート: {device_info['default_samplerate']}")
        
        if device_info['max_input_channels'] == 0:
            print("❌ このデバイスは入力をサポートしていません")
            return False
        
        # 複数の設定でテスト
        test_configs = [
            {"samplerate": 44100, "blocksize": 512, "channels": 1},
            {"samplerate": 22050, "blocksize": 256, "channels": 1},
            {"samplerate": 16000, "blocksize": 128, "channels": 1},
        ]
        
        for i, config in enumerate(test_configs):
            print(f"\n設定 {i+1}: {config}")
            try:
                # 実際に音声を取得してテスト
                sample_count = 0
                max_amplitude = 0
                total_energy = 0
                
                def callback(indata, frames, time, status):
                    nonlocal sample_count, max_amplitude, total_energy
                    if status:
                        print(f"  ステータス警告: {status}")
                    
                    # データ処理
                    if indata.ndim > 1:
                        audio_data = indata[:, 0]
                    else:
                        audio_data = indata
                    
                    sample_count += len(audio_data)
                    current_max = np.max(np.abs(audio_data))
                    max_amplitude = max(max_amplitude, current_max)
                    total_energy += np.sum(audio_data ** 2)
                
                # 3秒間のテスト
                print(f"  3秒間テスト中... 音を出してください")
                with sd.InputStream(
                    device=device_index,
                    samplerate=config["samplerate"], 
                    blocksize=config["blocksize"],
                    channels=config["channels"],
                    callback=callback,
                    dtype=np.float32
                ):
                    time.sleep(3.0)
                
                rms = np.sqrt(total_energy / sample_count) if sample_count > 0 else 0
                
                print(f"  ✅ 成功!")
                print(f"    サンプル数: {sample_count}")
                print(f"    最大振幅: {max_amplitude:.6f}")
                print(f"    RMS: {rms:.6f}")
                
                if max_amplitude > 0.001:
                    print(f"    🔊 音声検出: 良好なレベル")
                elif max_amplitude > 0.0001:
                    print(f"    🔇 音声検出: 微弱なレベル (ゲイン必要)")
                else:
                    print(f"    ❌ 音声検出: ほぼ無音")
                
                return True
                
            except Exception as e:
                print(f"  ❌ 失敗: {e}")
                continue
        
        return False
        
    except Exception as e:
        print(f"❌ デバイステストエラー: {e}")
        return False

def main():
    """メイン診断"""
    if len(sys.argv) > 1:
        # 特定のデバイスをテスト
        device_index = int(sys.argv[1])
        test_specific_device(device_index)
    else:
        # 動作可能デバイスを探索
        print("🔍 利用可能なオーディオデバイスを検索中...")
        
        devices = sd.query_devices()
        working_devices = []
        
        for idx, device in enumerate(devices):
            if device['max_input_channels'] > 0:
                print(f"\n=== デバイス {idx}: {device['name']} ===")
                if test_specific_device(idx):
                    working_devices.append((idx, device['name']))
        
        print(f"\n=== 結果 ===")
        if working_devices:
            print(f"動作する入力デバイス: {len(working_devices)}個")
            for idx, name in working_devices:
                print(f"  {idx}: {name}")
            
            print(f"\n推奨デバイスでの再テスト:")
            print(f"python {sys.argv[0]} {working_devices[0][0]}")
        else:
            print("❌ 動作する入力デバイスが見つかりませんでした")
            print("Windowsの音声設定を確認してください:")
            print("1. 設定 → プライバシーとセキュリティ → マイク")
            print("2. デバイスマネージャー → オーディオの入力と出力")
            print("3. コントロールパネル → サウンド → 録音")

if __name__ == "__main__":
    main()
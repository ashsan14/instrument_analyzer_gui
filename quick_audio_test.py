#!/usr/bin/env python3
"""
Windows Audio Device Quick Test
すべての入力デバイスを高速テストし、利用可能なものを特定
"""

import sounddevice as sd
import numpy as np
import time

def quick_device_test():
    print("=== Windows Audio Device Quick Test ===")
    print("Testing all input devices for basic connectivity...")
    print()
    
    try:
        devices = sd.query_devices()
        working_devices = []
        
        print(f"Found {len(devices)} total audio devices")
        print("-" * 60)
        
        for idx, device in enumerate(devices):
            if device.get('max_input_channels', 0) > 0:
                device_name = device['name']
                print(f"Testing Device {idx}: {device_name}")
                
                # 超高速接続テスト
                success = False
                error_msg = ""
                
                try:
                    # 最小限のテスト（256サンプル、0.005秒）
                    test_data = sd.rec(
                        frames=256,
                        samplerate=44100,
                        channels=1,
                        device=idx,
                        dtype=np.float32
                    )
                    sd.wait()
                    
                    if test_data is not None and len(test_data) > 0:
                        max_level = np.max(np.abs(test_data))
                        success = True
                        working_devices.append((idx, device_name, max_level))
                        print(f"  ✅ SUCCESS - Max level: {max_level:.6f}")
                    else:
                        print(f"  ❌ FAILED - No data returned")
                        
                except Exception as e:
                    error_msg = str(e)
                    if "MME error 1" in error_msg:
                        print(f"  ❌ FAILED - Windows MME driver error")
                    elif "DirectSound" in error_msg:
                        print(f"  ❌ FAILED - DirectSound error")
                    else:
                        print(f"  ❌ FAILED - {error_msg[:50]}...")
                
                print()
        
        print("=" * 60)
        print("SUMMARY:")
        
        if working_devices:
            print(f"✅ Found {len(working_devices)} working input devices:")
            for idx, name, level in working_devices:
                status = "🔊 Active" if level > 0.001 else "🔇 Silent"
                print(f"  Device {idx}: {name}")
                print(f"    Status: {status} (level: {level:.6f})")
                print()
                
            # 推奨デバイス
            print("RECOMMENDATIONS:")
            
            # レベルが最も高いデバイス
            if working_devices:
                best_device = max(working_devices, key=lambda x: x[2])
                print(f"🎯 Most active device: {best_device[0]} - {best_device[1]}")
                
            # ステレオミキサーがある場合
            stereo_devices = [d for d in working_devices if 'ステレオ' in d[1] or 'Stereo' in d[1]]
            if stereo_devices:
                print(f"🔊 Stereo mixer available: {stereo_devices[0][0]} - {stereo_devices[0][1]}")
                
        else:
            print("❌ NO WORKING INPUT DEVICES FOUND")
            print()
            print("Troubleshooting suggestions:")
            print("1. Run as Administrator")
            print("2. Check Windows Privacy Settings:")
            print("   Settings > Privacy & Security > Microphone")
            print("3. Update audio drivers in Device Manager")
            print("4. Restart Windows Audio service:")
            print("   services.msc > Windows Audio > Restart")
            
    except Exception as e:
        print(f"Critical error during device enumeration: {e}")

if __name__ == "__main__":
    quick_device_test()
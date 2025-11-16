#!/usr/bin/env python3
"""
Simple Audio Callback Test
audio_callback問題の最小限の修正版
"""

import sounddevice as sd
import numpy as np
import time

def test_simple_callback():
    """シンプルなコールバックテスト"""
    print("Testing simple audio callback...")
    
    # テスト用のコールバック関数
    def callback(indata, frames, time_info, status):
        if status:
            print(f"Status: {status}")
        # 音量レベルを計算
        if indata is not None and len(indata) > 0:
            chunk = indata[:, 0] if indata.ndim > 1 else indata
            volume = np.sqrt(np.mean(chunk ** 2))
            print(f"Volume: {volume:.6f}, Max: {np.max(np.abs(chunk)):.6f}")
    
    try:
        # デバイス29（ステレオミキサー）でテスト
        print("Starting audio stream with device 29...")
        stream = sd.InputStream(
            device=29,
            channels=1,
            samplerate=44100,
            blocksize=1024,
            callback=callback,
            dtype=np.float32
        )
        
        stream.start()
        print("✅ Audio stream started successfully!")
        print("Recording for 10 seconds... (play some audio)")
        
        time.sleep(10)
        
        stream.stop()
        stream.close()
        print("✅ Test completed successfully!")
        
    except Exception as e:
        print(f"❌ Test failed: {e}")

if __name__ == "__main__":
    test_simple_callback()
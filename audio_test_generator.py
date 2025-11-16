#!/usr/bin/env python3
"""
Simple Audio Test Generator
ステレオミキサーでの音声検出テスト用に音階を生成・再生
"""

import numpy as np
import sounddevice as sd
import time

def generate_tone(frequency, duration, sample_rate=44100):
    """指定周波数のサイン波を生成"""
    t = np.linspace(0, duration, int(sample_rate * duration))
    # エンベロープを適用して滑らかに
    envelope = np.exp(-t * 3)  # 減衰
    tone = 0.3 * np.sin(2 * np.pi * frequency * t) * envelope
    return tone

def play_musical_notes():
    """音楽的な音階を順番に再生"""
    print("=== Musical Note Test for Stereo Mixer ===")
    print("Playing musical notes through speakers...")
    print("This should be captured by Stereo Mixer (Device 29)")
    print()
    
    # ドレミファソラシド (C Major Scale)
    notes = [
        ("C4 (ド)", 261.63),
        ("D4 (レ)", 293.66),
        ("E4 (ミ)", 329.63),
        ("F4 (ファ)", 349.23),
        ("G4 (ソ)", 392.00),
        ("A4 (ラ)", 440.00),
        ("B4 (シ)", 493.88),
        ("C5 (ド)", 523.25)
    ]
    
    try:
        for note_name, frequency in notes:
            print(f"♪ Playing {note_name} ({frequency:.2f} Hz)")
            
            # 1秒間のトーンを生成
            tone = generate_tone(frequency, 1.0)
            
            # スピーカーから再生
            sd.play(tone, samplerate=44100)
            sd.wait()  # 再生完了を待つ
            
            time.sleep(0.5)  # 0.5秒の休止
        
        print()
        print("✅ Musical note playback completed!")
        print("If Stereo Mixer is working, the app should detect these frequencies.")
        
    except Exception as e:
        print(f"❌ Audio playback error: {e}")

def play_continuous_sweep():
    """連続的な周波数スイープを再生"""
    print("\n=== Frequency Sweep Test ===")
    print("Playing continuous frequency sweep (200-800 Hz)...")
    print("Duration: 10 seconds")
    
    try:
        duration = 10.0
        start_freq = 200.0
        end_freq = 800.0
        sample_rate = 44100
        
        t = np.linspace(0, duration, int(sample_rate * duration))
        # 線形に周波数を変化
        freq_t = start_freq + (end_freq - start_freq) * t / duration
        # チャープシグナル（周波数変化）
        sweep = 0.2 * np.sin(2 * np.pi * np.cumsum(freq_t) / sample_rate)
        
        print("Starting sweep...")
        sd.play(sweep, samplerate=sample_rate)
        sd.wait()
        
        print("✅ Frequency sweep completed!")
        
    except Exception as e:
        print(f"❌ Sweep playback error: {e}")

def main():
    print("🎵 Audio Test Generator for Stereo Mixer")
    print("="*50)
    
    while True:
        print("\nSelect test:")
        print("1. Play musical notes (C Major Scale)")
        print("2. Play frequency sweep (200-800 Hz)")
        print("3. Both tests")
        print("0. Exit")
        
        try:
            choice = input("\nEnter choice (0-3): ").strip()
            
            if choice == '0':
                break
            elif choice == '1':
                play_musical_notes()
            elif choice == '2':
                play_continuous_sweep()
            elif choice == '3':
                play_musical_notes()
                time.sleep(2)
                play_continuous_sweep()
            else:
                print("Invalid choice. Please enter 0-3.")
                
        except KeyboardInterrupt:
            print("\n\nTest interrupted by user.")
            break
        except Exception as e:
            print(f"Error: {e}")
    
    print("\n🎵 Audio test completed. Thank you!")

if __name__ == "__main__":
    main()
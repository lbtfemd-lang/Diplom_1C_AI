import sys
import os
import ctypes

def main():
    if len(sys.argv) < 2:
        sys.exit(1)
    
    wav_path = sys.argv[1]
    
    winmm = ctypes.windll.winmm
    winmm.mciSendStringW("close all", None, 0, None)
    winmm.mciSendStringW("open new type waveaudio alias recsound", None, 0, None)
    winmm.mciSendStringW("set recsound time format ms bitspersample 16 channels 1 samplespersec 16000 bytespersec 32000 alignment 2", None, 0, None)
    winmm.mciSendStringW("record recsound", None, 0, None)
    
    try:
        # Wait for stop signal via stdin
        sys.stdin.read()
    except Exception:
        pass
    
    winmm.mciSendStringW(f'save recsound "{wav_path}"', None, 0, None)
    winmm.mciSendStringW("close recsound", None, 0, None)

if __name__ == "__main__":
    main()

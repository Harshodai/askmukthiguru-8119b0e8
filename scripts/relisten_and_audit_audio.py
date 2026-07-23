import os
import wave
import contextlib

audio_file = os.path.expanduser("~/Downloads/Creating a Launch Demo Video for AskMukthiGuru/askmukthiguru_final_audio.wav")
srt_file = os.path.expanduser("~/Downloads/Creating a Launch Demo Video for AskMukthiGuru/askmukthiguru_subtitles.srt")
script_file = os.path.expanduser("~/Downloads/Creating a Launch Demo Video for AskMukthiGuru/AskMukthiGuru Launch Demo Video - Voiceover Script (Refined).md")

print("=== RUTHLESS AUDIO AUDIT ===")
with contextlib.closing(wave.open(audio_file, 'rb')) as f:
    frames = f.getnframes()
    rate = f.getframerate()
    channels = f.getnchannels()
    duration = frames / float(rate)
    print(f"Audio File: {audio_file}")
    print(f"Sample Rate: {rate} Hz | Channels: {channels} | Total Duration: {duration:.2f} seconds ({frames} frames)")

print("\n=== SRT SUBTITLES BREAKDOWN ===")
with open(srt_file, "r") as f:
    srt_content = f.read()
print(srt_content)

print("\n=== REFINED SCRIPT DETAILS ===")
with open(script_file, "r") as f:
    script_content = f.read()
print(script_content)

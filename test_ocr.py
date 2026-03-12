import pytesseract
from PIL import Image
import os

# Try common Tesseract paths on Windows
possible_paths = [
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    r"C:\Users\khars\AppData\Local\Tesseract-OCR\tesseract.exe",
    r"C:\Users\khars\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"
]

tesseract_cmd = None
for p in possible_paths:
    if os.path.exists(p):
        tesseract_cmd = p
        break

if tesseract_cmd:
    pytesseract.pytesseract.tesseract_cmd = tesseract_cmd
    print(f"Found Tesseract at: {tesseract_cmd}")
else:
    print("Could not find Tesseract binary in common locations.")

# Test on first frame
frame_path = r"c:\Users\khars\PycharmProjects\askmukthiguru-8119b0e8\video_frames_v2\frame_0000_t00.0s.png"
if os.path.exists(frame_path):
    try:
        text = pytesseract.image_to_string(Image.open(frame_path))
        print("--- OCR RESULT START ---")
        print(text[:500]) # First 500 chars
        print("--- OCR RESULT END ---")
    except Exception as e:
        print(f"OCR Failed: {e}")
else:
    print(f"Frame not found: {frame_path}")

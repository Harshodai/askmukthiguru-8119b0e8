import asyncio
import edge_tts
import os

TEXT = "When something is heavy on your heart at 2 AM, search engines give you noise. AskMukthiGuru is an AI guide grounded in authentic spiritual wisdom."

VOICES = [
    ("en-US-AvaNeural", "ava_us_female"),
    ("en-US-EmmaNeural", "emma_us_female"),
    ("en-IN-NeerjaNeural", "neerja_indian_female"),
    ("en-US-JennyNeural", "jenny_us_female"),
]

output_dir = "video-composition/assets/audio/voice_samples"
os.makedirs(output_dir, exist_ok=True)

async def generate_all():
    for voice, name in VOICES:
        out_path = os.path.join(output_dir, f"{name}.mp3")
        print(f"Generating voice sample for {voice} -> {out_path}...")
        communicate = edge_tts.Communicate(TEXT, voice)
        await communicate.save(out_path)
    print("All audio samples generated successfully!")

if __name__ == "__main__":
    asyncio.run(generate_all())

import os
import subprocess

def extract_keyframes():
    video_path = "askmukthiguru-official-launch-demo.mp4"
    output_dir = "video-composition/assets/keyframes"
    os.makedirs(output_dir, exist_ok=True)

    # Exact scene timestamps matching index.html GSAP timeline
    scenes = [
        ("Scene 1 (Problem)", "00:00:04", "frame_01_problem.png"),
        ("Scene 2A (Hero)", "00:00:11", "frame_02a_hero.png"),
        ("Scene 2B (How It Works)", "00:00:18", "frame_02b_how_it_works.png"),
        ("Scene 2C (Wisdom)", "00:00:26", "frame_02c_wisdom.png"),
        ("Scene 3 (Auth / Sign-In)", "00:00:35", "frame_03_auth.png"),
        ("Scene 4 (Grounded Chat)", "00:00:50", "frame_04_chat.png"),
        ("Scene 5 (Serene Mind)", "00:01:08", "frame_05_serene_mind.png"),
        ("Scene 6A (Knowledge Graph)", "00:01:20", "frame_06a_kg.png"),
        ("Scene 6B (Study Notebook)", "00:01:28", "frame_06b_notebook.png"),
        ("Scene 7 (Privacy Vault)", "00:01:38", "frame_07_privacy.png"),
        ("Scene 8 (Outro CTA)", "00:01:48", "frame_08_outro.png"),
    ]

    print("Extracting exact keyframes from rendered video...")
    for name, timestamp, filename in scenes:
        output_path = os.path.join(output_dir, filename)
        cmd = [
            "ffmpeg", "-y", "-ss", timestamp, "-i", video_path,
            "-vframes", "1", "-q:v", "2", output_path
        ]
        subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        if os.path.exists(output_path):
            size_kb = os.path.getsize(output_path) // 1024
            print(f"✓ {name} [{timestamp}] -> {filename} ({size_kb} KB)")

    print("\nKeyframe extraction complete!")

if __name__ == "__main__":
    extract_keyframes()

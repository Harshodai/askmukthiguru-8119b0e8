"""
Google Colab Data Transfer Script

Use this to backup and restore your Mukthi Guru data (Qdrant & Models)
to/from Google Drive or your local machine.
"""

import os
import shutil
import datetime
import sys
from pathlib import Path

# Paths to backup
BACKEND_DIR = Path(os.getcwd())  # Assuming run from backend/
QDRANT_DATA = BACKEND_DIR / "qdrant_data"
HF_CACHE = Path.home() / ".cache" / "huggingface"

# Backup filename format
TIMESTAMP = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP_FILENAME = f"mukthiguru_backup_{TIMESTAMP}.zip"

def mount_drive():
    """Mount Google Drive to /content/drive."""
    if os.path.exists("/content/drive"):
        print("✅ Google Drive already mounted.")
        return Path("/content/drive/MyDrive")
    
    try:
        from google.colab import drive
        drive.mount("/content/drive")
        return Path("/content/drive/MyDrive")
    except ImportError:
        print("⚠️  Not running in Google Colab (or google.colab module missing).")
        return None

def backup(target="drive", include_models=False):
    """
    Create a zip backup of qdrant_data (and optionally models).
    
    Args:
        target: 'drive' (save to GDrive) or 'local' (download file).
        include_models: If True, includes ~/.cache/huggingface (large!).
    """
    print(f"📦 Starting backup ({target})...")
    
    # Create a temp directory for staging
    staging_dir = Path("temp_backup_staging")
    if staging_dir.exists():
        shutil.rmtree(staging_dir)
    staging_dir.mkdir()
    
    # 1. Copy Qdrant Data
    if QDRANT_DATA.exists():
        print(f"   Copying Qdrant data ({get_size(QDRANT_DATA)})...")
        shutil.copytree(QDRANT_DATA, staging_dir / "qdrant_data")
    else:
        print("⚠️  No Qdrant data found to backup.")
        
    # 2. Copy Models (Optional - can be huge)
    if include_models:
        if HF_CACHE.exists():
            print(f"   Copying HuggingFace models ({get_size(HF_CACHE)})... this may take a while.")
            shutil.copytree(HF_CACHE, staging_dir / "models")
        else:
            print("⚠️  No HuggingFace cache found.")
            
    # 3. Zip it
    print("   Zipping archive...")
    shutil.make_archive("backup", "zip", staging_dir)
    zip_path = Path("backup.zip")
    
    # 4. Transfer
    final_path = None
    if target == "drive":
        drive_path = mount_drive()
        if drive_path:
            dest = drive_path / "MukthiGuru_Backups"
            dest.mkdir(exist_ok=True)
            final_path = dest / BACKUP_FILENAME
            shutil.copy2(zip_path, final_path)
            print(f"✅ Backup saved to Google Drive: {final_path}")
        else:
            print("❌ Cannot save to Drive (not mounted or valid).")
            
    elif target == "local":
        try:
            from google.colab import files
            files.download(str(zip_path))
            print("✅ Triggered local download.")
        except ImportError:
            print(f"⚠️  Not in Colab. File saved locally at: {zip_path.absolute()}")
            
    # Cleanup
    shutil.rmtree(staging_dir)
    if final_path and target == "drive":
        # clean up local zip if moved to drive
        zip_path.unlink()
        
def restore(backup_path, target_dir="."):
    """
    Restore from a backup zip file.
    """
    backup_file = Path(backup_path)
    if not backup_file.exists():
        print(f"❌ Backup file not found: {backup_file}")
        return
        
    print(f"♻️  Restoring from {backup_file}...")
    shutil.unpack_archive(backup_file, "temp_restore_staging")
    staging = Path("temp_restore_staging")
    
    # Restore Qdrant
    if (staging / "qdrant_data").exists():
        if QDRANT_DATA.exists():
            print("   Overwriting existing qdrant_data...")
            shutil.rmtree(QDRANT_DATA)
        shutil.move(str(staging / "qdrant_data"), str(QDRANT_DATA))
        print("✅ Qdrant data restored.")
        
    # Restore Models
    if (staging / "models").exists():
        print("   Restoring models to ~/.cache/huggingface...")
        if not HF_CACHE.parent.exists():
            HF_CACHE.parent.mkdir(parents=True)
        # Verify if we want to overwrite entire cache? 
        # Safer to merge or overwrite. Let's overwrite for simplicity in restore.
        if HF_CACHE.exists():
            shutil.rmtree(HF_CACHE)
        shutil.move(str(staging / "models"), str(HF_CACHE))
        print("✅ Models restored.")
        
    shutil.rmtree(staging)
    print("🎉 Restore complete. Please restart the backend.")

def get_size(start_path):
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(start_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if not os.path.islink(fp):
                total_size += os.path.getsize(fp)
    # convert to readable
    for unit in ['B', 'KiB', 'MiB', 'GiB']:
        if total_size < 1024.0:
            return f"{total_size:.1f} {unit}"
        total_size /= 1024.0
    return f"{total_size:.1f} TiB"

if __name__ == "__main__":
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "backup":
            backup(target="drive", include_models="--models" in sys.argv)
        elif cmd == "restore":
            if len(sys.argv) > 2:
                restore(sys.argv[2])
            else:
                print("Usage: python transfer.py restore <path_to_zip>")
    else:
        print("Usage:")
        print("  python transfer.py backup [--models]")
        print("  python transfer.py restore <path_to_zip>")

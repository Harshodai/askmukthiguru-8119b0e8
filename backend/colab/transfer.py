"""
Google Colab Data Transfer Script

Use this to backup and restore your Mukthi Guru data (Qdrant & Models)
to/from Google Drive or your local machine.
"""

import os
import shutil
import datetime
import sys
import tempfile
from pathlib import Path

# Paths to backup
BACKEND_DIR = Path(os.getcwd())  # Assuming run from backend/
QDRANT_DATA = BACKEND_DIR / "qdrant_data"
HF_CACHE = Path.home() / ".cache" / "huggingface"


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

def _get_timestamp():
    """Get current timestamp for filename."""
    return datetime.datetime.now().strftime("%Y%m%d_%H%M%S")

def backup(target="drive", include_models=False):
    """
    Create a zip backup of qdrant_data (and optionally models).
    
    Args:
        target: 'drive' (save to GDrive) or 'local' (download file).
        include_models: If True, includes ~/.cache/huggingface (large!).
    """
    print(f"📦 Starting backup ({target})...")
    
    timestamp = _get_timestamp()
    backup_filename = f"mukthiguru_backup_{timestamp}.zip"
    
    # Create a temp directory for staging
    with tempfile.TemporaryDirectory() as staging_str:
        staging_dir = Path(staging_str)
        
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
        # make_archive creates zip at base_name + .zip
        zip_base = Path("backup_temp")
        shutil.make_archive(str(zip_base), "zip", staging_dir)
        zip_path = Path(f"{zip_base}.zip")
        
        # 4. Transfer
        final_path = None
        if target == "drive":
            drive_path = mount_drive()
            if drive_path:
                dest = drive_path / "MukthiGuru_Backups"
                dest.mkdir(exist_ok=True, parents=True)
                final_path = dest / backup_filename
                shutil.copy2(zip_path, final_path)
                print(f"✅ Backup saved to Google Drive: {final_path}")
            else:
                print("❌ Cannot save to Drive (not mounted or valid).")
                
        elif target == "local":
            try:
                from google.colab import files
                # Rename to timestamped name for download
                renamed_zip = Path(backup_filename)
                shutil.move(str(zip_path), str(renamed_zip))
                zip_path = renamed_zip
                
                files.download(str(zip_path))
                print("✅ Triggered local download.")
            except ImportError:
                print(f"⚠️  Not in Colab. File saved locally at: {zip_path.absolute()}")
                
        # Cleanup zip
        if zip_path.exists():
            zip_path.unlink()
        
def restore(backup_path):
    """
    Restore from a backup zip file with safety checks and staging.
    """
    backup_file = Path(backup_path)
    if not backup_file.exists():
        print(f"❌ Backup file not found: {backup_file}")
        return
        
    print(f"♻️  Restoring from {backup_file}...")
    
    with tempfile.TemporaryDirectory() as staging_str:
        staging = Path(staging_str)
        try:
            shutil.unpack_archive(backup_file, staging)
        except Exception as e:
            print(f"❌ Failed to unpack archive: {e}")
            return

        # Verification
        has_data = (staging / "qdrant_data").exists()
        has_models = (staging / "models").exists()
        
        if not has_data and not has_models:
            print("❌ Invalid backup: No qdrant_data or models found in archive.")
            return

        # --- Restore Qdrant ---
        if has_data:
            print("   Restoring Qdrant data...")
            # Backup existing
            backup_path_q = QDRANT_DATA.with_suffix(".bak")
            if QDRANT_DATA.exists():
                if backup_path_q.exists():
                    shutil.rmtree(backup_path_q)
                shutil.move(str(QDRANT_DATA), str(backup_path_q))
            
            try:
                shutil.move(str(staging / "qdrant_data"), str(QDRANT_DATA))
                print("✅ Qdrant data restored.")
                # Cleanup backup if successful
                if backup_path_q.exists():
                    shutil.rmtree(backup_path_q)
            except Exception as e:
                print(f"❌ Failed to move Qdrant data: {e}")
                print("   Rolling back...")
                if backup_path_q.exists():
                    if QDRANT_DATA.exists():
                        shutil.rmtree(QDRANT_DATA)
                    shutil.move(str(backup_path_q), str(QDRANT_DATA))
                return

        # --- Restore Models ---
        if has_models:
            print("   Restoring models...")
            # Ensure parent exists
            if not HF_CACHE.parent.exists():
                HF_CACHE.parent.mkdir(parents=True)
                
            backup_path_m = HF_CACHE.with_suffix(".bak")
            if HF_CACHE.exists():
                if backup_path_m.exists():
                    shutil.rmtree(backup_path_m)
                shutil.move(str(HF_CACHE), str(backup_path_m))
            
            try:
                shutil.move(str(staging / "models"), str(HF_CACHE))
                print("✅ Models restored.")
                if backup_path_m.exists():
                    shutil.rmtree(backup_path_m)
            except Exception as e:
                print(f"❌ Failed to move Models: {e}")
                print("   Rolling back...")
                if backup_path_m.exists():
                    if HF_CACHE.exists():
                        shutil.rmtree(HF_CACHE)
                    shutil.move(str(backup_path_m), str(HF_CACHE))
                return

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

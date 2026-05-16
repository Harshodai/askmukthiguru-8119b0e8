#!/usr/bin/env python3
import os
import shutil
import logging
from pathlib import Path

# Basic logging without external dependencies
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def flush_gptcache():
    """Delete the GPTCache SQLite database and data directory."""
    # Check current dir and backend dir
    paths = [Path("data/gptcache"), Path("backend/data/gptcache")]
    for cache_dir in paths:
        if cache_dir.exists():
            try:
                shutil.rmtree(cache_dir)
                logger.info(f"✅ GPTCache directory '{cache_dir}' deleted.")
            except Exception as e:
                logger.error(f"❌ Failed to delete GPTCache directory {cache_dir}: {e}")
        else:
            logger.info(f"ℹ️ GPTCache directory '{cache_dir}' not found.")

def main():
    print("\n" + "═"*50)
    print("  🧹  AskMukthiGuru Cache Flusher (Minimal)")
    print("═"*50 + "\n")
    
    flush_gptcache()
    
    # Try to flush redis if available via shell
    try:
        os.system("redis-cli flushall")
        logger.info("✅ Redis flushed (if available via redis-cli).")
    except:
        pass

    print("\n" + "═"*50)
    print("  ✨  Core caches flushed.")
    print("═"*50 + "\n")

if __name__ == "__main__":
    main()

import logging
import os
import sys

# Configure logging to stdout
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# Ensure backend folder is in path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from services.cookie_helper import ensure_cookies_file

print("--- Running Cookie Helper Test ---")
cookie_path = ensure_cookies_file(force_refresh=True)
print(f"Resulting Cookie Path: {cookie_path}")
if cookie_path and os.path.exists(cookie_path):
    print(f"Success! File size: {os.path.getsize(cookie_path)} bytes")
else:
    print("Failure! Cookie file not generated.")

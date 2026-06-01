import os

from dotenv import load_dotenv

# Force loading .env.test for all tests
test_env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env.test")
if os.path.exists(test_env_path):
    load_dotenv(test_env_path, override=True)

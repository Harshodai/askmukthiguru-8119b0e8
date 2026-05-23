import requests

SUPABASE_URL = "http://localhost:54321"
SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZS1kZW1vIiwicm9sZSI6ImFub24iLCJleHAiOjE5ODM4MTI5OTZ9.CRXP1A7WOeoJeXxjNni43kdQwgnWNReilDMblYTn_I0"


def get_token():
    auth_url = f"{SUPABASE_URL}/auth/v1/token?grant_type=password"
    payload = {"email": "kharshaengineer@gmail.com", "password": "Admin@123456"}
    headers = {"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"}
    response = requests.post(auth_url, json=payload, headers=headers)
    response.raise_for_status()
    return response.json()["access_token"]


def test_chat(token):
    url = "http://localhost:8000/api/chat/stream"
    payload = {
        "user_message": "What do Preethaji and Krishnaji teach about entering the Serene Mind state?",
        "messages": [],
        "meditation_step": 0,
    }
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    print(f"\\n🧘‍♂️ Requesting: '{payload['user_message']}'\\n")
    print("-" * 50)

    with requests.post(url, json=payload, headers=headers, stream=True) as r:
        r.raise_for_status()
        for line in r.iter_lines():
            if line:
                line_str = line.decode("utf-8")
                if line_str.startswith("data: "):
                    data = line_str[6:]
                    if data.startswith("{"):  # JSON metadata at the end
                        print(f"\\n\\n[Metadata]: {data}")
                    else:
                        print(data.replace("\\n", ""), end="", flush=True)


if __name__ == "__main__":
    try:
        print("Authenticating...")
        token = get_token()
        print("Authentication successful!")
        test_chat(token)
        print("\\n")
    except Exception as e:
        print(f"Error: {e}")

from litellm import completion
response = completion(
    model="ollama/qwen3.5:9b",
    messages=[{"role": "user", "content": "Hello!"}],
    api_base="http://localhost:11434"
)
print(response.choices[0].message.content)

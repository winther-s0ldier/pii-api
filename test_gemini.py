import os
from dotenv import load_dotenv
from google import genai

load_dotenv()
key = os.getenv("GEMINI_API_KEY", "").strip('"').strip("'")
print(f"Key len: {len(key)}")
try:
    client = genai.Client(api_key=key)
    chat = client.chats.create(model="gemini-3.1-pro-preview")
    print(chat.send_message("hi").text)
except Exception as e:
    print(repr(e))

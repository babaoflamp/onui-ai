import os
import sys
from pathlib import Path
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))
load_dotenv()

from google import genai
from google.genai import types

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
client = genai.Client(api_key=GEMINI_API_KEY)

image_path = "static/images/onui-idol-barista.png"

with open(image_path, "rb") as image_file:
    image_bytes = image_file.read()
    
image_part = types.Part.from_bytes(
    data=image_bytes,
    mime_type="image/png",
)

prompt = "Describe the character's physical appearance (hair color/style, eye color, facial features, vibe) in detail so I can use it to generate a consistent character in DALL-E 3."

response = client.models.generate_content(
    model='gemini-2.5-flash',
    contents=[prompt, image_part]
)
print(response.text)

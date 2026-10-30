from google import genai
from app.core.config import settings

client = genai.Client(api_key=settings.GEMINI_API_KEY)

response = client.models.generate_content(
    model="gemini-2.0-flash-001",
    contents="Say hello in one sentence."
)

print(response.text)
from typing import List
from openai import AsyncOpenAI
from app.core.config import settings


class EmbeddingService:
    def __init__(self, api_key: str | None = None):
        self.client = AsyncOpenAI(
            api_key=api_key or settings.OPENAI_API_KEY
        )

    @staticmethod
    def chunk_text(
        text: str,
        chunk_size: int = 1000,
        overlap: int = 200,
    ) -> List[str]:

        if not text:
            return []

        chunks = []
        start = 0
        text_length = len(text)

        while start < text_length:
            end = start + chunk_size
            chunk = text[start:end].strip()

            if chunk:
                chunks.append(chunk)

            start += chunk_size - overlap

        return chunks

    async def create_embedding(self, text: str) -> list[float]:
        response = await self.client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
        )

        return response.data[0].embedding
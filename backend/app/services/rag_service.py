import json
import math

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.file_chunk import FileChunk
from app.services.embedding_service import EmbeddingService


class RAGService:

    @staticmethod
    def cosine_similarity(
        a: list[float],
        b: list[float],
    ) -> float:
        dot = sum(x * y for x, y in zip(a, b))

        norm_a = math.sqrt(sum(x * x for x in a))
        norm_b = math.sqrt(sum(x * x for x in b))

        if norm_a == 0 or norm_b == 0:
            return 0.0

        return dot / (norm_a * norm_b)

    @staticmethod
    async def search_chunks(
        db: AsyncSession,
        file_id: int,
        question: str,
        api_key: str | None = None,
        top_k: int = 5,
    ) -> list[str]:

        embedding_service = EmbeddingService(api_key)

        question_embedding = await embedding_service.create_embedding(
            question
        )

        result = await db.execute(
            select(FileChunk).where(
                FileChunk.file_id == file_id
            )
        )

        chunks = result.scalars().all()

        scored: list[tuple[float, str]] = []

        for chunk in chunks:

            embedding = json.loads(chunk.embedding)

            similarity = RAGService.cosine_similarity(
                question_embedding,
                embedding,
            )

            scored.append(
                (
                    similarity,
                    chunk.content,
                )
            )

        scored.sort(
            key=lambda x: x[0],
            reverse=True,
        )

        return [
            content
            for _, content in scored[:top_k]
        ]
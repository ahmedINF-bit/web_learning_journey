import re
from dataclasses import dataclass
from typing import Callable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_memory import UserMemory


@dataclass
class MemoryRule:
    memory_type: str
    extract: Callable[[str], str | None]
    validate: Callable[[str], bool]
    build: Callable[[str], str]


class MemoryService:
    def __init__(
        self,
        db: AsyncSession,
        user_id: int,
    ):
        self.db = db
        self.user_id = user_id

        self.rules = [
            MemoryRule(
                memory_type="name",
                extract=self._extract_name,
                validate=self._validate_name,
                build=lambda value: f"The user's name is {value}.",
            ),
            MemoryRule(
                memory_type="study",
                extract=self._extract_study,
                validate=self._validate_text,
                build=lambda value: f"The user studies {value}.",
            ),
            MemoryRule(
                memory_type="location",
                extract=self._extract_location,
                validate=self._validate_text,
                build=lambda value: f"The user lives in {value}.",
            ),
            MemoryRule(
                memory_type="language",
                extract=self._extract_language,
                validate=self._validate_text,
                build=lambda value: f"The user speaks {value}.",
            ),
            MemoryRule(
                memory_type="profession",
                extract=self._extract_job,
                validate=self._validate_text,
                build=lambda value: f"The user works as a {value}.",
            ),
            MemoryRule(
                memory_type="age",
                extract=self._extract_age,
                validate=self._validate_age,
                build=lambda value: f"The user is {value} years old.",
            ),
        ]

    # ========================================================
    # MEMORY UPDATE
    # ========================================================

    async def update_memory(
        self,
        memory_type: str,
        memory_content: str,
    ) -> UserMemory | None:
        result = await self.db.execute(
            select(UserMemory)
            .where(
                UserMemory.user_id == self.user_id,
                UserMemory.memory_type == memory_type,
            )
            .order_by(UserMemory.id)
        )

        memories = result.scalars().all()

        if memories:
            memories[0].content = memory_content

            # Remove accidental duplicates
            for old_memory in memories[1:]:
                await self.db.delete(old_memory)

            await self.db.flush()
            return memories[0]

        self.db.add(
            UserMemory(
                user_id=self.user_id,
                memory_type=memory_type,
                content=memory_content,
            )
        )

        await self.db.flush()

        return None

    # ========================================================
    # MEMORY API
    # ========================================================

    async def get_memories(self) -> list[UserMemory]:
        result = await self.db.execute(
            select(UserMemory)
            .where(UserMemory.user_id == self.user_id)
            .order_by(UserMemory.id)
        )

        return list(result.scalars().all())

    async def delete_memory(
        self,
        memory_type: str,
    ) -> bool:
        result = await self.db.execute(
            select(UserMemory)
            .where(
                UserMemory.user_id == self.user_id,
                UserMemory.memory_type == memory_type,
            )
        )

        memory = result.scalar_one_or_none()

        if memory is None:
            return False

        await self.db.delete(memory)
        await self.db.flush()

        return True

    # ========================================================
    # PROCESS MESSAGE
    # ========================================================

    async def process_message(
        self,
        content: str,
    ) -> None:
        content = content.strip()

        # Process every memory rule instead of stopping
        # after the first match.
        for rule in self.rules:
            value = rule.extract(content)

            if value and rule.validate(value):
                memory_content = rule.build(value)

                await self.update_memory(
                    memory_type=rule.memory_type,
                    memory_content=memory_content,
                )

    # ========================================================
    # MEMORY BOUNDARY
    # ========================================================

    @staticmethod
    def _memory_boundary() -> str:
        return (
            r"(?=\s*,?\s*(?:and\s+)?(?:"
            r"my name is|"
            r"i study|"
            r"i'm studying|"
            r"i am studying|"
            r"my major is|"
            r"i'm a|"
            r"i am a|"
            r"i live in|"
            r"i'm living in|"
            r"i am living in|"
            r"i speak|"
            r"i can speak|"
            r"i work as|"
            r"i'm\s+\d{1,3}|"
            r"i am\s+\d{1,3}"
            r")\b|,\s+|[.!?]\s*$|$)"
        )

    @staticmethod
    def _extract_value(
        content: str,
        pattern: str,
    ) -> str | None:
        boundary = MemoryService._memory_boundary()

        match = re.search(
            pattern + boundary,
            content,
            re.IGNORECASE,
        )

        if match:
            return MemoryService._normalize_value(match.group(1))

        return None

    # ========================================================
    # NORMALIZE VALUE
    # ========================================================

    @staticmethod
    def _normalize_value(
        value: str,
    ) -> str | None:
        value = value.strip()

        # Remove punctuation from the end
        value = value.rstrip(".,!?")

        # Remove extra spaces
        value = value.strip()

        return value or None

    # ========================================================
    # VALIDATION
    # ========================================================

    @staticmethod
    def _validate_text(
        value: str,
    ) -> bool:
        value = value.strip()

        if not value:
            return False

        if len(value) > 100:
            return False

        # Must contain at least one letter or digit.
        if not re.search(r"[\w]", value, re.UNICODE):
            return False

        return True

    @staticmethod
    def _validate_name(
        value: str,
    ) -> bool:
        value = value.strip()

        if not value:
            return False

        if len(value) > 50:
            return False

        # Letters with optional spaces, hyphens, and apostrophes.
        pattern = (
            r"^[^\W\d_]+"
            r"(?:[ '\-][^\W\d_]+)*$"
        )

        return bool(
            re.fullmatch(
                pattern,
                value,
                re.UNICODE,
            )
        )

    @staticmethod
    def _validate_age(
        value: str,
    ) -> bool:
        value = value.strip()

        if not value.isdigit():
            return False

        age = int(value)

        return 1 <= age <= 120

    # ========================================================
    # EXTRACT NAME
    # ========================================================

    @staticmethod
    def _extract_name(
        content: str,
    ) -> str | None:
        patterns = [
            r"\bmy name is\s+(.+?)",
            r"\bi'm\s+(?!(?:a|an)\b)([A-Za-z][A-Za-z0-9_-]*)",
            r"\bi am\s+(?!(?:a|an)\b)([A-Za-z][A-Za-z0-9_-]*)",
        ]

        for pattern in patterns:
            value = MemoryService._extract_value(
                content,
                pattern,
            )

            if value:
                return value

        return None

    # ========================================================
    # EXTRACT STUDY
    # ========================================================

    @staticmethod
    def _extract_study(
        content: str,
    ) -> str | None:
        patterns = [
            r"\bi study\s+(.+?)(?=\s+at\s+(?:the\s+|my\s+)?university\b|\s+(?:and\s+)?i\s+(?:live|speak|work)\b|[,.!?]|$)",
            r"\bi'm studying\s+(.+?)(?=\s+at\s+(?:the\s+|my\s+)?university\b|\s+(?:and\s+)?i\s+(?:live|speak|work)\b|[,.!?]|$)",
            r"\bi am studying\s+(.+?)(?=\s+at\s+(?:the\s+|my\s+)?university\b|\s+(?:and\s+)?i\s+(?:live|speak|work)\b|[,.!?]|$)",
            r"\bmy major is\s+(.+?)(?=\s+(?:and\s+)?i\s+(?:live|speak|work)\b|[,.!?]|$)",
            r"\bi'm a\s+(.+?)\s+student",
            r"\bi am a\s+(.+?)\s+student",
        ]

        for pattern in patterns:
            match = re.search(
                pattern,
                content,
                re.IGNORECASE,
            )

            if match:
                value = MemoryService._normalize_value(
                    match.group(1)
                )

                if value:
                    return value

        return None

    # ========================================================
    # EXTRACT LOCATION
    # ========================================================

    @staticmethod
    def _extract_location(
        content: str,
    ) -> str | None:
        patterns = [
            r"\bi\s+currently\s+live\s+in\s+(.+?)",
            r"\bi\s+live\s+in\s+(.+?)",
            r"\bi'm\s+currently\s+living\s+in\s+(.+?)",
            r"\bi'm\s+living\s+in\s+(.+?)",
            r"\bi am\s+currently\s+living\s+in\s+(.+?)",
            r"\bi am\s+living\s+in\s+(.+?)",
        ]

        for pattern in patterns:
            value = MemoryService._extract_value(
                content,
                pattern,
            )

            if value:
                return value

        return None
    # ========================================================
    # EXTRACT LANGUAGE
    # ========================================================

    @staticmethod
    def _extract_language(
        content: str,
    ) -> str | None:
        patterns = [
            r"\bi speak\s+(.+?)",
            r"\bi can speak\s+(.+?)",
        ]

        for pattern in patterns:
            value = MemoryService._extract_value(
                content,
                pattern,
            )

            if value:
                return value

        return None

    # ========================================================
    # EXTRACT JOB
    # ========================================================

    @staticmethod
    def _extract_job(
        content: str,
    ) -> str | None:
        patterns = [
            r"\bi work as\s+(?:a|an)\s+(.+?)(?=\s+at\s+|\s+(?:and\s+)?i\s+(?:study|live|speak|work)\b|[,.!?]|$)",
            r"\bi work as\s+(.+?)(?=\s+at\s+|\s+(?:and\s+)?i\s+(?:study|live|speak|work)\b|[,.!?]|$)",
            r"\bi'm\s+(?:a|an)\s+(.+?)(?=\s+at\s+|\s+(?:and\s+)?i\s+(?:study|live|speak|work)\b|[,.!?]|$)",
            r"\bi am\s+(?:a|an)\s+(.+?)(?=\s+at\s+|\s+(?:and\s+)?i\s+(?:study|live|speak|work)\b|[,.!?]|$)",
        ]

        for pattern in patterns:
            match = re.search(
                pattern,
                content,
                re.IGNORECASE,
            )

            if match:
                value = MemoryService._normalize_value(
                    match.group(1)
                )

                if value:
                    return value

        return None

    # ========================================================
    # EXTRACT AGE
    # ========================================================

    @staticmethod
    def _extract_age(
        content: str,
    ) -> str | None:
        patterns = [
            r"\bi am\s+(\d{1,3})\s+years old",
            r"\bi'm\s+(\d{1,3})\s+years old",
            r"\bi am\s+(\d{1,3})",
            r"\bi'm\s+(\d{1,3})",
        ]

        for pattern in patterns:
            value = MemoryService._extract_value(
                content,
                pattern,
            )

            if value and 1 <= int(value) <= 120:
                return value

        return None
import pytest

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.database import async_session, engine
from app.models.user_memory import UserMemory
from app.services.memory_service import MemoryService


# ========================================================
# UPDATE EXISTING MEMORY
# ========================================================

@pytest.mark.anyio
async def test_update_existing_memory():
    async with async_session() as db:
        try:
            service = MemoryService(
                db=db,
                user_id=3,
            )

            test_content = "The user studies __pytest_test__."

            await service.update_memory(
                memory_type="study",
                memory_content=test_content,
            )

            result = await db.execute(
                select(UserMemory).where(
                    UserMemory.user_id == 3,
                    UserMemory.memory_type == "study",
                )
            )

            memories = result.scalars().all()

            assert len(memories) == 1
            assert memories[0].content == test_content

        finally:
            await db.rollback()


# ========================================================
# INSERT NEW MEMORY
# ========================================================

@pytest.mark.anyio
async def test_insert_new_memory():
    async with async_session() as db:
        try:
            service = MemoryService(
                db=db,
                user_id=3,
            )

            await service.update_memory(
                memory_type="__pytest_new_type__",
                memory_content="__pytest_content__",
            )

            result = await db.execute(
                select(UserMemory).where(
                    UserMemory.user_id == 3,
                    UserMemory.memory_type == "__pytest_new_type__",
                )
            )

            memories = result.scalars().all()

            assert len(memories) == 1
            assert (
                memories[0].content
                == "__pytest_content__"
            )

        finally:
            await db.rollback()


# ========================================================
# NO DUPLICATE THROUGH MEMORY SERVICE
# ========================================================

@pytest.mark.anyio
async def test_update_memory_does_not_create_duplicate():
    async with async_session() as db:
        try:
            service = MemoryService(
                db=db,
                user_id=3,
            )

            await service.update_memory(
                memory_type="study",
                memory_content="The user studies __pytest_one__.",
            )

            await service.update_memory(
                memory_type="study",
                memory_content="The user studies __pytest_two__.",
            )

            result = await db.execute(
                select(UserMemory).where(
                    UserMemory.user_id == 3,
                    UserMemory.memory_type == "study",
                )
            )

            memories = result.scalars().all()

            assert len(memories) == 1
            assert (
                memories[0].content
                == "The user studies __pytest_two__."
            )

        finally:
            await db.rollback()


# ========================================================
# DATABASE UNIQUE CONSTRAINT
# ========================================================

@pytest.mark.anyio
async def test_database_rejects_duplicate_memory_type():
    async with async_session() as db:
        try:
            first_memory = UserMemory(
                user_id=3,
                memory_type="__pytest_unique__",
                content="first",
            )

            second_memory = UserMemory(
                user_id=3,
                memory_type="__pytest_unique__",
                content="second",
            )

            db.add(first_memory)

            await db.flush()

            db.add(second_memory)

            with pytest.raises(IntegrityError):
                await db.flush()

        finally:
            await db.rollback()
# ========================================================
# PROCESS MESSAGE - VALID MESSAGE
# ========================================================

@pytest.mark.anyio
async def test_process_message_updates_study():
    async with async_session() as db:
        try:
            service = MemoryService(
                db=db,
                user_id=3,
            )

            await service.process_message(
                "I'm studying __pytest_process__!!!"
            )

            result = await db.execute(
                select(UserMemory).where(
                    UserMemory.user_id == 3,
                    UserMemory.memory_type == "study",
                )
            )

            memories = result.scalars().all()

            assert len(memories) == 1

            assert (
                memories[0].content
                == "The user studies __pytest_process__."
            )

        finally:
            await db.rollback()


# ========================================================
# PROCESS MESSAGE - INVALID VALUE
# ========================================================

@pytest.mark.anyio
async def test_process_message_rejects_invalid_age():
    async with async_session() as db:
        try:
            service = MemoryService(
                db=db,
                user_id=3,
            )

            await service.process_message(
                "I am 999 years old."
            )

            result = await db.execute(
                select(UserMemory).where(
                    UserMemory.user_id == 3,
                    UserMemory.memory_type == "age",
                )
            )

            memories = result.scalars().all()

            assert len(memories) == 1

            assert (
                memories[0].content
                == "The user is 18 years old."
            )

        finally:
            await db.rollback()

@pytest.mark.anyio
async def test_process_message_updates_multiple_memories():
    async with async_session() as db:
        try:
            service = MemoryService(
                db=db,
                user_id=3,
            )

            await service.process_message(
                "My name is Ahmed and I study Physics and I live in Algeria."
            )

            result = await db.execute(
                select(UserMemory)
                .where(UserMemory.user_id == 3)
                .where(
                    UserMemory.memory_type.in_(
                        ["name", "study", "location"]
                    )
                )
                .order_by(UserMemory.memory_type)
            )

            memories = result.scalars().all()

            memory_map = {
                memory.memory_type: memory.content
                for memory in memories
            }

            assert memory_map["name"] == "The user's name is Ahmed."
            assert memory_map["study"] == "The user studies Physics."
            assert memory_map["location"] == "The user lives in Algeria."

        finally:
            await db.rollback()   


@pytest.mark.anyio
async def test_process_message_updates_multiple_memories_without_duplicates():
    async with async_session() as db:
        try:
            service = MemoryService(
                db=db,
                user_id=3,
            )

            await service.process_message(
                "My name is Ahmed and I study Physics."
            )

            await service.process_message(
                "My name is Ahmed and I study Computer Science."
            )

            result = await db.execute(
                select(UserMemory)
                .where(UserMemory.user_id == 3)
                .where(
                    UserMemory.memory_type.in_(
                        ["name", "study"]
                    )
                )
                .order_by(UserMemory.memory_type)
            )

            memories = result.scalars().all()

            memory_map = {
                memory.memory_type: memory.content
                for memory in memories
            }

            assert len(memories) == 2

            assert memory_map["name"] == (
                "The user's name is Ahmed."
            )

            assert memory_map["study"] == (
                "The user studies Computer Science."
            )

        finally:
            await db.rollback()

@pytest.mark.anyio
async def test_process_message_handles_multiple_memories_with_commas():
    async with async_session() as db:
        try:
            service = MemoryService(
                db=db,
                user_id=3,
            )

            await service.process_message(
                "My name is Ahmed, and I study Physics, and I live in Algeria."
            )

            result = await db.execute(
                select(UserMemory)
                .where(UserMemory.user_id == 3)
                .where(
                    UserMemory.memory_type.in_(
                        ["name", "study", "location"]
                    )
                )
                .order_by(UserMemory.memory_type)
            )

            memories = result.scalars().all()

            memory_map = {
                memory.memory_type: memory.content
                for memory in memories
            }

            assert len(memories) == 3

            assert memory_map["name"] == (
                "The user's name is Ahmed."
            )

            assert memory_map["study"] == (
                "The user studies Physics."
            )

            assert memory_map["location"] == (
                "The user lives in Algeria."
            )

        finally:
            await db.rollback()


@pytest.mark.anyio
async def test_process_message_updates_all_memory_types():
    async with async_session() as db:
        try:
            service = MemoryService(
                db=db,
                user_id=3,
            )

            await service.process_message(
                "My name is Ahmed, I study Computer Science, "
                "I live in Algeria, I speak Arabic, "
                "I work as a designer, and I am 18 years old."
            )

            result = await db.execute(
                select(UserMemory)
                .where(UserMemory.user_id == 3)
                .where(
                    UserMemory.memory_type.in_(
                        [
                            "name",
                            "study",
                            "location",
                            "language",
                            "profession",
                            "age",
                        ]
                    )
                )
                .order_by(UserMemory.memory_type)
            )

            memories = result.scalars().all()

            memory_map = {
                memory.memory_type: memory.content
                for memory in memories
            }

            assert len(memories) == 6

            assert memory_map["name"] == (
                "The user's name is Ahmed."
            )

            assert memory_map["study"] == (
                "The user studies Computer Science."
            )

            assert memory_map["location"] == (
                "The user lives in Algeria."
            )

            assert memory_map["language"] == (
                "The user speaks Arabic."
            )

            assert memory_map["profession"] == (
                "The user works as a designer."
            )

            assert memory_map["age"] == (
                "The user is 18 years old."
            )

        finally:
            await db.rollback()
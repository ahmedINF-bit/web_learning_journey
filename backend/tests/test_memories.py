from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.database import async_session
from app.core.database import get_db
from app.core.security import get_current_user
from app.main import app


# ========================================================
# TEST CONFIG
# ========================================================

TEST_USER_ID = 3


# ========================================================
# TEST DATABASE DEPENDENCY
# ========================================================

async def override_get_db():
    async with async_session() as db:

        async def test_commit():
            await db.flush()

        db.commit = test_commit

        try:
            yield db
        finally:
            await db.rollback()


# ========================================================
# TEST USER DEPENDENCY
# ========================================================

async def override_get_current_user():
    return SimpleNamespace(
        id=TEST_USER_ID
    )


# ========================================================
# FIXTURE
# ========================================================

@pytest.fixture
def client():
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = (
        override_get_current_user
    )

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


# ========================================================
# AUTHENTICATION
# ========================================================

def test_get_memories(client, monkeypatch):
    from app.api.v1.memories import MemoryService
    from types import SimpleNamespace

    async def fake_get_memories(self):
        return [
            SimpleNamespace(
                id=1,
                memory_type="name",
                content="The user's name is Ahmed.",
            ),
            SimpleNamespace(
                id=2,
                memory_type="study",
                content="The user studies Physics.",
            ),
            SimpleNamespace(
                id=3,
                memory_type="location",
                content="The user lives in Algeria.",
            ),
        ]

    monkeypatch.setattr(
        MemoryService,
        "get_memories",
        fake_get_memories,
    )

    response = client.get("/api/v1/memories")

    assert response.status_code == 200

    data = response.json()

    assert isinstance(data, list)
    assert len(data) == 3

    memory_types = {
        memory["memory_type"]
        for memory in data
    }

    assert memory_types == {
        "name",
        "study",
        "location",
    }


# ========================================================
# GET MEMORIES
# ========================================================

def test_get_memories(client, monkeypatch):
    from types import SimpleNamespace
    from app.api.v1.memories import MemoryService

    async def fake_get_memories(self):
        return [
            SimpleNamespace(
                id=1,
                memory_type="name",
                content="The user's name is Ahmed.",
            ),
            SimpleNamespace(
                id=2,
                memory_type="study",
                content="The user studies Physics.",
            ),
            SimpleNamespace(
                id=3,
                memory_type="location",
                content="The user lives in Algeria.",
            ),
        ]

    monkeypatch.setattr(
        MemoryService,
        "get_memories",
        fake_get_memories,
    )

    response = client.get("/api/v1/memories")

    assert response.status_code == 200

    data = response.json()

    assert isinstance(data, list)
    assert len(data) == 3

    memory_types = {
        memory["memory_type"]
        for memory in data
    }

    assert memory_types == {"name", "study", "location"}


# ========================================================
# DELETE NON-EXISTING MEMORY
# ========================================================

def test_delete_non_existing_memory(client):
    response = client.delete(
        "/api/v1/memories/__pytest_non_existing_memory__"
    )

    assert response.status_code == 404

    data = response.json()

    assert data["detail"] == "Memory not found"


# ========================================================
# DELETE EXISTING MEMORY
# ========================================================

def test_delete_existing_memory(client):
    from app.api.v1.memories import MemoryService

    original_delete_memory = MemoryService.delete_memory

    async def fake_delete_memory(
        self,
        memory_type: str,
    ) -> bool:
        assert memory_type == "__pytest_delete_test__"
        return True

    MemoryService.delete_memory = fake_delete_memory

    try:
        response = client.delete(
            "/api/v1/memories/__pytest_delete_test__"
        )

        assert response.status_code == 204
        assert response.content == b""

    finally:
        MemoryService.delete_memory = original_delete_memory


# ========================================================
# MEMORY RESPONSE
# ========================================================

def test_get_memories_returns_only_current_user_memories(client):
    response = client.get(
        "/api/v1/memories"
    )

    assert response.status_code == 200

    data = response.json()

    assert isinstance(data, list)

    for memory in data:
        assert "memory_type" in memory
        assert "content" in memory
        assert "id" in memory


# ========================================================
# MEMORY ISOLATION
# ========================================================

def test_get_memories_uses_current_user_id(client, monkeypatch):
    from app.api.v1.memories import MemoryService

    captured_user_ids = []

    async def fake_get_memories(self):
        captured_user_ids.append(self.user_id)
        return []

    monkeypatch.setattr(
        MemoryService,
        "get_memories",
        fake_get_memories,
    )

    response = client.get(
        "/api/v1/memories"
    )

    assert response.status_code == 200
    assert response.json() == []

    assert captured_user_ids == [TEST_USER_ID]


# ========================================================
# UPDATE MEMORY
# ========================================================

def test_update_existing_memory(client, monkeypatch):
    class FakeMemory:
        id = 1
        memory_type = "study"
        content = "The user studies Computer Science."

    async def fake_update_memory(
        self,
        memory_type,
        memory_content,
    ):
        assert memory_type == "study"
        assert memory_content == (
            "The user studies Computer Science."
        )
        return FakeMemory()

    monkeypatch.setattr(
        "app.api.v1.memories.MemoryService.update_memory",
        fake_update_memory,
    )

    response = client.put(
        "/api/v1/memories/study",
        json={
            "content": "The user studies Computer Science."
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "id": 1,
        "memory_type": "study",
        "content": "The user studies Computer Science.",
    }


def test_update_missing_memory_returns_404(client, monkeypatch):
    async def fake_update_memory(
        self,
        memory_type,
        memory_content,
    ):
        return None

    monkeypatch.setattr(
        "app.api.v1.memories.MemoryService.update_memory",
        fake_update_memory,
    )

    response = client.put(
        "/api/v1/memories/study",
        json={
            "content": "The user studies Computer Science."
        },
    )

    assert response.status_code == 404
    assert response.json() == {
        "detail": "Memory not found"
    }


def test_update_memory_empty_content_returns_422(client):
    response = client.put(
        "/api/v1/memories/study",
        json={
            "content": ""
        },
    )

    assert response.status_code == 422


def test_update_memory_missing_content_returns_422(client):
    response = client.put(
        "/api/v1/memories/study",
        json={},
    )

    assert response.status_code == 422


def test_update_memory_uses_current_user_id(client, monkeypatch):
    from app.api.v1.memories import MemoryService

    captured_user_ids = []

    async def fake_update_memory(
        self,
        memory_type,
        memory_content,
    ):
        captured_user_ids.append(self.user_id)

        return SimpleNamespace(
            id=1,
            memory_type=memory_type,
            content=memory_content,
        )

    monkeypatch.setattr(
        MemoryService,
        "update_memory",
        fake_update_memory,
    )

    response = client.put(
        "/api/v1/memories/study",
        json={
            "content": "The user studies Computer Science."
        },
    )

    assert response.status_code == 200
    assert captured_user_ids == [TEST_USER_ID]

def test_update_memory_content_too_long_returns_422(client):
    response = client.put(
        "/api/v1/memories/study",
        json={
            "content": "a" * 501
        },
    )

    assert response.status_code == 422
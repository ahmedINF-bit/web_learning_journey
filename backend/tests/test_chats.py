from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import async_session
from app.core.database import get_db
from app.core.security import get_current_user
from app.services.subscription_service import enforce_ai_quota
from app.main import app
from app.models.chat import Message
from app.models.user_memory import UserMemory


# ========================================================
# TEST CONFIG
# ========================================================

TEST_USER_ID = 3
TEST_CHAT_ID = 14


# ========================================================
# FAKE AI SERVICE
# ========================================================

class FakeAIService:
    last_messages = None
    last_model = None
    last_temperature = None
    last_max_tokens = None

    def __init__(self, api_key=None):
        self.api_key = api_key

    async def chat(
        self,
        messages,
        model=None,
        temperature=0.7,
        max_tokens=2048,
    ):
        FakeAIService.last_messages = messages
        FakeAIService.last_model = model
        FakeAIService.last_temperature = temperature
        FakeAIService.last_max_tokens = max_tokens

        return "Mocked AI response"


# ========================================================
# TEST DATABASE DEPENDENCY
# ========================================================

async def override_get_db():
    async with async_session() as db:

        # The real endpoint calls db.commit().
        # For tests, replace commit with flush so
        # everything can be rolled back at the end.
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
# FIXTURES
# ========================================================

async def allow_ai_quota_for_endpoint_tests():
    return None


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(
        "app.api.v1.chats.AIService",
        FakeAIService,
    )

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[enforce_ai_quota] = allow_ai_quota_for_endpoint_tests
    app.dependency_overrides[get_current_user] = (
        override_get_current_user
    )

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        FakeAIService.last_messages = None
        FakeAIService.last_model = None
        FakeAIService.last_temperature = None
        FakeAIService.last_max_tokens = None


# ========================================================
# SEND MESSAGE - SUCCESS
# ========================================================

def test_send_message_with_mocked_ai(client):
    response = client.post(
        f"/api/v1/chats/{TEST_CHAT_ID}/messages",
        json={
            "content": "Hello from integration test",
            "temperature": 0.7,
            "max_tokens": 100,
        },
    )

    assert response.status_code == 200

    data = response.json()

    assert data["role"] == "assistant"
    assert data["content"] == "Mocked AI response"


# ========================================================
# SEND MESSAGE - AI RECEIVES MEMORY CONTEXT
# ========================================================

def test_send_message_sends_memory_to_ai(client):
    response = client.post(
        f"/api/v1/chats/{TEST_CHAT_ID}/messages",
        json={
            "content": "What do I study?",
            "temperature": 0.7,
            "max_tokens": 100,
        },
    )

    assert response.status_code == 200

    messages = FakeAIService.last_messages

    assert messages is not None

    system_messages = [
        message
        for message in messages
        if message["role"] == "system"
    ]

    assert len(system_messages) == 1

    system_content = system_messages[0]["content"]

    assert "CURRENT USER MEMORIES" in system_content
    assert "The user studies Physics." in system_content


# ========================================================
# SEND MESSAGE - HISTORY ENDS WITH USER
# ========================================================

def test_send_message_history_ends_with_current_user(client):
    response = client.post(
        f"/api/v1/chats/{TEST_CHAT_ID}/messages",
        json={
            "content": "Test current user message",
            "temperature": 0.7,
            "max_tokens": 100,
        },
    )

    assert response.status_code == 200

    messages = FakeAIService.last_messages

    assert messages is not None
    assert messages[-1]["role"] == "user"
    assert (
        messages[-1]["content"]
        == "Test current user message"
    )


# ========================================================
# SEND MESSAGE - REQUEST PARAMETERS
# ========================================================

def test_send_message_passes_parameters_to_ai(client):
    response = client.post(
        f"/api/v1/chats/{TEST_CHAT_ID}/messages",
        json={
            "content": "Parameter test",
            "temperature": 0.3,
            "max_tokens": 123,
        },
    )

    assert response.status_code == 200

    assert FakeAIService.last_temperature == 0.3
    assert FakeAIService.last_max_tokens == 123

# ========================================================
# SEND MESSAGE - AI RECEIVES MULTIPLE MEMORIES
# ========================================================

def test_send_message_sends_multiple_memories_to_ai(client, monkeypatch):
    from app.services.memory_service import MemoryService

    async def seed_test_memories(self, content):
        test_memories = [
            ("name", "The user's name is Ahmed."),
            ("study", "The user studies Physics."),
            ("location", "The user lives in Algeria."),
        ]

        for memory_type, memory_content in test_memories:
            await self.update_memory(memory_type, memory_content)

    monkeypatch.setattr(
        MemoryService,
        "process_message",
        seed_test_memories,
    )

    response = client.post(
        f"/api/v1/chats/{TEST_CHAT_ID}/messages",
        json={
            "content": "Tell me what you know about me.",
            "temperature": 0.7,
            "max_tokens": 100,
        },
    )

    assert response.status_code == 200

    messages = FakeAIService.last_messages

    assert messages is not None

    system_messages = [
        message
        for message in messages
        if message["role"] == "system"
    ]

    assert len(system_messages) == 1

    system_content = system_messages[0]["content"]

    assert "CURRENT USER MEMORIES" in system_content
    assert "The user's name is Ahmed." in system_content
    assert "The user studies Physics." in system_content
    assert "The user lives in Algeria." in system_content
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.database import get_db
from app.core.security import get_current_user
from app.main import app
from app.models.code_file import CodeFile
from app.models.code_project import CodeProject


TEST_USER_ID = 701
TEST_PROJECT_ID = 801


class FakeResult:
    def __init__(self, rows):
        self.rows = rows

    def scalar_one_or_none(self):
        return self.rows[0] if self.rows else None

    def scalars(self):
        return self

    def all(self):
        return list(self.rows)


class FakeDB:
    def __init__(self, state):
        self.state = state

    async def execute(self, statement):
        entity = statement.column_descriptions[0]["entity"]
        if entity is CodeProject:
            candidates = [self.state["project"]] if self.state["project"] else []
        elif entity is CodeFile:
            candidates = list(self.state["files"])
        else:
            raise AssertionError(f"Unexpected query entity: {entity}")

        for condition in getattr(statement, "_where_criteria", ()):
            if not hasattr(condition, "left") or not hasattr(condition, "right"):
                continue
            key = getattr(condition.left, "key", None)
            expected = getattr(condition.right, "value", None)
            candidates = [item for item in candidates if getattr(item, key, None) == expected]
        return FakeResult(candidates)

    def add(self, obj):
        if isinstance(obj, CodeFile):
            obj.id = self.state["next_file_id"]
            self.state["next_file_id"] += 1
            obj.created_at = datetime.now(timezone.utc)
            obj.updated_at = obj.created_at
            self.state["files"].append(obj)
        else:
            raise AssertionError(f"Unexpected object added: {type(obj)}")

    async def commit(self):
        now = datetime.now(timezone.utc)
        for item in self.state["files"]:
            if getattr(item, "updated_at", None) is None:
                item.updated_at = now

    async def refresh(self, _obj):
        return None

    async def delete(self, obj):
        self.state["files"] = [item for item in self.state["files"] if item.id != obj.id]

    async def rollback(self):
        return None


@pytest.fixture
def code_files_client(monkeypatch):
    state = {
        "project": SimpleNamespace(
            id=TEST_PROJECT_ID,
            user_id=TEST_USER_ID,
            name="main.c",
            language="c",
            code="int main(void) { return 0; }",
        ),
        "files": [],
        "next_file_id": 1,
    }

    async def override_get_db():
        yield FakeDB(state)

    async def override_get_current_user():
        return SimpleNamespace(id=TEST_USER_ID)

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    try:
        with TestClient(app) as client:
            yield client, state
    finally:
        app.dependency_overrides.clear()


def test_create_and_list_project_code_files(code_files_client):
    client, _state = code_files_client
    response = client.post(
        f"/api/v1/code-projects/{TEST_PROJECT_ID}/files",
        json={"name": "utils.c", "language": "c", "code": "int add(int a, int b) { return a + b; }"},
    )
    assert response.status_code == 201
    created = response.json()
    assert created["name"] == "utils.c"
    assert created["language"] == "c"
    assert created["project_id"] == TEST_PROJECT_ID

    listed = client.get(f"/api/v1/code-projects/{TEST_PROJECT_ID}/files")
    assert listed.status_code == 200
    assert [item["name"] for item in listed.json()] == ["utils.c"]


def test_update_and_delete_project_code_file(code_files_client):
    client, _state = code_files_client
    created = client.post(
        f"/api/v1/code-projects/{TEST_PROJECT_ID}/files",
        json={"name": "helpers.py", "language": "python", "code": "print('before')"},
    )
    assert created.status_code == 201
    file_id = created.json()["id"]

    updated = client.put(
        f"/api/v1/code-projects/{TEST_PROJECT_ID}/files/{file_id}",
        json={"code": "print('after')"},
    )
    assert updated.status_code == 200
    assert updated.json()["code"] == "print('after')"

    deleted = client.delete(f"/api/v1/code-projects/{TEST_PROJECT_ID}/files/{file_id}")
    assert deleted.status_code == 200
    assert deleted.json()["message"] == "Code file deleted."
    assert client.get(f"/api/v1/code-projects/{TEST_PROJECT_ID}/files").json() == []


def test_rejects_language_extension_mismatch(code_files_client):
    client, _state = code_files_client
    response = client.post(
        f"/api/v1/code-projects/{TEST_PROJECT_ID}/files",
        json={"name": "helpers.py", "language": "c", "code": ""},
    )
    assert response.status_code == 422


def test_rejects_duplicate_file_name_in_project(code_files_client):
    client, _state = code_files_client
    payload = {"name": "utils.c", "language": "c", "code": ""}
    assert client.post(f"/api/v1/code-projects/{TEST_PROJECT_ID}/files", json=payload).status_code == 201
    duplicate = client.post(f"/api/v1/code-projects/{TEST_PROJECT_ID}/files", json=payload)
    assert duplicate.status_code == 409


def test_does_not_allow_access_to_another_users_project(code_files_client):
    client, state = code_files_client
    state["project"].user_id = TEST_USER_ID + 1
    response = client.get(f"/api/v1/code-projects/{TEST_PROJECT_ID}/files")
    assert response.status_code == 404


def test_rejects_name_used_by_main_project_file(code_files_client):
    client, _state = code_files_client
    response = client.post(
        f"/api/v1/code-projects/{TEST_PROJECT_ID}/files",
        json={"name": "main.c", "language": "c", "code": ""},
    )
    assert response.status_code == 409

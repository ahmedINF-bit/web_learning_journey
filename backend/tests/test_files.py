
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.database import get_db
from app.core.security import get_current_user
from app.main import app
from app.services.subscription_service import enforce_ai_quota
import os
from datetime import datetime, timezone

from app.core.config import settings
from app.models.file import File
from app.services.file_service import FileService

TEST_USER_ID = 3
TEST_FILE_ID = 12


class FakeScalarRows:
    def __init__(self, value):
        self.value = value

    def all(self):
        return [] if self.value is None else [self.value]


class FakeResult:
    def __init__(self, value):
        self.value = value

    def scalar_one_or_none(self):
        return self.value

    def scalars(self):
        return FakeScalarRows(self.value)


@pytest.fixture
def files_client(monkeypatch):
    state = {
        "file": SimpleNamespace(
            id=TEST_FILE_ID,
            user_id=TEST_USER_ID,
            filename="lecture.txt",
            original_name="lecture.txt",
            file_type="txt",
            file_size=120,
            created_at=datetime.now(timezone.utc),
            extracted_text=(
                "Loi de Moore: the number of transistors doubles "
                "every 18 months according to these study notes."
            ),
        ),
        "deleted_files": [],
        "messages": None,
        "fail_ai": False,
    }

    
    class FakeDB:
        async def execute(self, statement):
            db_file = state["file"]

            if db_file is None:
                return FakeResult(None)

            for condition in getattr(statement, "_where_criteria", ()):
                column_name = getattr(condition.left, "key", None)
                expected_value = getattr(condition.right, "value", None)

                if column_name in ("id", "user_id"):
                    if getattr(db_file, column_name, None) != expected_value:
                        return FakeResult(None)

            return FakeResult(db_file)

        async def delete(self, db_file):
            state["deleted_files"].append(db_file)

            if state["file"] is db_file:
                state["file"] = None

        async def commit(self):
            pass

            

    class FakeAIService:
        def __init__(self, api_key=None):
            self.api_key = api_key

        async def chat(
            self,
            messages,
            model=None,
            temperature=0.7,
            max_tokens=2048,
        ):
            state["messages"] = messages

            if state["fail_ai"]:
                raise RuntimeError("Simulated AI failure")

            return "Mocked AI response"

    async def override_get_db():
        yield FakeDB()

    async def override_current_user():
        return SimpleNamespace(id=TEST_USER_ID)

    async def allow_ai_quota():
        return None

    monkeypatch.setattr(
        "app.api.v1.files.AIService",
        FakeAIService,
    )
    monkeypatch.setattr(
        settings,
        "GEMINI_API_KEY",
        "test-api-key",
    )

    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_current_user
    app.dependency_overrides[enforce_ai_quota] = allow_ai_quota

    try:
        with TestClient(app) as client:
            yield client, state
    finally:
        app.dependency_overrides.clear()


def test_ask_about_file_returns_ai_response(files_client):
    client, state = files_client

    response = client.post(
        "/api/v1/files/ask",
        json={
            "file_id": TEST_FILE_ID,
            "question": "Summarize this document.",
        },
    )

    assert response.status_code == 200
    assert response.json()["content"] == "Mocked AI response"
    assert state["messages"] is not None
    assert "Summarize this document." in state["messages"][1]["content"]
    assert "Loi de Moore" in state["messages"][1]["content"]


def test_ask_about_missing_file_returns_404(files_client):
    client, state = files_client
    state["file"] = None

    response = client.post(
        "/api/v1/files/ask",
        json={
            "file_id": TEST_FILE_ID,
            "question": "Summarize this document.",
        },
    )

    assert response.status_code == 404


@pytest.mark.parametrize(
    "extracted_text",
    [
        None,
        "",
        "   ",
    ],
)
def test_ask_about_file_without_readable_text_returns_400(
    files_client,
    extracted_text,
):
    client, state = files_client
    state["file"].extracted_text = extracted_text

    response = client.post(
        "/api/v1/files/ask",
        json={
            "file_id": TEST_FILE_ID,
            "question": "Summarize this document.",
        },
    )

    assert response.status_code == 400


def test_ask_about_file_with_extraction_error_returns_400(files_client):
    client, state = files_client
    state["file"].extracted_text = "Error extracting text: test error"

    response = client.post(
        "/api/v1/files/ask",
        json={
            "file_id": TEST_FILE_ID,
            "question": "Summarize this document.",
        },
    )

    assert response.status_code == 400
    assert "extract" in response.json()["detail"].lower()


def test_ask_about_file_returns_502_if_ai_fails(files_client):
    client, state = files_client
    state["fail_ai"] = True

    response = client.post(
        "/api/v1/files/ask",
        json={
            "file_id": TEST_FILE_ID,
            "question": "Explain this document.",
        },
    )

    assert response.status_code == 502


@pytest.mark.parametrize(
    "tool",
    [
        "summarize",
        "quiz",
        "flashcards",
        "solve-math",
    ],
)
def test_study_tool_accepts_supported_tools(files_client, tool):
    client, state = files_client

    response = client.post(
        "/api/v1/files/study-tool",
        json={
            "file_id": TEST_FILE_ID,
            "tool": tool,
        },
    )

    assert response.status_code == 200
    assert response.json()["content"] == "Mocked AI response"
    assert state["messages"] is not None
    assert "Loi de Moore" in state["messages"][1]["content"]


def test_study_tool_returns_404_for_missing_file(files_client):
    client, state = files_client
    state["file"] = None

    response = client.post(
        "/api/v1/files/study-tool",
        json={
            "file_id": TEST_FILE_ID,
            "tool": "summarize",
        },
    )

    assert response.status_code == 404


def test_study_tool_returns_400_for_empty_document(files_client):
    client, state = files_client
    state["file"].extracted_text = "   "

    response = client.post(
        "/api/v1/files/study-tool",
        json={
            "file_id": TEST_FILE_ID,
            "tool": "summarize",
        },
    )

    assert response.status_code == 400


def test_study_tool_returns_400_for_extraction_error(files_client):
    client, state = files_client
    state["file"].extracted_text = "Error extracting text: test error"

    response = client.post(
        "/api/v1/files/study-tool",
        json={
            "file_id": TEST_FILE_ID,
            "tool": "summarize",
        },
    )

    assert response.status_code == 400


def test_study_tool_returns_502_if_ai_fails(files_client):
    client, state = files_client
    state["fail_ai"] = True

    response = client.post(
        "/api/v1/files/study-tool",
        json={
            "file_id": TEST_FILE_ID,
            "tool": "solve-math",
        },
    )

    assert response.status_code == 502

def test_ask_about_another_users_file_returns_404(files_client):
    client, state = files_client
    state["file"].user_id = TEST_USER_ID + 1

    response = client.post(
        "/api/v1/files/ask",
        json={
            "file_id": TEST_FILE_ID,
            "question": "Summarize this document.",
        },
    )

    assert response.status_code == 404

@pytest.fixture
def upload_files_client(monkeypatch, tmp_path):
    state = {
        "added_files": [],
        "extraction_calls": [],
    }

    class FakeUploadDB:
        def add(self, db_file):
            state["added_files"].append(db_file)

        async def flush(self):
            for index, db_file in enumerate(state["added_files"]):
                if db_file.id is None:
                    db_file.id = 700 + index

                if db_file.created_at is None:
                    db_file.created_at = datetime.now(timezone.utc)

        async def refresh(self, db_file):
            if db_file.id is None:
                db_file.id = 700

            if db_file.created_at is None:
                db_file.created_at = datetime.now(timezone.utc)

        async def commit(self):
            pass

    async def override_db():
        yield FakeUploadDB()

    async def override_current_user():
        return SimpleNamespace(
            id=TEST_USER_ID,
            openai_api_key=None,
        )

    upload_dir = tmp_path / "uploads"
    monkeypatch.setattr(settings, "UPLOAD_DIR", str(upload_dir))
    monkeypatch.setattr(
        settings,
        "MAX_FILE_SIZE",
        10 * 1024 * 1024,
    )

    def fake_extract_text(filepath, ext):
        state["extraction_calls"].append((filepath, ext))
        return "Extracted sample text"

    monkeypatch.setattr(
        "app.api.v1.files.FileService.extract_text",
        fake_extract_text,
    )

    app.dependency_overrides.clear()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_current_user

    try:
        with TestClient(app) as client:
            yield client, state, upload_dir
    finally:
        app.dependency_overrides.clear()

@pytest.mark.parametrize(
    ("filename", "content_type", "extension"),
    [
        ("lecture.pdf", "application/pdf", ".pdf"),
        (
            "lecture.docx",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            ".docx",
        ),
        ("lecture.txt", "text/plain", ".txt"),
        ("lecture.md", "text/markdown", ".md"),
    ],
)
def test_upload_supported_file_types(
    upload_files_client,
    filename,
    content_type,
    extension,
):
    client, state, upload_dir = upload_files_client

    response = client.post(
        "/api/v1/files/upload",
        files={
            "file": (
                filename,
                b"sample document content",
                content_type,
            )
        },
    )

    assert response.status_code == 200

    data = response.json()
    assert data["original_name"] == filename
    assert data["file_type"] == extension.lstrip(".")
    assert data["file_size"] == len(b"sample document content")

    assert len(state["added_files"]) == 1
    assert state["added_files"][0].extracted_text == (
        "Extracted sample text"
    )

    assert len(state["extraction_calls"]) == 1
    filepath, extracted_extension = state["extraction_calls"][0]

    assert extracted_extension == extension
    assert os.path.exists(filepath)
    assert str(upload_dir) in filepath

def test_upload_rejects_unsupported_file_type(upload_files_client):
    client, state, _ = upload_files_client

    response = client.post(
        "/api/v1/files/upload",
        files={
            "file": (
                "program.exe",
                b"not a supported document",
                "application/octet-stream",
            )
        },
    )

    assert response.status_code == 400
    assert "not supported" in response.json()["detail"].lower()
    assert state["added_files"] == []
    assert state["extraction_calls"] == []

def test_upload_rejects_file_larger_than_limit(
    upload_files_client,
    monkeypatch,
):
    client, state, _ = upload_files_client

    monkeypatch.setattr(settings, "MAX_FILE_SIZE", 4)

    response = client.post(
        "/api/v1/files/upload",
        files={
            "file": (
                "large.txt",
                b"12345",
                "text/plain",
            )
        },
    )

    assert response.status_code == 400
    assert "too large" in response.json()["detail"].lower()
    assert state["added_files"] == []
    assert state["extraction_calls"] == []


def test_list_files_returns_current_users_files(files_client):
    client, state = files_client

    response = client.get("/api/v1/files")

    assert response.status_code == 200
    data = response.json()

    assert len(data) == 1
    assert data[0]["id"] == TEST_FILE_ID
    assert data[0]["original_name"] == "lecture.txt"


def test_list_files_does_not_return_another_users_file(files_client):
    client, state = files_client
    state["file"].user_id = TEST_USER_ID + 1

    response = client.get("/api/v1/files")

    assert response.status_code == 200
    assert response.json() == []


def test_delete_file_removes_database_record_and_disk_file(
    files_client,
    monkeypatch,
    tmp_path,
):
    client, state = files_client

    monkeypatch.setattr(settings, "UPLOAD_DIR", str(tmp_path))

    user_dir = tmp_path / str(TEST_USER_ID)
    user_dir.mkdir(parents=True)

    stored_file = user_dir / state["file"].filename
    stored_file.write_text("sample file", encoding="utf-8")

    response = client.delete(f"/api/v1/files/{TEST_FILE_ID}")

    assert response.status_code == 200
    assert response.json()["message"] == "File deleted"
    assert not stored_file.exists()
    assert len(state["deleted_files"]) == 1
    assert state["deleted_files"][0].id == TEST_FILE_ID
    assert state["file"] is None


def test_delete_file_returns_404_for_another_users_file(files_client):
    client, state = files_client
    state["file"].user_id = TEST_USER_ID + 1

    response = client.delete(f"/api/v1/files/{TEST_FILE_ID}")

    assert response.status_code == 404
    assert state["deleted_files"] == []
    assert state["file"] is not None


def test_delete_missing_file_returns_404(files_client):
    client, state = files_client
    state["file"] = None

    response = client.delete(f"/api/v1/files/{TEST_FILE_ID}")

    assert response.status_code == 404
    assert state["deleted_files"] == []


@pytest.mark.parametrize(
    ("extension", "filename"),
    [
        (".txt", "notes.txt"),
        (".md", "notes.md"),
    ],
)
def test_extract_text_from_plain_text_files(
    tmp_path,
    extension,
    filename,
):
    expected = "Résumé du cours\nالمعالج الدقيق"
    path = tmp_path / filename
    path.write_text(expected, encoding="utf-8")

    extracted = FileService.extract_text(str(path), extension)

    assert extracted == expected


def test_extract_text_returns_none_for_unsupported_extension(tmp_path):
    path = tmp_path / "notes.csv"
    path.write_text("a,b,c", encoding="utf-8")

    assert FileService.extract_text(str(path), ".csv") is None


@pytest.mark.parametrize(
    ("extension", "filename"),
    [
        (".pdf", "broken.pdf"),
        (".docx", "broken.docx"),
    ],
)
def test_extract_text_handles_invalid_documents(
    tmp_path,
    extension,
    filename,
):
    path = tmp_path / filename
    path.write_text("This is not a valid document", encoding="utf-8")

    extracted = FileService.extract_text(str(path), extension)

    assert (
        extracted is None
        or (
            isinstance(extracted, str)
            and extracted.startswith("Error extracting text:")
        )
    )
def test_extract_text_from_real_pdf(tmp_path):
    import fitz

    from app.services.file_service import FileService

    pdf_path = tmp_path / "microprocessor.pdf"

    document = fitz.open()
    page = document.new_page()

    page.insert_text(
        (72, 72),
        "Microprocessor study notes: Moore law.",
    )

    document.save(str(pdf_path))
    document.close()

    extracted = FileService.extract_text(
        str(pdf_path),
        ".pdf",
    )

    assert extracted is not None
    assert "Microprocessor study notes" in extracted
    assert "Moore law" in extracted

def test_extract_text_from_real_docx(tmp_path):
    from docx import Document

    from app.services.file_service import FileService

    docx_path = tmp_path / "microprocessor.docx"

    document = Document()
    document.add_paragraph("Microprocessor")
    document.add_paragraph(
        "Moore law doubles transistor count every 18 months."
    )
    document.save(str(docx_path))

    extracted = FileService.extract_text(
        str(docx_path),
        ".docx",
    )

    assert extracted is not None
    assert "Microprocessor" in extracted
    assert "Moore law doubles transistor count every 18 months." in extracted

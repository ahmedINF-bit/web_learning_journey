import asyncio
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.schemas.code_execution import CodeExecutionRequest, CodeExecutionResponse
from app.services import code_runner


def test_multi_file_c_request_accepts_source_and_header_files():
    request = CodeExecutionRequest(
        language="c",
        code="int main(void) { return 0; }",
        source_files=[
            {"name": "main.c", "code": "int main(void) { return 0; }"},
            {"name": "utils.c", "code": "int sum(int a, int b) { return a + b; }"},
            {"name": "utils.h", "code": "int sum(int a, int b);"},
        ],
    )
    assert [item.name for item in request.source_files] == ["main.c", "utils.c", "utils.h"]


def test_source_file_names_cannot_escape_workspace():
    with pytest.raises(ValidationError):
        CodeExecutionRequest(
            language="c",
            code="int main(void) { return 0; }",
            source_files=[{"name": "../utils.c", "code": "int sum(void) { return 1; }"}],
        )


def test_source_file_names_must_be_unique_case_insensitively():
    with pytest.raises(ValidationError):
        CodeExecutionRequest(
            language="c",
            code="int main(void) { return 0; }",
            source_files=[
                {"name": "main.c", "code": "int main(void) { return 0; }"},
                {"name": "MAIN.C", "code": "int main(void) { return 0; }"},
            ],
        )


def test_additional_source_files_are_c_only():
    with pytest.raises(ValidationError):
        CodeExecutionRequest(
            language="python",
            code="print('hello')",
            source_files=[{"name": "main.c", "code": "int main(void) { return 0; }"}],
        )


def test_c_runner_compiles_all_c_source_files():
    command = code_runner._runner_command("c")
    assert "/workspace/*.c" in command[-1]
    assert "-std=c11" in command[-1]


def test_python_runner_keeps_single_file_execution():
    command = code_runner._runner_command("python")
    assert "/workspace/main.py" in command[-1]
    assert "/workspace/*.c" not in command[-1]


def test_execute_code_writes_all_named_sources(monkeypatch, tmp_path):
    captured: dict[str, str] = {}

    async def fake_execute_container(workspace: Path, language: str, stdin: str = ""):
        captured.update({path.name: path.read_text(encoding="utf-8") for path in workspace.iterdir()})
        assert language == "c"
        assert stdin == ""
        return CodeExecutionResponse(status="success", stdout="7\n", exit_code=0, duration_ms=1)

    monkeypatch.setattr(code_runner, "RUN_TEMP_ROOT", tmp_path)
    monkeypatch.setattr(code_runner, "_execute_container", fake_execute_container)

    request = CodeExecutionRequest(
        language="c",
        code="int main(void) { return 0; }",
        source_files=[
            {"name": "main.c", "code": "int main(void) { return sum(3, 4) == 7 ? 0 : 1; }"},
            {"name": "utils.c", "code": "int sum(int a, int b) { return a + b; }"},
        ],
    )

    result = asyncio.run(
        code_runner.execute_code(
            request.language,
            request.code,
            request.stdin,
            request.source_files,
        )
    )

    assert result.status == "success"
    assert captured == {
        "main.c": "int main(void) { return sum(3, 4) == 7 ? 0 : 1; }",
        "utils.c": "int sum(int a, int b) { return a + b; }",
    }
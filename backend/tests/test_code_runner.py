import pytest
from pydantic import ValidationError

from app.schemas.code_execution import CodeExecutionRequest
from app.services.code_runner import (
    COMPILE_FAILURE_MARKER,
    _docker_unavailable_message,
    _runner_command,
    parse_diagnostics,
)


def test_c_compiler_diagnostic_parses_line_and_column():
    stderr = (
        "/workspace/main.c:5:19: error: "
        "expected ')' before 'return'\n"
    )

    diagnostics = parse_diagnostics("c", stderr)

    assert len(diagnostics) == 1
    assert diagnostics[0].line == 5
    assert diagnostics[0].column == 19
    assert diagnostics[0].severity == "error"
    assert "expected" in diagnostics[0].message


def test_c_diagnostic_preserves_secondary_source_filename():
    stderr = "/workspace/utils.c:8:5: error: expected expression\n"

    diagnostics = parse_diagnostics("c", stderr)

    assert len(diagnostics) == 1
    assert diagnostics[0].file == "utils.c"
    assert diagnostics[0].line == 8
    assert diagnostics[0].column == 5


def test_c_diagnostic_supports_header_filename():
    stderr = "/workspace/utils.h:4:7: error: unknown type name 'Thing'\n"

    diagnostics = parse_diagnostics("c", stderr)

    assert len(diagnostics) == 1
    assert diagnostics[0].file == "utils.h"
    assert diagnostics[0].line == 4
    assert diagnostics[0].column == 7


def test_c_runner_command_compiles_and_marks_compile_failure():
    command = " ".join(_runner_command("c"))

    assert "gcc -std=c11" in command
    assert COMPILE_FAILURE_MARKER in command
    assert "timeout --signal=KILL 3s" in command


def test_python_runner_command_has_timeout_and_isolated_mode():
    command = " ".join(_runner_command("python"))

    assert "timeout --signal=KILL 3s" in command
    assert "python3 -I -S /workspace/main.py" in command


def test_javascript_runner_command_has_timeout():
    command = " ".join(_runner_command("javascript"))

    assert "timeout --signal=KILL 3s" in command
    assert "node /workspace/main.js" in command


def test_all_runner_commands_use_program_timeout():
    for language in ("c", "python", "javascript"):
        assert "timeout --signal=KILL 3s" in " ".join(_runner_command(language))


def test_python_and_javascript_are_supported_languages():
    assert CodeExecutionRequest(language="python", code="print(input())").language == "python"
    assert CodeExecutionRequest(language="javascript", code="console.log('ok')").language == "javascript"


def test_standard_input_defaults_to_empty_string():
    request = CodeExecutionRequest(language="python", code="print('ok')")
    assert request.stdin == ""


def test_standard_input_is_limited_to_16_kb():
    with pytest.raises(ValidationError):
        CodeExecutionRequest(language="python", code="print('ok')", stdin="x" * 16_385)


def test_windows_docker_pipe_error_is_reported_as_unavailable():
    error = (
        "failed to connect to the docker API at npipe:////./pipe/"
        "dockerDesktopLinuxEngine; open //./pipe/dockerDesktopLinuxEngine: "
        "The system cannot find the file specified."
    )
    message = _docker_unavailable_message(1, error)
    assert message is not None
    assert "Docker Engine is not reachable" in message


def test_missing_runner_image_has_specific_message():
    message = _docker_unavailable_message(
        125, "Unable to find image 'talaba-code-runner:1' locally"
    )
    assert message is not None
    assert "talaba-code-runner:1" in message


def test_unrelated_runtime_error_is_not_classified_as_docker_failure():
    assert _docker_unavailable_message(1, "ZeroDivisionError: division by zero") is None


def test_standard_input_is_limited_by_utf8_byte_size():
    with pytest.raises(ValidationError):
        CodeExecutionRequest(language="python", code="print(input())", stdin="ع" * 8_193)

import shutil
import subprocess

import pytest

from app.services.code_runner import RUNNER_IMAGE, execute_code


def _command_succeeds(command: list[str], timeout: int = 8) -> bool:
    try:
        result = subprocess.run(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=timeout,
            check=False,
        )
        return result.returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.fixture(scope="module", autouse=True)
def require_docker_runner():
    if shutil.which("docker") is None:
        pytest.skip("Docker CLI is not installed; isolated runner integration tests require Docker.")
    if not _command_succeeds(["docker", "info"]):
        pytest.skip("Docker Engine is not reachable; start Docker Desktop to run integration tests.")
    if not _command_succeeds(["docker", "image", "inspect", RUNNER_IMAGE]):
        pytest.skip(f"Runner image {RUNNER_IMAGE} is missing; build it before integration tests.")


@pytest.mark.parametrize(
    ("language", "code", "stdin", "expected"),
    [
        (
            "c",
            '#include <stdio.h>\nint main(void) { char name[80]; if (scanf("%79s", name) != 1) return 2; printf("Hello, %s!\\n", name); return 0; }',
            "Talaba\n",
            "Hello, Talaba!",
        ),
        (
            "python",
            'name = input("Name: ")\nprint(f"Hello, {name}!")',
            "Talaba\n",
            "Hello, Talaba!",
        ),
        (
            "javascript",
            'const fs = require("fs");\nconst name = fs.readFileSync(0, "utf8").trim();\nconsole.log(`Hello, ${name}!`);',
            "Talaba\n",
            "Hello, Talaba!",
        ),
    ],
)
@pytest.mark.anyio
async def test_language_executes_with_standard_input(language, code, stdin, expected):
    result = await execute_code(language, code, stdin)
    assert result.status == "success", result.model_dump()
    assert expected in result.stdout
    assert result.exit_code == 0


@pytest.mark.anyio
async def test_python_runtime_error_has_diagnostic():
    result = await execute_code("python", "print('before')\n1 / 0")
    assert result.status == "runtime_error", result.model_dump()
    assert result.stdout.strip() == "before"
    assert result.diagnostics
    assert result.diagnostics[0].line == 2


@pytest.mark.anyio
async def test_c_compile_error_is_reported():
    code = "int main(void) {\n    return missing_symbol;\n}"
    result = await execute_code("c", code)
    assert result.status == "compile_error", result.model_dump()
    assert result.diagnostics
    assert result.diagnostics[0].line == 2


@pytest.mark.anyio
async def test_python_infinite_loop_times_out():
    result = await execute_code("python", "while True:\n    pass")
    assert result.status == "timeout", result.model_dump()

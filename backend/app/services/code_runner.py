import asyncio
import sys
import re
import tempfile
import time
import uuid
from pathlib import Path

from app.schemas.code_execution import (
    CodeDiagnostic,
    CodeExecutionResponse,
    CodeExecutionSourceFile,
    CodeLanguage,
)

RUNNER_IMAGE = "talaba-code-runner:1"
MAX_OUTPUT_BYTES = 16 * 1024
WALL_TIMEOUT_SECONDS = 30
PROGRAM_TIMEOUT_SECONDS = 3
COMPILE_FAILURE_MARKER = "__TALABA_COMPILATION_FAILED__"

# Keep temporary source files on D alongside the project.
RUN_TEMP_ROOT = Path(tempfile.gettempdir()) / "TalabaAI-CodeRunner"


def parse_diagnostics(language: CodeLanguage, stderr: str) -> list[CodeDiagnostic]:
    diagnostics: list[CodeDiagnostic] = []

    if language == "c":
        pattern = re.compile(
            r"(?:/workspace/)?(.+?\.(?:c|h)):(\d+):(\d+):\s*"
            r"(fatal error|error|warning|note):\s*(.*)"
        )
        for match in pattern.finditer(stderr):
            kind = match.group(4)
            if kind == "note":
                continue
            diagnostics.append(
                CodeDiagnostic(
                    file=match.group(1).rsplit("/", 1)[-1],
                    line=int(match.group(2)),
                    column=int(match.group(3)),
                    severity="warning" if kind == "warning" else "error",
                    message=match.group(5).strip() or kind,
                )
            )

    elif language == "python":
        frames = list(
            re.finditer(r'File "/workspace/main\.py", line (\d+)', stderr)
        )
        if frames:
            lines = [line.strip() for line in stderr.splitlines() if line.strip()]
            message = lines[-1] if lines else "Python execution failed."
            diagnostics.append(
                CodeDiagnostic(
                    line=int(frames[-1].group(1)),
                    column=1,
                    severity="error",
                    message=message,
                )
            )

    elif language == "javascript":
        matches = list(
            re.finditer(r"(?:/workspace/)?main\.js:(\d+)(?::(\d+))?", stderr)
        )
        if matches:
            match = matches[-1]
            lines = [line.strip() for line in stderr.splitlines() if line.strip()]
            message = lines[-1] if lines else "JavaScript execution failed."
            diagnostics.append(
                CodeDiagnostic(
                    line=int(match.group(1)),
                    column=int(match.group(2) or 1),
                    severity="error",
                    message=message,
                )
            )

    return diagnostics


async def _collect_limited(
    stream: asyncio.StreamReader,
    destination: bytearray,
    budget: dict[str, int | bool],
    overflow_event: asyncio.Event,
) -> None:
    while True:
        chunk = await stream.read(4096)
        if not chunk:
            return

        used = int(budget["used"])
        remaining = max(0, MAX_OUTPUT_BYTES - used)
        included = chunk[:remaining]

        if included:
            destination.extend(included)
            budget["used"] = used + len(included)

        if len(chunk) > remaining:
            budget["overflow"] = True
            overflow_event.set()
            return


async def _docker_control(*args: str, timeout: float = 2.0) -> None:
    try:
        process = await asyncio.create_subprocess_exec(
            "docker",
            *args,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            await asyncio.wait_for(process.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
    except (OSError, asyncio.SubprocessError):
        return


def _runner_command(language: CodeLanguage) -> list[str]:
    if language == "c":
        script = (
            "if gcc -std=c11 -O0 -Wall -Wextra -fno-diagnostics-color "
            "/workspace/*.c -o /tmp/talaba-program; then "
            f"timeout --signal=KILL {PROGRAM_TIMEOUT_SECONDS}s /tmp/talaba-program; "
            "else echo __TALABA_COMPILATION_FAILED__ >&2; exit 86; fi"
        )
    elif language == "python":
        script = (
            f"timeout --signal=KILL {PROGRAM_TIMEOUT_SECONDS}s "
            "python3 -I -S /workspace/main.py"
        )
    else:
        script = (
            f"timeout --signal=KILL {PROGRAM_TIMEOUT_SECONDS}s "
            "node /workspace/main.js"
        )

    return ["/bin/sh", "-lc", script]


def _docker_unavailable_message(return_code: int | None, stderr: str) -> str | None:
    """Map common Docker CLI/daemon failures to a useful runner status."""
    docker_error = stderr.lower()
    connection_markers = (
        "failed to connect to the docker api",
        "error during connect",
        "cannot connect to the docker daemon",
        "is the docker daemon running",
        "the system cannot find the file specified",
        "docker daemon is not running",
    )
    image_markers = (
        "error response from daemon",
        "unable to find image",
        "no such image",
        "pull access denied",
        "image not found",
    )

    if any(marker in docker_error for marker in connection_markers):
        return "Docker Engine is not reachable. Start Docker Desktop and try again."

    if any(marker in docker_error for marker in image_markers):
        return (
            "The talaba-code-runner:1 image is missing or unavailable. "
            "Run scripts/start-talaba.ps1 to prepare the runner."
        )

    if return_code in (125, 126, 127) and "docker: " in docker_error:
        return (
            "Docker could not start the runner container. Check Docker Desktop "
            "and the talaba-code-runner:1 image."
        )

    return None


async def _execute_container_impl(
    workspace: Path,
    language: CodeLanguage,
    stdin: str = "",
) -> CodeExecutionResponse:
    started = time.monotonic()
    container_name = f"talaba-run-{uuid.uuid4().hex[:16]}"
    source_path = workspace.as_posix()

    command = [
        "docker", "run",
        "--interactive",
        "--pull=never",
        "--rm",
        "--name", container_name,
        "--network", "none",
        "--memory", "128m",
        "--memory-swap", "128m",
        "--cpus", "0.5",
        "--pids-limit", "32",
        "--ulimit", "cpu=6:6",
        "--ulimit", "core=0:0",
        "--read-only",
        "--tmpfs", "/tmp:rw,exec,nosuid,nodev,size=32m",
        "--user", "65534:65534",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges:true",
        "--env", "HOME=/tmp",
        "--env", "PYTHONDONTWRITEBYTECODE=1",
        "--workdir", "/workspace",
        "--mount",
        f"type=bind,source={source_path},target=/workspace,readonly",
        RUNNER_IMAGE,
        *_runner_command(language),
    ]

    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except OSError:
        return CodeExecutionResponse(
            status="unavailable",
            duration_ms=int((time.monotonic() - started) * 1000),
            message="Docker could not be started. Check Docker Desktop and the Docker CLI.",
        )

    stdout_bytes = bytearray()
    stderr_bytes = bytearray()
    budget: dict[str, int | bool] = {"used": 0, "overflow": False}
    overflow_event = asyncio.Event()

    stdout_task = asyncio.create_task(
        _collect_limited(process.stdout, stdout_bytes, budget, overflow_event)
    )
    stderr_task = asyncio.create_task(
        _collect_limited(process.stderr, stderr_bytes, budget, overflow_event)
    )
    waiter = asyncio.create_task(process.wait())
    overflow_waiter = asyncio.create_task(overflow_event.wait())

    timed_out = False

    try:
        # Docker only forwards standard input when `docker run -i` is enabled.
        # Always close the pipe so programs that do not read input receive EOF.
        if process.stdin is not None:
            try:
                if stdin:
                    process.stdin.write(stdin.encode("utf-8"))
                    await process.stdin.drain()
            except (BrokenPipeError, ConnectionResetError, OSError):
                # The Docker CLI may exit immediately if the engine or image is unavailable.
                pass
            finally:
                process.stdin.close()
                try:
                    await process.stdin.wait_closed()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    pass

        done, _ = await asyncio.wait(
            {waiter, overflow_waiter},
            timeout=WALL_TIMEOUT_SECONDS,
            return_when=asyncio.FIRST_COMPLETED,
        )

        if not done:
            timed_out = True
            await _docker_control("kill", container_name)
        elif overflow_event.is_set():
            await _docker_control("kill", container_name)
        else:
            await waiter

        if process.returncode is None:
            try:
                await asyncio.wait_for(process.wait(), timeout=2.0)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()

        try:
            await asyncio.wait_for(
                asyncio.gather(stdout_task, stderr_task),
                timeout=2.0,
            )
        except asyncio.TimeoutError:
            stdout_task.cancel()
            stderr_task.cancel()
            await asyncio.gather(stdout_task, stderr_task, return_exceptions=True)

    finally:
        overflow_waiter.cancel()
        await asyncio.gather(overflow_waiter, return_exceptions=True)

        if process.returncode is None:
            process.kill()
            await process.wait()

        await _docker_control("rm", "-f", container_name)

    duration_ms = int((time.monotonic() - started) * 1000)
    stdout = stdout_bytes.decode("utf-8", errors="replace")
    stderr = stderr_bytes.decode("utf-8", errors="replace")
    return_code = process.returncode

    compile_failed = COMPILE_FAILURE_MARKER in stderr
    stderr = stderr.replace(COMPILE_FAILURE_MARKER, "").strip()

    if bool(budget["overflow"]):
        return CodeExecutionResponse(
            status="output_limit",
            stdout=stdout,
            stderr=stderr,
            exit_code=return_code,
            duration_ms=duration_ms,
            diagnostics=parse_diagnostics(language, stderr),
            message=f"Output exceeded the {MAX_OUTPUT_BYTES // 1024} KB limit. Execution was stopped.",
        )

    if timed_out or return_code in (124, 137):
        return CodeExecutionResponse(
            status="timeout",
            stdout=stdout,
            stderr=stderr,
            exit_code=return_code,
            duration_ms=duration_ms,
            diagnostics=parse_diagnostics(language, stderr),
            message=(
                f"Execution exceeded the {PROGRAM_TIMEOUT_SECONDS}-second program "
                "limit, or reached a resource limit."
            ),
        )

    docker_message = _docker_unavailable_message(return_code, stderr)
    if docker_message:
        return CodeExecutionResponse(
            status="unavailable",
            stdout="",
            stderr="",
            exit_code=None,
            duration_ms=duration_ms,
            message=docker_message,
        )

    if compile_failed:
        return CodeExecutionResponse(
            status="compile_error",
            stdout=stdout,
            stderr=stderr,
            exit_code=None,
            duration_ms=duration_ms,
            diagnostics=parse_diagnostics(language, stderr),
            message="Compilation failed. Check the highlighted source line and compiler output.",
        )

    if return_code == 0:
        return CodeExecutionResponse(
            status="success",
            stdout=stdout,
            stderr=stderr,
            exit_code=0,
            duration_ms=duration_ms,
            diagnostics=parse_diagnostics(language, stderr),
            message="Execution completed.",
        )

    return CodeExecutionResponse(
        status="runtime_error",
        stdout=stdout,
        stderr=stderr,
        exit_code=return_code,
        duration_ms=duration_ms,
        diagnostics=parse_diagnostics(language, stderr),
        message="The program exited with an error. Check the output and highlighted source line.",
    )



def _run_container_with_proactor(workspace, language, stdin=""):
    """Run subprocess orchestration on a Windows Proactor event loop."""
    loop = asyncio.ProactorEventLoop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(
            _execute_container_impl(workspace, language, stdin)
        )
    finally:
        try:
            loop.run_until_complete(loop.shutdown_asyncgens())
        except Exception:
            pass
        loop.close()
        asyncio.set_event_loop(None)


async def _execute_container(workspace, language, stdin=""):
    """Use a subprocess-capable event loop on Windows."""
    if sys.platform == "win32":
        return await asyncio.to_thread(
            _run_container_with_proactor, workspace, language, stdin
        )

    return await _execute_container_impl(workspace, language, stdin)


async def execute_code(
    language: CodeLanguage,
    code: str,
    stdin: str = "",
    source_files: list[CodeExecutionSourceFile] | None = None,
) -> CodeExecutionResponse:
    RUN_TEMP_ROOT.mkdir(parents=True, exist_ok=True)

    filename = {
        "c": "main.c",
        "python": "main.py",
        "javascript": "main.js",
    }[language]

    with tempfile.TemporaryDirectory(
        prefix="run-",
        dir=RUN_TEMP_ROOT,
    ) as directory:
        workspace = Path(directory)
        if language == "c" and source_files:
            for source_file in source_files:
                (workspace / source_file.name).write_text(
                    source_file.code,
                    encoding="utf-8",
                    newline="\n",
                )
        else:
            (workspace / filename).write_text(code, encoding="utf-8", newline="\n")
        return await _execute_container(workspace, language, stdin)

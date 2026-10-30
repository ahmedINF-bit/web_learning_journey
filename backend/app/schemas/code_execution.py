from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


CodeLanguage = Literal["c", "python", "javascript"]
ExecutionStatus = Literal[
    "success",
    "compile_error",
    "runtime_error",
    "timeout",
    "output_limit",
    "unavailable",
]


class CodeExecutionSourceFile(BaseModel):
    name: str = Field(..., min_length=1, max_length=150)
    code: str = Field(..., max_length=200_000)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value or value in {".", ".."}:
            raise ValueError("Source file name cannot be empty or a path marker.")
        if any(char in value for char in ("/", "\\", ":", "\x00")):
            raise ValueError("Source file names must be plain file names without paths.")
        if any(ord(char) < 32 for char in value):
            raise ValueError("Source file names cannot contain control characters.")
        return value


class CodeExecutionRequest(BaseModel):
    language: CodeLanguage
    code: str = Field(..., min_length=1, max_length=200_000)
    stdin: str = Field(default="", max_length=16_384)
    source_files: list[CodeExecutionSourceFile] = Field(default_factory=list, max_length=20)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Code cannot be empty.")
        return value

    @field_validator("stdin")
    @classmethod
    def validate_stdin(cls, value: str) -> str:
        if len(value.encode("utf-8")) > 16_384:
            raise ValueError("Standard input cannot exceed 16 KB when encoded as UTF-8.")
        return value

    @model_validator(mode="after")
    def validate_source_files(self) -> "CodeExecutionRequest":
        if not self.source_files:
            return self
        if self.language != "c":
            raise ValueError("Additional source files are currently supported for C projects only.")

        seen: set[str] = set()
        total_bytes = 0
        has_c_source = False
        for source_file in self.source_files:
            normalized_name = source_file.name.casefold()
            if normalized_name in seen:
                raise ValueError("Source file names must be unique, ignoring letter case.")
            seen.add(normalized_name)

            suffix = source_file.name.rsplit(".", 1)[-1].lower() if "." in source_file.name else ""
            if suffix not in {"c", "h"}:
                raise ValueError("C multi-file projects can include only .c and .h files.")
            if suffix == "c":
                has_c_source = True
            total_bytes += len(source_file.code.encode("utf-8"))

        if not has_c_source:
            raise ValueError("At least one .c source file is required.")
        if total_bytes > 1_000_000:
            raise ValueError("Combined source files cannot exceed 1 MB per run.")
        return self


class CodeDiagnostic(BaseModel):
    file: str | None = None
    line: int = Field(ge=1)
    column: int = Field(default=1, ge=1)
    severity: Literal["error", "warning"] = "error"
    message: str


class CodeExecutionResponse(BaseModel):
    status: ExecutionStatus
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    duration_ms: int = Field(ge=0)
    diagnostics: list[CodeDiagnostic] = Field(default_factory=list)
    message: str | None = None

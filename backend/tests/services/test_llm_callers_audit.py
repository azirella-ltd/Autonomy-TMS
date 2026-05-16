"""§3.16 LLMClient-consumer-migration drift-prevention guard (TMS plane).

CLAUDE.md "LLM usage discipline" requires every LLM call to go
through Core's ``azirella_assistant.LLMClient`` with a
:class:`Workload` tag.

Two complementary checks guard against regression:

1. **URL audit** (the canonical grep from CLAUDE.md / §3.16):

       grep -RIn 'api.anthropic.com\\|api.openai.com\\|/chat/completions' \\
           --include='*.py' backend/app/

   Catches direct httpx / requests calls that build the URL by hand.

2. **SDK-direct-import audit**: any ``from openai import`` or
   ``from anthropic import`` (or equivalent ``import openai`` /
   ``import anthropic``) inside ``backend/app/`` is a §3.16 violation.
   The SDK builds the chat-completions / messages URL internally so
   the URL-grep can't see it — this second pass catches the case.
   The Core substrate (``azirella_assistant.OpenAICompatibleClient``)
   is the one place the OpenAI SDK is legitimately imported.

Steady-state expectation for TMS backend/app/: zero hits on both.
A failure means somebody re-introduced a direct SDK caller — route
the new call through ``azirella_assistant.LLMClient`` instead.
"""
from __future__ import annotations

import pathlib
import re


_AUDIT_PATTERN = re.compile(
    r"api\.anthropic\.com|api\.openai\.com|/chat/completions"
)

# SDK-direct imports — top-level statement forms only. ``re.MULTILINE``
# anchors ``^`` to a line start so we don't false-match a substring
# inside a comment / docstring.
_SDK_IMPORT_PATTERN = re.compile(
    r"^[ \t]*(?:from\s+(?:openai|anthropic)(?:\.\w+)*\s+import\b"
    r"|import\s+(?:openai|anthropic)(?:\s|$|\.))",
    re.MULTILINE,
)


def _iter_tms_app_python_files() -> list[pathlib.Path]:
    """Yield every .py file under ``backend/app/``.

    The test lives at ``backend/tests/services/test_llm_callers_audit.py``,
    so ``backend/app/`` is two parents up + ``app``.
    """
    backend_root = pathlib.Path(__file__).resolve().parents[2]
    app_root = backend_root / "app"
    if not app_root.is_dir():
        return []
    return [
        p for p in app_root.rglob("*.py")
        if "__pycache__" not in p.parts
    ]


def test_no_direct_llm_api_callers_in_tms_app() -> None:
    """Scan every Python file under TMS's ``backend/app/``. Any direct
    mention of the audit URLs (``api.anthropic.com``,
    ``api.openai.com``, ``/chat/completions``) is a §3.16 regression
    and fails CI with the full violator list."""
    violators: list[tuple[str, list[int]]] = []
    for path in _iter_tms_app_python_files():
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        if not _AUDIT_PATTERN.search(content):
            continue
        hit_lines = [
            i for i, line in enumerate(content.splitlines(), start=1)
            if _AUDIT_PATTERN.search(line)
        ]
        violators.append((str(path), hit_lines))

    assert not violators, (
        "§3.16 LLMClient-substrate violation: TMS backend/app/ files "
        "contain direct LLM-API references. Route through "
        "`azirella_assistant.LLMClient` with a `Workload` tag instead. "
        "Violators:\n"
        + "\n".join(f"  {p}: lines {ls}" for p, ls in violators)
    )


def test_no_direct_openai_or_anthropic_sdk_imports_in_tms_app() -> None:
    """Catch the SDK-direct path the URL audit can't see.

    The OpenAI / Anthropic Python SDKs build their endpoint URL
    internally, so a caller that does ``from openai import AsyncOpenAI``
    and ``self.client.chat.completions.create(...)`` produces zero hits
    on the URL grep. Banning the import itself in ``backend/app/`` is
    the second line of defence.
    """
    violators: list[tuple[str, list[int]]] = []
    for path in _iter_tms_app_python_files():
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        hit_lines = [
            i for i, line in enumerate(content.splitlines(), start=1)
            if _SDK_IMPORT_PATTERN.search(line)
        ]
        if hit_lines:
            violators.append((str(path), hit_lines))

    assert not violators, (
        "§3.16 LLMClient-substrate violation: TMS backend/app/ files "
        "import the OpenAI or Anthropic SDK directly. The substrate "
        "(`azirella_assistant.OpenAICompatibleClient` / "
        "`azirella_assistant.AnthropicClient`) is the only legitimate "
        "consumer of those SDKs. Route the call through the substrate. "
        "Violators:\n"
        + "\n".join(f"  {p}: lines {ls}" for p, ls in violators)
    )

#!/usr/bin/env python3
"""Small client for the local LightRAG knowledge bases.

Routing rule:
- ALGO KB is only for trader-facing market, strategy, risk, and trading context.
- GENERAL KB is for operational notes, repo changes, task recovery, and Codex context.
"""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Callable, Optional

import requests


ALGO_KB_BASE_URL = os.getenv("ALGO_KB_BASE_URL", "http://127.0.0.1:9624").rstrip("/")
GENERAL_KB_BASE_URL = os.getenv("GENERAL_KB_BASE_URL", "http://127.0.0.1:9622").rstrip("/")
DEFAULT_TIMEOUT = int(os.getenv("ALGO_KB_TIMEOUT_SECONDS", "60"))
MIN_USEFUL_TEXT_CHARS = int(os.getenv("ALGO_KB_MIN_USEFUL_TEXT_CHARS", "40"))
BLOCKED_EXACT_TEXTS = {
    "analysis failed.",
    "incubation failed.",
    "audit failed.",
    "error",
    "no data.",
    "kb unavailable.",
}
BLOCKED_TEXT_PATTERNS = (
    r"\banalysis failed\b",
    r"\bincubation failed\b",
    r"\baudit failed\b",
    r"\bcurrent directory is empty\b",
    r"\bprovide a more comprehensive dataset\b",
    r"\bimpossible to fulfill\b",
    r"\bwithout sufficient historical data\b",
    r"\bi require a more extensive dataset\b",
)


def _auth():
    user = os.getenv("ALGO_KB_USER")
    password = os.getenv("ALGO_KB_PASSWORD")
    if user and password:
        return (user, password)
    return None


def _log(log_func: Optional[Callable[[str], None]], message: str) -> None:
    if log_func:
        log_func(message)
    else:
        print(message)


def _check_insert_response(response: requests.Response) -> dict:
    response.raise_for_status()
    payload = response.json()
    status = payload.get("status")
    if status not in {"success", "duplicated", "partial_success"}:
        raise RuntimeError(f"ALGO KB insert failed: {payload}")
    return payload


def validate_kb_text(text: str, *, source: str = "inline text") -> str:
    """Reject empty placeholders before they pollute the knowledge base."""
    clean_text = (text or "").strip()
    normalized = re.sub(r"\s+", " ", clean_text).strip().lower()
    if not clean_text:
        raise ValueError(f"ALGO KB insert skipped for {source}: text is empty")
    if normalized in BLOCKED_EXACT_TEXTS:
        raise ValueError(f"ALGO KB insert skipped for {source}: blocked placeholder text '{clean_text}'")
    for pattern in BLOCKED_TEXT_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE):
            raise ValueError(f"ALGO KB insert skipped for {source}: blocked low-quality text pattern '{pattern}'")
    if len(clean_text) < MIN_USEFUL_TEXT_CHARS:
        raise ValueError(
            f"ALGO KB insert skipped for {source}: text is too short ({len(clean_text)} chars)"
        )
    if not re.search(r"[A-Za-zА-Яа-я0-9]", clean_text):
        raise ValueError(f"ALGO KB insert skipped for {source}: text has no useful symbols")
    return clean_text


def upload_file_to_kb(
    file_path: str | Path,
    *,
    base_url: str = ALGO_KB_BASE_URL,
    kb_name: str = "ALGO KB",
    log_func: Optional[Callable[[str], None]] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """Upload a local file through /documents/upload and return the LightRAG response."""
    path = Path(file_path)
    validate_kb_text(path.read_text(encoding="utf-8", errors="ignore"), source=path.name)
    with path.open("rb") as file_handle:
        response = requests.post(
            f"{base_url.rstrip('/')}/documents/upload",
            files={"file": (path.name, file_handle, "text/markdown")},
            auth=_auth(),
            timeout=timeout,
        )
    payload = _check_insert_response(response)
    _log(
        log_func,
        f"{kb_name} upload: file={path.name} status={payload.get('status')} track_id={payload.get('track_id')}",
    )
    return payload


def upload_file_to_algo_kb(
    file_path: str | Path,
    *,
    log_func: Optional[Callable[[str], None]] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    return upload_file_to_kb(file_path, log_func=log_func, timeout=timeout)


def upload_file_to_general_kb(
    file_path: str | Path,
    *,
    log_func: Optional[Callable[[str], None]] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    return upload_file_to_kb(
        file_path,
        base_url=GENERAL_KB_BASE_URL,
        kb_name="GENERAL KB",
        log_func=log_func,
        timeout=timeout,
    )


def insert_text_to_kb(
    text: str,
    *,
    file_source: str,
    base_url: str = ALGO_KB_BASE_URL,
    kb_name: str = "ALGO KB",
    log_func: Optional[Callable[[str], None]] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """Insert raw text through /documents/text and return the LightRAG response."""
    clean_text = validate_kb_text(text, source=file_source)

    response = requests.post(
        f"{base_url.rstrip('/')}/documents/text",
        json={"text": clean_text, "file_source": file_source},
        auth=_auth(),
        timeout=timeout,
    )
    payload = _check_insert_response(response)
    _log(
        log_func,
        f"{kb_name} insert: source={file_source} status={payload.get('status')} track_id={payload.get('track_id')}",
    )
    return payload


def insert_text_to_algo_kb(
    text: str,
    *,
    file_source: str,
    log_func: Optional[Callable[[str], None]] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    return insert_text_to_kb(text, file_source=file_source, log_func=log_func, timeout=timeout)


def insert_text_to_general_kb(
    text: str,
    *,
    file_source: str,
    log_func: Optional[Callable[[str], None]] = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    return insert_text_to_kb(
        text,
        file_source=file_source,
        base_url=GENERAL_KB_BASE_URL,
        kb_name="GENERAL KB",
        log_func=log_func,
        timeout=timeout,
    )


def wait_for_algo_kb_track(
    track_id: str,
    *,
    timeout: int = 120,
    poll_seconds: float = 2.0,
) -> dict:
    """Poll LightRAG background processing status for smoke tests and diagnostics."""
    deadline = time.monotonic() + timeout
    last_payload: dict = {}
    while time.monotonic() < deadline:
        response = requests.get(
            f"{ALGO_KB_BASE_URL}/documents/track_status/{track_id}",
            auth=_auth(),
            timeout=DEFAULT_TIMEOUT,
        )
        response.raise_for_status()
        last_payload = response.json()
        statuses = [
            str(document.get("status", "")).lower()
            for document in last_payload.get("documents", [])
        ]
        if not statuses:
            status = str(last_payload.get("status", "")).lower()
            statuses = [status] if status else []
        if statuses and all(status in {"processed", "failed"} for status in statuses):
            return last_payload
        time.sleep(poll_seconds)
    raise TimeoutError(f"ALGO KB track {track_id} did not finish in {timeout}s: {last_payload}")

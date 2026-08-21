"""
safe_parse.py — Subprocess-isolated file parsing

The tree-sitter C extension can cause a process-level crash (exit code 1 /
segfault) on certain source files. Python's try/except cannot catch a
C-level abort, so a crash in parse_file() kills the entire Uvicorn worker,
making ALL subsequent requests return 502 Bad Gateway.

Design
──────
A single persistent worker subprocess handles all parse_file() calls
sequentially.  The worker loops on a queue: parent sends (extension, path,
content), worker sends back a result via Pipe and loops to the next.

If the worker crashes (C-level exit), the parent detects EOFError / dead
process, logs the bad file, spawns a fresh worker, and continues.

This means:
  - Only ONE subprocess is running at a time (no pool overhead).
  - Spawn cost is paid once per analysis job (or after each crash).
  - A single crashing file is logged + skipped; the rest of the repo
    continues normally.
  - The main Uvicorn worker never dies.
"""

import multiprocessing
import pickle
import traceback
from pathlib import Path
from typing import Optional
import structlog

from archon.pipeline.parsers.base import ParsedFile

logger = structlog.get_logger(__name__)

PARSE_TIMEOUT_SECONDS = 30  # per file

# Use spawn on all platforms — the only method that safely isolates C extensions.
_CTX = multiprocessing.get_context("spawn")


# ---------------------------------------------------------------------------
# Worker loop — runs inside the child process
# ---------------------------------------------------------------------------

def _worker_loop(recv_conn, send_conn) -> None:
    """
    Runs in the child process. Imports all parsers once, then loops:
      - recv  (extension, path, content)
      - parse
      - send  ("OK", ParsedFile)  or  ("ERROR", msg, tb)
    """
    try:
        from archon.pipeline.parsers.registry import registry
        import archon.pipeline.parsers.python.parser      # noqa: F401
        import archon.pipeline.parsers.javascript.parser  # noqa: F401
        import archon.pipeline.parsers.typescript.parser  # noqa: F401
        import archon.pipeline.parsers.java.parser        # noqa: F401
        import archon.pipeline.parsers.csharp.parser      # noqa: F401
        import archon.pipeline.parsers.go.parser          # noqa: F401
        import archon.pipeline.parsers.rust.parser        # noqa: F401
    except Exception as exc:
        try:
            send_conn.send_bytes(pickle.dumps(("STARTUP_ERROR", str(exc))))
        except Exception:
            pass
        return

    while True:
        try:
            if not recv_conn.poll(60):
                break  # idle 60s — exit cleanly
            task = recv_conn.recv_bytes()
            if task == b"EXIT":
                break
            extension, path, content = pickle.loads(task)

            parser = registry.get_parser(extension)
            if parser is None:
                result = None
            else:
                result = parser.parse_file(path, content)

            send_conn.send_bytes(pickle.dumps(("OK", result)))
        except EOFError:
            break  # parent closed connection
        except Exception as exc:
            try:
                send_conn.send_bytes(
                    pickle.dumps(("ERROR", str(exc), traceback.format_exc()))
                )
            except Exception:
                pass


# ---------------------------------------------------------------------------
# ParseWorker — manages the persistent subprocess
# ---------------------------------------------------------------------------

class _ParseWorker:
    """Manages a single persistent subprocess for file parsing."""

    def __init__(self):
        self._proc = None
        self._parent_recv = None
        self._parent_send = None

    def _spawn(self) -> None:
        if self._proc and self._proc.is_alive():
            self._proc.kill()
            self._proc.join(timeout=2)

        parent_recv, child_send = _CTX.Pipe(duplex=False)
        child_recv, parent_send = _CTX.Pipe(duplex=False)

        proc = _CTX.Process(
            target=_worker_loop,
            args=(child_recv, child_send),
            daemon=True,
        )
        proc.start()
        child_send.close()
        child_recv.close()

        self._proc = proc
        self._parent_recv = parent_recv
        self._parent_send = parent_send
        logger.debug("parse_worker_spawned", pid=proc.pid)

    def _ensure_alive(self) -> None:
        if self._proc is None or not self._proc.is_alive():
            logger.info("parse_worker_respawning")
            self._spawn()

    def parse(
        self,
        extension: str,
        path: str,
        content: str,
        rel_path: str,
    ) -> Optional[ParsedFile]:
        self._ensure_alive()

        try:
            self._parent_send.send_bytes(pickle.dumps((extension, path, content)))
        except Exception as e:
            logger.error("parse_worker_send_failed", path=rel_path, error=str(e))
            self._spawn()
            return _error_file(rel_path, content, f"send_failed: {e}")

        try:
            if not self._parent_recv.poll(PARSE_TIMEOUT_SECONDS):
                logger.error("safe_parse_timeout", path=rel_path, timeout_s=PARSE_TIMEOUT_SECONDS)
                self._spawn()
                return _error_file(rel_path, content, f"parse_timeout after {PARSE_TIMEOUT_SECONDS}s")

            payload = self._parent_recv.recv_bytes()
            obj = pickle.loads(payload)

        except EOFError:
            exit_code = self._proc.exitcode if self._proc else "?"
            logger.error("safe_parse_subprocess_crash", path=rel_path, exit_code=exit_code)
            self._spawn()
            return _error_file(rel_path, content, f"parser_subprocess_crash (exit {exit_code})")

        except Exception as e:
            logger.error("safe_parse_recv_error", path=rel_path, error=str(e))
            self._spawn()
            return _error_file(rel_path, content, f"recv_error: {e}")

        if not isinstance(obj, tuple):
            return obj if isinstance(obj, ParsedFile) else _error_file(rel_path, content, "unknown_response")

        tag = obj[0]
        if tag == "OK":
            return obj[1]  # None means unsupported extension
        if tag in ("ERROR", "STARTUP_ERROR"):
            err_msg = obj[1]
            logger.error("safe_parse_python_exception", path=rel_path, error=err_msg)
            return _error_file(rel_path, content, f"parser_exception: {err_msg}")

        return _error_file(rel_path, content, "unknown_response_tag")

    def shutdown(self) -> None:
        if self._proc and self._proc.is_alive():
            try:
                self._parent_send.send_bytes(b"EXIT")
            except Exception:
                pass
            self._proc.join(timeout=3)
            if self._proc.is_alive():
                self._proc.kill()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _error_file(rel_path: str, content: str, reason: str) -> ParsedFile:
    return ParsedFile(
        path=rel_path,
        language="unknown",
        module_name=Path(rel_path).stem,
        total_lines=len(content.splitlines()),
        docstring=None,
        classes=[],
        functions=[],
        imports=[],
        parse_errors=[reason],
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

# Module-level worker — one persistent child process per Uvicorn worker process.
_worker = _ParseWorker()


def safe_parse_file(
    path: str,
    content: str,
    extension: str,
    rel_path: str,
) -> Optional[ParsedFile]:
    """
    Parse a file in a subprocess-isolated environment.

    Returns:
        ParsedFile  — successful parse (may contain parse_errors for syntax)
        ParsedFile  — with a single error if the parser crashed or timed out
        None        — unsupported extension (orchestrator should skip/record)
    """
    return _worker.parse(
        extension=extension,
        path=path,
        content=content,
        rel_path=rel_path,
    )

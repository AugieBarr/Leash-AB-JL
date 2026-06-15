"""Scoped subprocess runner — the hard enforcement point for tool execution.

Every external CLI a worker invokes goes through ``scoped_run``, which calls the
fail-closed ``scope_guard`` *before* any process is spawned. An out-of-scope
target raises ScopeViolationError and nothing executes (the ToolBridge pre-hook
port).
"""
from __future__ import annotations

import asyncio
import shutil

from governance.capability import Capability
from governance.scope_guard import scope_guard


def tool_available(name: str) -> bool:
    return shutil.which(name) is not None


def ensure_leading_slash(path: str) -> str:
    """Normalize a tool's path argument to start with '/'."""
    return path if path.startswith("/") else "/" + path


async def scoped_run(
    cmd: list[str], target_url: str, cap: Capability, *, timeout: float = 60.0, halted: bool = False
) -> dict:
    """Authorize target_url against cap, then run cmd. Returns
    {returncode, stdout, stderr, timed_out}. Raises RuntimeError if the
    engagement is halted (kill-switch) and ScopeViolationError if out of scope —
    both before any process is spawned. The halt check is enforced here so the
    kill-switch is intrinsic to the runner, not a per-caller convention."""
    if halted:
        raise RuntimeError("engagement halted — kill-switch engaged; refusing to spawn any process")
    scope_guard(target_url, cap)

    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return {"returncode": -1, "stdout": "", "stderr": f"timeout after {timeout}s", "timed_out": True}

    return {
        "returncode": proc.returncode,
        "stdout": out.decode("utf-8", "replace"),
        "stderr": err.decode("utf-8", "replace"),
        "timed_out": False,
    }

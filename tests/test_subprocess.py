"""Tests for scoped_run — the hard tool-execution chokepoint.

Covers all three gates before exec (scope, kill-switch, in-scope success) plus
the timeout path. No network: commands are local echo/sleep.
"""
import pytest

from governance.capability import ScopeSpec, root_capability
from governance.scope_guard import ScopeViolationError
from tools._subprocess import scoped_run


def cap():
    return root_capability("eng", ScopeSpec.of(["localhost"], [3000], ["/"]))


async def test_out_of_scope_raises_before_exec():
    with pytest.raises(ScopeViolationError):
        await scoped_run(["echo", "x"], "http://google.com/", cap())


async def test_halted_raises_before_exec():
    with pytest.raises(RuntimeError):
        await scoped_run(["echo", "x"], "http://localhost:3000/", cap(), halted=True)


async def test_timeout_returns_timed_out():
    res = await scoped_run(["sleep", "5"], "http://localhost:3000/", cap(), timeout=0.05)
    assert res["timed_out"] is True
    assert res["returncode"] == -1


async def test_in_scope_command_runs():
    res = await scoped_run(["echo", "hello"], "http://localhost:3000/", cap(), timeout=5)
    assert res["returncode"] == 0
    assert "hello" in res["stdout"]

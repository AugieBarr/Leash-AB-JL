"""The scaffolder must produce specialists that are governed *by construction*.

The strongest assertion here is runtime, not textual: we generate a specialist, import
it, and run its handler through the same governed-behavior gauntlet the hand-written
tools pass — refused when halted, blocked out of scope, blocked without approval,
confirming only on the marker. If a generated tool could skip a leash step, these fail.
"""
import argparse
import ast
import importlib.util

import httpx
import pytest

from governance.capability import ScopeSpec, issue_capability
from swarm.engagement import open_engagement
from tools import scaffolder


def _spec(**kw):
    base = dict(
        name="demo_marker", owasp_class="OWASP A03", target_path="/in?q=", payload="x",
        marker="LEASHMARK", confirm_condition="marker_in_body", severity="high",
        finding_type="demo_marker", description="Confirm demo marker exposure on an endpoint.",
    )
    base.update(kw)
    return argparse.Namespace(**base)


def _load(src, tmp_path, name):
    path = tmp_path / f"{name}_tools.py"
    path.write_text(src)
    spec = importlib.util.spec_from_file_location(f"{name}_tools", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # absolute imports resolve via the repo root on sys.path
    return mod


class _FakeResp:
    def __init__(self, status, text):
        self.status_code = status
        self.text = text


class _FakeClient:
    _body, _status = "", 200

    def __init__(self, *a, **k):
        self._noop = True

    async def __aenter__(self):
        return self

    async def __aexit__(self, *a):
        return False

    async def get(self, url):
        return _FakeResp(type(self)._status, type(self)._body)


def _client(body="", status=200):
    return type("_C", (_FakeClient,), {"_body": body, "_status": status})


# ---- textual invariants -------------------------------------------------------

def test_generated_module_parses_and_orders_the_leash():
    src = scaffolder.render_module(_spec())
    ast.parse(src)  # valid Python
    # The four leash imports are present...
    for imp in ("from governance.scope_guard import", "from swarm.control_channel import enforce_gate",
                "from tools._subprocess import ensure_leading_slash"):
        assert imp in src
    # ...and inside the HANDLER body, the anchors appear in the fail-closed order.
    body = src.split("async def demo_marker_probe", 1)[1]
    i_halt = body.find("refuse_if_halted")
    i_base = body.find("ensure_leading_slash(args.path)")
    i_scope = body.find("scope_guard(probe_url")
    i_gate = body.find("_gate(")
    assert 0 <= i_halt < i_base < i_scope < i_gate, (i_halt, i_base, i_scope, i_gate)


def test_generated_capability_is_scoped_never_root():
    src = scaffolder.render_module(_spec())
    assert 'eng.cap_for("leash-demo-marker")' in src
    assert "eng.root_cap" not in src
    # generated tools must not reach for brain-only primitives or raw shell-out
    # (the legit `from tools._subprocess import ensure_leading_slash` is fine — that
    # helper is the scoped-run home, not a subprocess call).
    for forbidden in ("eng.halt(", "eng.ledger", "import subprocess", "os.system", "shell=True"):
        assert forbidden not in src


# ---- runtime: a generated specialist is governed exactly like the hand-written ones ----

def _pair(mod, eng, **kw):
    model, handler = mod.demo_marker_tools(eng, **kw)[0]
    return model, handler


def _scope(eng, paths):
    eng.capabilities["leash-demo-marker"] = issue_capability(
        eng.root_cap, ScopeSpec.of(["localhost"], [3000], paths)
    )


async def test_generated_confirms_only_on_marker(tmp_path, monkeypatch):
    mod = _load(scaffolder.render_module(_spec()), tmp_path, "demo_marker")
    eng = open_engagement("t-scaf-ok", "localhost", 3000, root=str(tmp_path))
    _scope(eng, ["/in"])
    await eng.record_approval("/in", operator="op", tool="demo_marker_probe")
    monkeypatch.setattr(httpx, "AsyncClient", _client(body='{"data":{"__typename":"Query"},"echo":"LEASHMARK"}', status=200))
    model, handler = _pair(mod, eng, gate_timeout=0.1)
    out = await handler(model(path="/in?q="))
    assert "VULNERABLE" in out
    assert len(eng.findings) == 1 and eng.findings[0]["type"] == "demo_marker"
    assert eng.ledger.verify_chain().ok


async def test_generated_not_confirmed_without_marker(tmp_path, monkeypatch):
    mod = _load(scaffolder.render_module(_spec()), tmp_path, "demo_marker")
    eng = open_engagement("t-scaf-no", "localhost", 3000, root=str(tmp_path))
    _scope(eng, ["/in"])
    await eng.record_approval("/in", operator="op", tool="demo_marker_probe")
    monkeypatch.setattr(httpx, "AsyncClient", _client(body="nothing here", status=200))
    model, handler = _pair(mod, eng, gate_timeout=0.1)
    out = await handler(model(path="/in?q="))
    assert "not confirmed" in out and eng.findings == []


async def test_generated_blocks_out_of_scope(tmp_path):
    mod = _load(scaffolder.render_module(_spec()), tmp_path, "demo_marker")
    eng = open_engagement("t-scaf-scope", "localhost", 3000, root=str(tmp_path))
    _scope(eng, ["/in"])
    await eng.record_approval("/out", operator="op", tool="demo_marker_probe")
    model, handler = _pair(mod, eng, gate_timeout=0.1)
    out = await handler(model(path="/out?q="))
    assert "BLOCKED by scope guard" in out and eng.findings == []


async def test_generated_refuses_when_halted(tmp_path):
    mod = _load(scaffolder.render_module(_spec()), tmp_path, "demo_marker")
    eng = open_engagement("t-scaf-halt", "localhost", 3000, root=str(tmp_path))
    _scope(eng, ["/in"])
    await eng.halt("operator kill-switch")
    model, handler = _pair(mod, eng, gate_timeout=0.1)
    out = await handler(model(path="/in?q="))
    assert "HALTED" in out and eng.findings == []


async def test_generated_refuses_without_approval(tmp_path):
    mod = _load(scaffolder.render_module(_spec()), tmp_path, "demo_marker")
    eng = open_engagement("t-scaf-gate", "localhost", 3000, root=str(tmp_path))
    _scope(eng, ["/in"])
    model, handler = _pair(mod, eng, gate_timeout=0.1, gate_poll=0.02)
    out = await handler(model(path="/in?q="))
    assert "BLOCKED" in out
    assert eng.halted and eng.findings == []


# ---- validation refusals ------------------------------------------------------

def test_rejects_weaponizing_name():
    with pytest.raises(SystemExit):
        scaffolder.main(["--name", "data_stealer", "--owasp-class", "A01",
                         "--target-path", "/x", "--description", "x", "--marker", "m"])


def test_marker_required_for_marker_mode():
    with pytest.raises(SystemExit):
        scaffolder.main(["--name", "demo", "--owasp-class", "A01", "--target-path", "/x",
                         "--confirm-condition", "marker_in_body", "--description", "x"])


def test_refuses_to_overwrite_existing_tool(capsys):
    # tools/sqli_tools.py already exists — the scaffolder must refuse, not clobber it.
    rc = scaffolder.main(["--name", "sqli", "--owasp-class", "A03", "--target-path", "/x",
                          "--marker", "m", "--description", "Confirm sqli on an endpoint."])
    assert rc == 1
    assert "already exists" in capsys.readouterr().err


def test_marker_injection_is_neutralized():
    # A crafted marker that tries to break out of the string literal must NOT inject
    # executable code — json.dumps keeps it inside _MARKER as data.
    evil = 'm"; import os; PWNED = os.getcwd(); _x = "'
    src = scaffolder.render_module(_spec(marker=evil))
    tree = ast.parse(src)  # still a valid, parseable module
    top_assigns = {t.id for n in tree.body if isinstance(n, ast.Assign)
                   for t in n.targets if isinstance(t, ast.Name)}
    assert "PWNED" not in top_assigns
    imported = {a.name for n in tree.body if isinstance(n, ast.Import) for a in n.names}
    assert "os" not in imported


def test_breakout_in_description_is_rejected():
    with pytest.raises(SystemExit):
        scaffolder.main(["--name", "demo", "--owasp-class", "A01", "--target-path", "/x",
                         "--marker", "m", "--description", 'x"; import os; os.system("id"); "'])


def test_legit_braced_payload_is_valid():
    # A real GraphQL probe payload contains braces — it must scaffold a valid module
    # (json-encoded into _PAYLOAD), never an f-string injection.
    src = scaffolder.render_module(_spec(name="graphql_introspection", finding_type="graphql_introspection",
                                         marker="__schema", payload="{__schema{types{name}}}"))
    ast.parse(src)
    assert '_PAYLOAD = "{__schema{types{name}}}"' in src

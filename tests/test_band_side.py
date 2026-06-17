"""Tests for the two Band-room-mutating modules — the room seeder and the
Band-side kill-switch eject. Both are pure async functions over a Band REST
client, so a fake client lets us pin their behavior without live Band creds:
the seeder adds the whole roster (minus the owner) and posts the kickoff; the
eject removes every specialist and keeps the Commander unless told otherwise.
"""
from types import SimpleNamespace

import swarm.kill_switch as ks
import swarm.seed as seed


class _Chats:
    async def create_agent_chat(self, *, chat=None, request_options=None):
        return SimpleNamespace(data=SimpleNamespace(id="room-123"))


class _Participants:
    def __init__(self, recorder, participants):
        self._rec = recorder
        self._participants = participants

    async def add_agent_chat_participant(self, *, chat_id=None, participant=None, request_options=None):
        self._rec.append(("add", chat_id, getattr(participant, "participant_id", None)))

    async def list_agent_chat_participants(self, room_id, request_options=None):
        return SimpleNamespace(data=self._participants)

    async def remove_agent_chat_participant(self, room_id, pid, request_options=None):
        self._rec.append(("remove", room_id, pid))


class _Messages:
    def __init__(self, recorder):
        self._rec = recorder

    async def create_agent_chat_message(self, *, chat_id=None, message=None, request_options=None):
        self._rec.append(("msg", chat_id, getattr(message, "content", "")))


class _FakeClient:
    def __init__(self, recorder, participants=None):
        self.agent_api_chats = _Chats()
        self.agent_api_participants = _Participants(recorder, participants or [])
        self.agent_api_messages = _Messages(recorder)


def _patch(monkeypatch, module, recorder, participants=None):
    monkeypatch.setattr(module, "load_dotenv", lambda: None)
    monkeypatch.setattr(module, "load_agent_config", lambda label: (f"{label}-id", f"{label}-key"))
    monkeypatch.setattr(module, "band_client", lambda key: _FakeClient(recorder, participants))


# ----- seeder ----------------------------------------------------------------
async def test_seed_room_adds_full_roster_and_posts_kickoff(monkeypatch):
    rec = []
    _patch(monkeypatch, seed, rec)
    room_id = await seed.seed_room("localhost:3000", kickoff=True)

    assert room_id == "room-123"
    adds = [c for c in rec if c[0] == "add"]
    assert len(adds) == len(seed.SWARM) - 1  # everyone except the commander (the owner)
    # the commander is never added as a participant to its own room
    assert all(pid != "leash-commander-id" for (_, _, pid) in adds)
    msgs = [c for c in rec if c[0] == "msg"]
    assert len(msgs) == 1 and "leash-commander" in msgs[0][2] and "localhost:3000" in msgs[0][2]


async def test_seed_room_no_kickoff_posts_nothing(monkeypatch):
    rec = []
    _patch(monkeypatch, seed, rec)
    await seed.seed_room("localhost:3000", kickoff=False)
    assert [c for c in rec if c[0] == "msg"] == []


# ----- kill-switch eject -----------------------------------------------------
def _roster():
    return [
        SimpleNamespace(id="leash-commander-id", handle="leash-commander"),
        SimpleNamespace(id="leash-sqli-hunter-id", handle="leash-sqli-hunter"),
        SimpleNamespace(id="leash-xss-hunter-id", handle="leash-xss-hunter"),
    ]


async def test_eject_keeps_commander_by_default(monkeypatch):
    rec = []
    _patch(monkeypatch, ks, rec, participants=_roster())
    removed = await ks.eject_room("room-1", include_commander=False)

    assert set(removed) == {"leash-sqli-hunter", "leash-xss-hunter"}
    assert "leash-commander" not in removed
    removes = [c for c in rec if c[0] == "remove"]
    assert all(pid != "leash-commander-id" for (_, _, pid) in removes)


async def test_eject_can_include_commander(monkeypatch):
    rec = []
    _patch(monkeypatch, ks, rec, participants=_roster())
    removed = await ks.eject_room("room-1", include_commander=True)
    assert "leash-commander" in removed and len(removed) == 3

import pytest

from services.layered_memory.l1_extractor import extract_atoms


@pytest.mark.asyncio
async def test_extract_atoms_empty_when_provider_unavailable(monkeypatch):
    monkeypatch.setattr("services.layered_memory.l1_extractor._build_client", lambda: None)
    atoms = await extract_atoms("Hi", "Hello", [])
    assert atoms == []


@pytest.mark.asyncio
async def test_extract_atoms_normalizes_bad_json(monkeypatch):
    async def fake_create(**kwargs):
        class _Choice:
            message = type("M", (), {"content": "not json"})()

        class _Resp:
            choices = [_Choice()]

        return _Resp()

    monkeypatch.setattr(
        "services.layered_memory.l1_extractor._build_client",
        lambda: (
            type(
                "C",
                (),
                {
                    "chat": type(
                        "Chat", (), {"completions": type("Comp", (), {"create": fake_create})()}
                    )()
                },
            )(),
            "model",
        ),
    )
    atoms = await extract_atoms("I meditate daily.", "That is good.", [])
    assert atoms == []


def test_model_import():
    from services.layered_memory.models import MemoryAtom

    atom = MemoryAtom("x", "persona", 80, [], "s", {})
    assert atom.content == "x"
    assert atom.type == "persona"

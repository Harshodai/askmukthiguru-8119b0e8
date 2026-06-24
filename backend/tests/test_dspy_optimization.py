from pathlib import Path

from optimization.dspy.dataset import examples_from_question_bank, write_jsonl
from optimization.dspy.optimize import build_artifact


def test_question_bank_examples_are_compact():
    examples = examples_from_question_bank(limit=5)
    assert len(examples) == 5
    assert all(example.question for example in examples)
    assert all(example.category for example in examples)


def test_write_jsonl(tmp_path: Path):
    examples = examples_from_question_bank(limit=2)
    out = tmp_path / "examples.jsonl"
    write_jsonl(examples, out)
    assert out.read_text().count("\n") == 2


def test_build_artifact_writes_manifest(tmp_path: Path):
    out_dir = build_artifact(
        limit=3, report=None, artifact_dir=tmp_path / "askmukthiguru-dspy-test"
    )
    assert (out_dir / "manifest.json").exists()
    assert (out_dir / "examples.jsonl").exists()

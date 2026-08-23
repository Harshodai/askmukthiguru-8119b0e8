from pathlib import Path

from app.runtime_artifacts import RuntimeArtifact, inspect_runtime_artifacts


def test_runtime_artifact_inspection_reports_missing_assets(tmp_path: Path):
    present = tmp_path / "present.json"
    present.write_text("{}", encoding="utf-8")

    result = inspect_runtime_artifacts(
        (
            RuntimeArtifact("present", present),
            RuntimeArtifact("missing", tmp_path / "missing.json"),
        )
    )

    assert result["ok"] is False
    assert result["present"] == 1
    assert result["total"] == 2
    assert result["missing"] == ["missing"]
    assert result["artifacts"]["present"]["size_bytes"] == 2


def test_runtime_artifact_inspection_handles_directory(tmp_path: Path):
    directory = tmp_path / "reranker"
    directory.mkdir()
    (directory / "model.bin").write_bytes(b"1234")

    result = inspect_runtime_artifacts((RuntimeArtifact("reranker", directory),))

    assert result["ok"] is True
    assert result["missing"] == []
    assert result["artifacts"]["reranker"]["present"] is True
    assert result["artifacts"]["reranker"]["size_bytes"] == 4

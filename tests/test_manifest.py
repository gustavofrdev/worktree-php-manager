from pathlib import Path

from wtp.manifest import Manifest, ManifestStore


def test_manifest_round_trip_and_filter(tmp_path: Path) -> None:
    store = ManifestStore(tmp_path)
    store.save(Manifest("a", "x", "/p/a-x", "wtp/x", created_worktree=True))
    store.save(Manifest("b", "y", "/p/b-y", "wtp/y"))
    loaded = store.load("a-x")
    assert loaded is not None and loaded.created_worktree
    assert [m.slug for m in store.all_for("b")] == ["b-y"]
    store.delete("a-x")
    assert store.load("a-x") is None


def test_all_for_without_state_dir(tmp_path: Path) -> None:
    assert ManifestStore(tmp_path / "none").all_for(None) == []

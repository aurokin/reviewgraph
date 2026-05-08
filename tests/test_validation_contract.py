import importlib.util
import tomllib
from pathlib import Path


LIVE_MARKERS = {
    "live_read": "REVIEWGRAPH_LIVE_READ",
    "live_llm": "REVIEWGRAPH_LIVE_LLM",
    "live_post": "REVIEWGRAPH_LIVE_POST",
}


class FakePytestItem:
    def __init__(self, marker_name: str) -> None:
        self.keywords = {marker_name: True}
        self.added_markers: list[object] = []

    def add_marker(self, marker: object) -> None:
        self.added_markers.append(marker)


def test_live_markers_are_registered_in_pyproject() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())
    markers = pyproject["tool"]["pytest"]["ini_options"]["markers"]

    for marker_name, env_var in LIVE_MARKERS.items():
        assert any(entry.startswith(f"{marker_name}:") and env_var in entry for entry in markers)


def test_live_markers_are_skipped_by_default_without_env_opt_in(monkeypatch) -> None:
    conftest = _load_conftest()
    items = [FakePytestItem(marker_name) for marker_name in LIVE_MARKERS]
    for env_var in LIVE_MARKERS.values():
        monkeypatch.delenv(env_var, raising=False)

    conftest.pytest_collection_modifyitems(config=None, items=items)

    assert [len(item.added_markers) for item in items] == [1, 1, 1]
    for item, env_var in zip(items, LIVE_MARKERS.values(), strict=True):
        assert env_var in item.added_markers[0].kwargs["reason"]


def test_live_markers_are_not_skipped_when_env_opt_in_is_present(monkeypatch) -> None:
    conftest = _load_conftest()
    items = [FakePytestItem(marker_name) for marker_name in LIVE_MARKERS]
    for env_var in LIVE_MARKERS.values():
        monkeypatch.setenv(env_var, "1")

    conftest.pytest_collection_modifyitems(config=None, items=items)

    assert [item.added_markers for item in items] == [[], [], []]


def _load_conftest():
    spec = importlib.util.spec_from_file_location("reviewgraph_tests_conftest", Path("tests/conftest.py"))
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module

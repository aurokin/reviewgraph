import importlib
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


def test_ruff_complexity_lint_is_configured() -> None:
    pyproject = tomllib.loads(Path("pyproject.toml").read_text())
    test_dependencies = pyproject["project"]["optional-dependencies"]["test"]
    ruff = pyproject["tool"]["ruff"]
    lint = pyproject["tool"]["ruff"]["lint"]

    assert "ruff==0.15.12" in test_dependencies
    assert ruff["required-version"] == "==0.15.12"
    assert "C901" in lint["select"]
    assert lint["mccabe"]["max-complexity"] == 30


def test_default_handoff_docs_include_ruff_and_test_extra_setup() -> None:
    docs = {
        Path("README.md"): (
            "Default handoff validation",
            'Default handoff validation assumes the project test extra is installed (`python -m pip install -e ".[test]"`):',
        ),
        Path("docs/implementation/README.md"): (
            "Run the default handoff validation sequence",
            'The sequence assumes the project test extra is installed (`python -m pip install -e ".[test]"`)',
        ),
        Path("docs/harnesses/harness-engineering.md"): (
            "For implementation handoff",
            'The default validation sequence assumes the project test extra is installed (`python -m pip install -e ".[test]"`).',
        ),
    }
    expected_commands = [
        "python -m pytest -q",
        "python -m ruff check src tests scripts",
        "python -m py_compile src/reviewgraph/*.py",
        "python scripts/check_docs.py",
        "git diff --check",
    ]

    for path, (marker, setup_text) in docs.items():
        text = path.read_text()
        default_commands = _bash_block_after_marker(text, marker)

        assert setup_text in _section_after_marker(text, marker)
        assert default_commands == expected_commands


def test_compatibility_import_surfaces_remain_available() -> None:
    expected_names = {
        "reviewgraph.posting": ("canonical_json_hash", "marker_payload_hash", "sha256_text"),
        "reviewgraph.runner": ("FixtureError", "ClarificationRequest"),
        "reviewgraph.graph": ("ReviewStage",),
        "reviewgraph.writer_fake": ("build_finalized_issue_comment_writer_input",),
    }

    for module_name, names in expected_names.items():
        module = importlib.import_module(module_name)
        for name in names:
            assert hasattr(module, name)


def _bash_block_after_marker(text: str, marker: str) -> list[str]:
    marker_index = text.index(marker)
    fence_index = text.index("```bash", marker_index)
    block_start = text.index("\n", fence_index) + 1
    block_end = text.index("```", block_start)
    return [line.strip() for line in text[block_start:block_end].splitlines() if line.strip()]


def _section_after_marker(text: str, marker: str) -> str:
    marker_index = text.index(marker)
    next_heading_index = text.find("\n## ", marker_index + len(marker))
    if next_heading_index == -1:
        return text[marker_index:]
    return text[marker_index:next_heading_index]


def _load_conftest():
    spec = importlib.util.spec_from_file_location("reviewgraph_tests_conftest", Path("tests/conftest.py"))
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module

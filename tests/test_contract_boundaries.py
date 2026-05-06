import ast
import dataclasses
import inspect
import json
import subprocess
import sys
from pathlib import Path


def test_models_module_is_leaf_contract_module() -> None:
    imports = _imports(Path("src/reviewgraph/models.py"))

    assert imports <= {
        "__future__",
        "dataclasses",
        "enum",
        "hashlib",
        "json",
        "types",
        "typing",
    }


def test_contract_and_config_modules_do_not_import_side_effect_boundaries() -> None:
    forbidden_roots = {
        "github",
        "langgraph",
        "llm",
        "openai",
        "requests",
    }
    forbidden_reviewgraph_modules = {
        "reviewgraph.approval",
        "reviewgraph.finalization",
        "reviewgraph.github",
        "reviewgraph.llm",
        "reviewgraph.writer",
    }

    for path in (Path("src/reviewgraph/models.py"), Path("src/reviewgraph/config.py")):
        imports = _imports(path)
        assert not ({name.split(".", 1)[0] for name in imports} & forbidden_roots)
        assert not (imports & forbidden_reviewgraph_modules)


def test_reviewer_context_module_does_not_import_side_effect_boundaries() -> None:
    forbidden_roots = {
        "github",
        "httpx",
        "langgraph",
        "llm",
        "openai",
        "requests",
        "socket",
        "subprocess",
        "urllib",
    }
    forbidden_reviewgraph_modules = {
        "reviewgraph.approval",
        "reviewgraph.finalization",
        "reviewgraph.github",
        "reviewgraph.llm",
        "reviewgraph.posting",
        "reviewgraph.writer",
    }

    imports = _imports(Path("src/reviewgraph/reviewer_context.py"))

    assert not ({name.split(".", 1)[0] for name in imports} & forbidden_roots)
    assert not (imports & forbidden_reviewgraph_modules)


def test_reviewer_context_shapes_do_not_accept_side_effect_handles() -> None:
    import reviewgraph.reviewer_context as reviewer_context

    forbidden_fragments = {
        "approval",
        "client",
        "finalization",
        "github",
        "http",
        "llm",
        "openai",
        "process",
        "session",
        "socket",
        "subprocess",
        "transport",
        "writer",
    }
    dataclass_types = (
        reviewer_context.ProviderRequestPreview,
        reviewer_context.ReviewerCapabilityPolicy,
        reviewer_context.ReviewerConfigMetadata,
        reviewer_context.ReviewerContextPackage,
        reviewer_context.ReviewerPromptInput,
    )
    allowed_boundary_fields = {
        "github_writes_available",
        "live_provider_calls_available",
        "provider",
        "raw_provider_submission_enabled",
    }

    for dataclass_type in dataclass_types:
        assert dataclasses.is_dataclass(dataclass_type)
        field_names = {field.name for field in dataclasses.fields(dataclass_type)}
        assert not _contains_forbidden_fragment(field_names - allowed_boundary_fields, forbidden_fragments)

    for function in (
        reviewer_context.build_provider_request_preview,
        reviewer_context.build_reviewer_context_package,
        reviewer_context.build_reviewer_prompt_input,
    ):
        parameter_names = set(inspect.signature(function).parameters)
        assert "config" not in parameter_names
        assert "config_map" not in parameter_names
        assert "reviewer_config_map" not in parameter_names
        assert not _contains_forbidden_fragment(parameter_names, forbidden_fragments)


def test_contract_imports_do_not_transitively_load_side_effect_modules() -> None:
    script = """
import json
import sys
import reviewgraph.models
import reviewgraph.config
forbidden = sorted(
    name for name in sys.modules
    if name.startswith(('reviewgraph.github', 'reviewgraph.llm', 'reviewgraph.writer', 'reviewgraph.approval', 'reviewgraph.finalization'))
    or name.split('.', 1)[0] in {'github', 'langgraph', 'llm', 'openai', 'requests'}
)
print(json.dumps(forbidden))
"""
    completed = subprocess.run(
        [sys.executable, "-c", script],
        check=True,
        capture_output=True,
        text=True,
        env={"PYTHONPATH": "src"},
    )

    assert json.loads(completed.stdout) == []


def _imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text())
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module)
    return imports


def _contains_forbidden_fragment(names: set[str], fragments: set[str]) -> bool:
    return any(fragment in name.casefold() for name in names for fragment in fragments)

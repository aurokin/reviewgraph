import ast
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

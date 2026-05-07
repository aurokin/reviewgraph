import os

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("REVIEWGRAPH_LIVE_READ") == "1":
        return
    skip_live_read = pytest.mark.skip(reason="set REVIEWGRAPH_LIVE_READ=1 to run live GitHub read smoke tests")
    for item in items:
        if "live_read" in item.keywords:
            item.add_marker(skip_live_read)

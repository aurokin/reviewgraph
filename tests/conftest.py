import os

import pytest


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    skip_live_read = pytest.mark.skip(reason="set REVIEWGRAPH_LIVE_READ=1 to run live GitHub read smoke tests")
    skip_live_post = pytest.mark.skip(reason="set REVIEWGRAPH_LIVE_POST=1 to run manual live GitHub post smoke tests")
    for item in items:
        if "live_read" in item.keywords and os.environ.get("REVIEWGRAPH_LIVE_READ") != "1":
            item.add_marker(skip_live_read)
        if "live_post" in item.keywords and os.environ.get("REVIEWGRAPH_LIVE_POST") != "1":
            item.add_marker(skip_live_post)

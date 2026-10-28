"""pytest fixtures and marker handling. Test data lives in tests/helpers.py."""

import pytest

from tests.helpers import FIXTURE_JUDGMENT, ROOT, has_live_keys
from core.judgments import JudgmentStore


@pytest.fixture
def store():
    return JudgmentStore([FIXTURE_JUDGMENT])


def pytest_collection_modifyitems(config, items):
    skip_live = pytest.mark.skip(reason="live keys absent")
    skip_data = pytest.mark.skip(reason="corpus data absent (run scripts/build_judgments.py)")
    data_ok = (ROOT / "data" / "judgments" / "judgments.jsonl").exists()
    for item in items:
        if "live" in item.keywords and not has_live_keys():
            item.add_marker(skip_live)
        if "corpus" in item.keywords and not data_ok:
            item.add_marker(skip_data)

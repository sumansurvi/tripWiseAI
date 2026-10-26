"""Phase 5 pytest fixtures."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

PHASE5_SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
PHASE3_SCRIPTS = (
    Path(__file__).resolve().parents[2]
    / "phase-03-embeddings-vector-store"
    / "scripts"
)
for _p in (str(PHASE5_SCRIPTS), str(PHASE3_SCRIPTS)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from tripwise_p3.warnings_util import suppress_vendor_noise  # noqa: E402

suppress_vendor_noise(quiet_http_logs=True)

from integration_helpers import require_live_stack  # noqa: E402


@pytest.fixture
def live_settings():
    return require_live_stack()

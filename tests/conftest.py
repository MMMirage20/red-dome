from __future__ import annotations

import pytest

from reddome.config.balance import Balance, load_balance


@pytest.fixture
def balance() -> Balance:
    return load_balance()

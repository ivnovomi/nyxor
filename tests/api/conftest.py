from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from nyxor.api.app import create_app


@pytest.fixture
def nyxor_test_client() -> Iterator[TestClient]:
    with TestClient(create_app()) as client:
        yield client

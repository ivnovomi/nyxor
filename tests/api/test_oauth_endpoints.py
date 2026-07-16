from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from nyxor.api.app import create_app


@pytest.fixture
def app():
    return create_app()


def test_approve_from_loopback_succeeds(app) -> None:
    with TestClient(app, base_url="http://127.0.0.1", client=("127.0.0.1", 12345)) as client:
        code_resp = client.post("/oauth/device/code")
        user_code = code_resp.json()["user_code"]

        approve_resp = client.post("/oauth/device/approve", params={"user_code": user_code})

        assert approve_resp.status_code == 200


def test_approve_from_a_remote_caller_is_rejected(app) -> None:
    # Without this check, any client that can reach the API could create a
    # device code and immediately self-approve it — no human involved.
    with TestClient(app, base_url="http://127.0.0.1", client=("203.0.113.5", 12345)) as client:
        code_resp = client.post("/oauth/device/code")
        user_code = code_resp.json()["user_code"]

        approve_resp = client.post("/oauth/device/approve", params={"user_code": user_code})

        assert approve_resp.status_code == 403


def test_approve_from_the_default_test_client_host_is_rejected(app) -> None:
    # TestClient's default synthetic client host ("testclient") isn't a
    # loopback address either, and must not be treated as one.
    with TestClient(app) as client:
        code_resp = client.post("/oauth/device/code")
        user_code = code_resp.json()["user_code"]

        approve_resp = client.post("/oauth/device/approve", params={"user_code": user_code})

        assert approve_resp.status_code == 403


def test_approve_with_a_spoofed_host_header_is_rejected_even_from_loopback(app) -> None:
    # DNS rebinding: an attacker's page can get a browser to genuinely
    # connect to 127.0.0.1 (so request.client.host is loopback) while the
    # browser still sends the original page's Host header — checking the
    # TCP peer alone isn't sufficient, the Host header itself must say
    # localhost too.
    with TestClient(app, base_url="http://attacker.example", client=("127.0.0.1", 12345)) as client:
        code_resp = client.post("/oauth/device/code")
        user_code = code_resp.json()["user_code"]

        approve_resp = client.post("/oauth/device/approve", params={"user_code": user_code})

        assert approve_resp.status_code == 403

"""Shared pytest fixtures for MTG Scripts."""

import socket
from typing import Never

import pytest
import requests


@pytest.fixture(autouse=True)
def block_unmarked_network(monkeypatch: pytest.MonkeyPatch, request: pytest.FixtureRequest) -> None:
    if request.node.get_closest_marker("network") is not None:
        return

    def fail_network(*args: object, **kwargs: object) -> Never:
        pytest.fail(
            "Unexpected network access: stub the request or mark this integration test with @pytest.mark.network"
        )

    monkeypatch.setattr(requests.sessions.Session, "request", fail_network)
    monkeypatch.setattr(socket.socket, "connect", fail_network)
    monkeypatch.setattr(socket.socket, "connect_ex", fail_network)

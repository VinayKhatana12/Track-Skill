"""Tests for the realtime WebSocket gateway."""

from fastapi.testclient import TestClient


def test_websocket_ping_pong(client: TestClient) -> None:
    with client.websocket_connect("/ws?channel=test") as websocket:
        welcome = websocket.receive_json()
        assert welcome["event"] == "connection.established"
        assert welcome["payload"]["role"] == "anonymous"
        assert welcome["payload"]["channels"] == ["public:test"]

        websocket.send_json({"event": "ping", "payload": {"sent_at": "now"}})
        pong = websocket.receive_json()
        assert pong["event"] == "pong"
        assert pong["payload"]["echo"] == {"sent_at": "now"}


def test_websocket_broadcasts_to_channel(client: TestClient) -> None:
    with (
        client.websocket_connect("/ws?channel=room") as first,
        client.websocket_connect("/ws?channel=room") as second,
    ):
        first.receive_json()  # welcome
        second.receive_json()  # welcome

        first.send_json({"event": "trainee.updated", "payload": {"id": 7}})
        received = second.receive_json()
        assert received["event"] == "trainee.updated"
        assert received["payload"] == {"id": 7}


def test_websocket_rejects_non_json_frames(client: TestClient) -> None:
    with client.websocket_connect("/ws?channel=test") as websocket:
        websocket.receive_json()  # welcome

        websocket.send_text("not-json")
        error = websocket.receive_json()
        assert error["event"] == "error"
        assert "JSON objects" in error["payload"]["message"]

def test_recent_reflects_say_and_messages(client):
    client.post("/say", json={"say": "recent-say-marker"})
    client.post("/messages", json={"say": "recent-message-marker"})

    response = client.get("/recent")
    assert response.status_code == 200
    body = response.json()

    assert body[0] == "recent-message-marker"  # most recent push is at index 0
    assert "recent-say-marker" in body
    assert len(body) <= 5


def test_recent_caps_at_five(client):
    for i in range(7):
        client.post("/say", json={"say": f"cap-test-{i}"})

    response = client.get("/recent")
    body = response.json()
    assert len(body) == 5
    assert body[0] == "cap-test-6"

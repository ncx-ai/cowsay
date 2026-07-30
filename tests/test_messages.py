def test_create_and_list_messages(client):
    response = client.post("/messages", json={"say": "test message one"})
    assert response.status_code == 200
    created = response.json()
    assert created["say"] == "test message one"
    assert isinstance(created["id"], int)
    assert "^__^" in created["cowsay"]


def test_create_message_dedups_exact_match(client):
    # A second insert would receive a new SERIAL id, so an identical id proves
    # the existing row was reused. Deliberately does NOT read GET /messages —
    # that response shape changes in Task 2.
    first = client.post("/messages", json={"say": "dedup-marker-xyz"}).json()
    second = client.post("/messages", json={"say": "dedup-marker-xyz"}).json()
    assert first["id"] == second["id"]


def test_create_message_returns_cowsay_art(client):
    created = client.post("/messages", json={"say": "art-marker"}).json()
    assert "art-marker" in created["cowsay"]
    assert "^__^" in created["cowsay"]


def test_cowsay_by_id(client):
    created = client.post("/messages", json={"say": "cowsay me"}).json()
    response = client.get(f"/messages/{created['id']}/cowsay")
    assert response.status_code == 200
    assert "cowsay me" in response.text
    assert "^__^" in response.text


def test_cowsay_by_id_not_found(client):
    response = client.get("/messages/999999999/cowsay")
    assert response.status_code == 404


def test_create_message_pushes_to_recent(client):
    from app.redis_client import RECENT_KEY, get_redis

    client.post("/messages", json={"say": "unique-marker-msg"})
    recent = get_redis().lrange(RECENT_KEY, 0, 4)
    assert "unique-marker-msg" in recent

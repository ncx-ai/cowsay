def test_create_and_list_messages(client):
    response = client.post("/messages", json={"say": "test message one"})
    assert response.status_code == 200
    created = response.json()
    assert created["say"] == "test message one"
    assert isinstance(created["id"], int)

    listing = client.get("/messages")
    assert listing.status_code == 200
    ids = [m["id"] for m in listing.json()]
    assert created["id"] in ids


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

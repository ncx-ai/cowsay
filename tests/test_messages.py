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


def test_messages_pagination_shape_and_bounds(client):
    # Unique per run: POST /messages dedups on exact match (Task 1), so fixed
    # text would insert nothing on a re-run and make ordering assertions flaky.
    import uuid

    run = uuid.uuid4().hex[:8]
    for i in range(3):
        client.post("/messages", json={"say": f"page-marker-{run}-{i}"})

    page = client.get("/messages", params={"limit": 2, "offset": 0}).json()
    assert len(page["items"]) == 2
    assert page["limit"] == 2
    assert page["offset"] == 0
    assert page["total"] >= 3

    # newest-first: the two most recent inserts are this run's -2 and -1
    says = [m["say"] for m in page["items"]]
    assert says == [f"page-marker-{run}-2", f"page-marker-{run}-1"]

    # and the second page continues the descending sequence
    page2 = client.get("/messages", params={"limit": 2, "offset": 2}).json()
    assert page2["offset"] == 2
    assert page2["items"][0]["say"] == f"page-marker-{run}-0"


def test_messages_default_pagination(client):
    page = client.get("/messages").json()
    assert page["limit"] == 10
    assert page["offset"] == 0
    assert len(page["items"]) <= 10


def test_messages_limit_is_capped(client):
    page = client.get("/messages", params={"limit": 1000}).json()
    assert page["limit"] == 100

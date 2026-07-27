from app.redis_client import RECENT_KEY, get_redis


def test_say_returns_cowsay_art(client):
    response = client.post("/say", json={"say": "hello world"})
    assert response.status_code == 200
    assert "hello world" in response.text
    assert "^__^" in response.text


def test_say_pushes_to_recent_list(client):
    client.post("/say", json={"say": "unique-marker-abc"})
    recent = get_redis().lrange(RECENT_KEY, 0, 4)
    assert "unique-marker-abc" in recent

def test_ui_is_served(client):
    response = client.get("/ui/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]


def test_ui_default_mode_is_light(client):
    response = client.get("/ui/")
    assert response.status_code == 200
    assert 'data-theme="light"' in response.text


def test_ui_respects_ui_mode_dark(client, monkeypatch):
    monkeypatch.setenv("UI_MODE", "dark")
    response = client.get("/ui/")
    assert response.status_code == 200
    assert 'data-theme="dark"' in response.text


def test_ui_invalid_mode_falls_back_to_light(client, monkeypatch):
    monkeypatch.setenv("UI_MODE", "bogus")
    response = client.get("/ui/")
    assert response.status_code == 200
    assert 'data-theme="light"' in response.text

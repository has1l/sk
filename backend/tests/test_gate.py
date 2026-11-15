"""Пароль на сайт публичного прототипа: своя страница входа и кука."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.gate import COOKIE, TRIES_PER_MINUTE, PasswordGate, token


def _client(password: str) -> TestClient:
    app = FastAPI()

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/templates")
    def templates() -> list:
        return []

    @app.get("/")
    def index() -> dict:
        return {"page": "app"}

    app.add_middleware(PasswordGate, password=password)
    return TestClient(app, follow_redirects=False)


def test_page_without_cookie_shows_our_login_form_not_the_browser_dialog():
    response = _client("sekret").get("/?dashboard=abc")
    assert response.status_code == 401
    assert "www-authenticate" not in response.headers
    assert "Клодик" in response.text
    assert 'value="/?dashboard=abc"' in response.text


def test_api_without_cookie_answers_json():
    response = _client("sekret").get("/api/templates")
    assert response.status_code == 401
    assert response.json() == {"detail": "Нужен пароль"}


def test_right_password_sets_cookie_and_returns_to_the_dashboard_link():
    client = _client("sekret")
    response = client.post("/login", data={"password": "sekret", "next": "/?dashboard=abc"})
    assert response.status_code == 303
    assert response.headers["location"] == "/?dashboard=abc"
    assert "HttpOnly" in response.headers["set-cookie"]
    assert "sekret" not in response.headers["set-cookie"]
    client.cookies.set(COOKIE, token("sekret"))
    assert client.get("/api/templates").status_code == 200


def test_wrong_password_shows_the_form_again_with_an_error():
    response = _client("sekret").post("/login", data={"password": "wrong", "next": "/"})
    assert response.status_code == 401
    assert "Пароль не подошёл" in response.text
    assert "set-cookie" not in response.headers


def test_forged_cookie_is_refused():
    client = _client("sekret")
    client.cookies.set(COOKIE, token("other"))
    assert client.get("/api/templates").status_code == 401


def test_login_cannot_redirect_to_another_site():
    response = _client("sekret").post("/login", data={"password": "sekret", "next": "//evil.example"})
    assert response.headers["location"] == "/"


def test_guessing_is_throttled():
    client = _client("sekret")
    for _ in range(TRIES_PER_MINUTE):
        client.post("/login", data={"password": "wrong"})
    assert client.post("/login", data={"password": "sekret"}).status_code == 429


def test_health_fonts_and_icon_stay_open():
    client = _client("sekret")
    assert client.get("/api/health").status_code == 200
    assert client.get("/fonts/inter-latin.woff2").status_code != 401


def test_empty_password_leaves_local_mode_open():
    assert _client("").get("/api/templates").status_code == 200

from app.core.config import get_settings

settings = get_settings()
PREFIX = settings.api_v1_prefix


async def test_register_creates_user_and_returns_token(client):
    payload = {"email": "new.user@example.com", "password": "supersecret123", "username": "new_user"}
    response = await client.post(f"{PREFIX}/auth/register", json=payload)

    assert response.status_code == 201
    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == "new.user@example.com"
    assert body["user"]["username"] == "new_user"
    assert "password" not in body["user"]


async def test_register_rejects_duplicate_email(client, test_user):
    payload = {"email": test_user.email, "password": "anotherpassword123", "username": "someone_else"}
    response = await client.post(f"{PREFIX}/auth/register", json=payload)
    assert response.status_code == 409


async def test_register_rejects_short_password(client):
    payload = {"email": "weak@example.com", "password": "1234567", "username": "weak"}
    response = await client.post(f"{PREFIX}/auth/register", json=payload)
    assert response.status_code == 422


async def test_login_with_correct_credentials(client, test_user):
    payload = {"email": test_user.email, "password": "correct-horse-battery-staple"}
    response = await client.post(f"{PREFIX}/auth/login", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["access_token"]
    assert body["user"]["email"] == test_user.email


async def test_login_with_wrong_password_fails(client, test_user):
    payload = {"email": test_user.email, "password": "wrong-password"}
    response = await client.post(f"{PREFIX}/auth/login", json=payload)
    assert response.status_code == 401


async def test_login_with_unknown_email_fails(client):
    payload = {"email": "ghost@example.com", "password": "whatever123"}
    response = await client.post(f"{PREFIX}/auth/login", json=payload)
    assert response.status_code == 401


async def test_me_requires_authentication(client):
    response = await client.get(f"{PREFIX}/auth/me")
    assert response.status_code == 401


async def test_me_rejects_garbage_token(client):
    response = await client.get(f"{PREFIX}/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert response.status_code == 401


async def test_me_returns_current_user(client, test_user, authed_client_factory):
    headers = authed_client_factory(test_user.id)
    response = await client.get(f"{PREFIX}/auth/me", headers=headers)

    assert response.status_code == 200
    body = response.json()
    assert body["username"] == "octocat"
    assert body["email"] == test_user.email


async def test_logout_is_a_noop_ok_response(client):
    response = await client.post(f"{PREFIX}/auth/logout")
    assert response.status_code == 200
    assert response.json() == {"ok": True}

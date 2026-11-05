"""How the app decides who's asking: the dev fallback locally, and in
production the Cloudflare Access token (verified) or, if it isn't configured,
the plain header."""
import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app import auth, config

AUD = "test-aud-tag"


@pytest.fixture(scope="module")
def keypair():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private, private.public_key()


def token(private, email="alice@example.com", aud=AUD, exp_in=300, **extra):
    claims = {"email": email, "aud": [aud], "exp": int(time.time()) + exp_in, **extra}
    return jwt.encode(claims, private, algorithm="RS256")


@pytest.fixture()
def production(monkeypatch, keypair):
    monkeypatch.setattr(config, "ENV", "production")
    monkeypatch.setattr(config, "CF_TEAM_DOMAIN", "team.cloudflareaccess.com")
    monkeypatch.setattr(config, "CF_ACCESS_AUD", AUD)
    monkeypatch.setattr(auth, "_signing_key", lambda _token: keypair[1])


def test_locally_with_no_header_you_are_the_dev_user(client):
    me = client.get("/api/me").json()
    assert me["email"] == config.DEV_USER_EMAIL and me["is_admin"] is True


def test_a_valid_token_identifies_the_person(client, production, keypair):
    resp = client.get("/api/me", headers={"Cf-Access-Jwt-Assertion": token(keypair[0], "Alice@Example.com")})
    assert resp.status_code == 200 and resp.json()["email"] == "alice@example.com"


@pytest.mark.parametrize(
    "build",
    [
        lambda private: token(private, aud="some-other-app"),
        lambda private: token(private, exp_in=-10),
        lambda private: token(private, email=None),
        lambda private: jwt.encode({"email": "alice@example.com", "aud": [AUD], "exp": int(time.time()) + 300}, "not-the-key", algorithm="HS256"),
        lambda private: "garbage",
    ],
    ids=["wrong audience", "expired", "no email", "wrong signature", "not a token"],
)
def test_a_bad_token_is_rejected(client, production, keypair, build):
    assert client.get("/api/me", headers={"Cf-Access-Jwt-Assertion": build(keypair[0])}).status_code == 401


def test_any_of_several_configured_audiences_is_accepted(client, production, keypair, monkeypatch):
    monkeypatch.setattr(config, "CF_ACCESS_AUD", f"some-other-app, {AUD}")
    resp = client.get("/api/me", headers={"Cf-Access-Jwt-Assertion": token(keypair[0])})
    assert resp.status_code == 200
    assert client.get("/api/me", headers={"Cf-Access-Jwt-Assertion": token(keypair[0], aud="neither")}).status_code == 401


def test_a_forged_plain_header_is_ignored_when_tokens_are_verified(client, production):
    resp = client.get("/api/me", headers={"Cf-Access-Authenticated-User-Email": "alice@example.com"})
    assert resp.status_code == 401


def test_no_identity_at_all_is_a_401_in_production(client, production):
    assert client.get("/api/trips").status_code == 401


def test_without_token_config_production_refuses_everything_even_with_the_header(client, monkeypatch):
    # A hostname that bypasses Access lets anyone send this header themselves.
    monkeypatch.setattr(config, "ENV", "production")
    monkeypatch.setattr(config, "CF_ACCESS_AUD", None)
    assert client.get("/api/me").status_code == 503
    assert client.get("/api/me", headers={"Cf-Access-Authenticated-User-Email": "alice@example.com"}).status_code == 503


@pytest.mark.parametrize("pasted", ["team.cloudflareaccess.com", "https://team.cloudflareaccess.com/", " team.cloudflareaccess.com "])
def test_the_team_domain_may_be_pasted_with_a_scheme_or_slash(monkeypatch, pasted):
    seen = []
    monkeypatch.setattr(auth, "_jwks_client", None)
    monkeypatch.setattr(config, "CF_TEAM_DOMAIN", pasted)
    monkeypatch.setattr(auth.jwt, "PyJWKClient", lambda url, **kw: seen.append(url) or object())
    try:
        auth._signing_key("token")
    except AttributeError:
        pass  # the stand-in client has no get_signing_key_from_jwt; only the URL matters
    assert seen == ["https://team.cloudflareaccess.com/cdn-cgi/access/certs"]
    monkeypatch.setattr(auth, "_jwks_client", None)

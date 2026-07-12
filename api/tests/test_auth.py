from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.main import app
from tests.conftest import make_token

router = APIRouter()

@router.get("/whoami")
def whoami(user_id: str = Depends(get_current_user)):
    return {"user_id": user_id}

app.include_router(router)


def test_valid_token(client, auth_headers):
    r = client.get("/whoami", headers=auth_headers)
    assert r.status_code == 200
    assert r.json() == {"user_id": "user-1"}

def test_missing_token(client):
    assert client.get("/whoami").status_code == 401

def test_bad_signature(client):
    import jwt, time
    bad = jwt.encode({"sub": "x", "aud": "authenticated", "exp": int(time.time()) + 60},
                     "wrong-secret-padded-to-thirty-two-bytes!", algorithm="HS256")
    assert client.get("/whoami", headers={"Authorization": f"Bearer {bad}"}).status_code == 401

def test_missing_sub(client):
    import jwt, time
    from app.config import get_settings
    tok = jwt.encode({"aud": "authenticated", "exp": int(time.time()) + 60},
                     get_settings().supabase_jwt_secret, algorithm="HS256")
    assert client.get("/whoami", headers={"Authorization": f"Bearer {tok}"}).status_code == 401

def test_wrong_audience(client):
    tok = make_token(aud="anon")
    assert client.get("/whoami", headers={"Authorization": f"Bearer {tok}"}).status_code == 401

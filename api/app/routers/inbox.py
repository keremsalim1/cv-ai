"""The inbox's HTTP surface: four endpoints, no logic.

Every failure the user can act on is a 409 carrying a code, never a message.
The services raise errors that quote Google's raw reply — useful in the log,
but it names our client id and the grant, so it stops here.
"""
import logging
from collections.abc import Iterator

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.auth import get_current_user
from app.services.inbox_connect import (
    ConnectionError_, connect_gmail, connection_status, disconnect_gmail,
)
from app.services.inbox_sync import sync_user_inbox
from app.services.llm import LLMClient, get_llm
from app.services.supabase_db import SupabaseDB, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/inbox", tags=["inbox"])

DISCONNECTED = {"code": "GMAIL_DISCONNECTED"}


def get_http() -> Iterator[httpx.Client]:
    # A client per request, closed with the request: `with` is what keeps the
    # connection pool from outliving it.
    with httpx.Client(timeout=30.0) as client:
        yield client


class ConnectRequest(BaseModel):
    code: str
    redirect_uri: str


@router.post("/connect")
def connect(
    req: ConnectRequest,
    user_id: str = Depends(get_current_user),
    db: SupabaseDB = Depends(get_db),
    http: httpx.Client = Depends(get_http),
):
    try:
        return connect_gmail(db, http, user_id, req.code, req.redirect_uri)
    except ConnectionError_ as exc:
        logger.warning("[inbox] connect failed for %s: %s", user_id, exc)
        raise HTTPException(status_code=409, detail=DISCONNECTED)


@router.delete("/connect")
def disconnect(
    user_id: str = Depends(get_current_user),
    db: SupabaseDB = Depends(get_db),
    http: httpx.Client = Depends(get_http),
):
    disconnect_gmail(db, http, user_id)
    return {"connected": False}


@router.get("/status")
def status(
    user_id: str = Depends(get_current_user),
    db: SupabaseDB = Depends(get_db),
):
    return connection_status(db, user_id)


@router.post("/sync")
def sync(
    user_id: str = Depends(get_current_user),
    db: SupabaseDB = Depends(get_db),
    http: httpx.Client = Depends(get_http),
    llm: LLMClient = Depends(get_llm),
):
    try:
        report = sync_user_inbox(db, http, llm, user_id)
    except ConnectionError_ as exc:
        # The grant is gone. Say so, so the UI can offer reconnection instead of
        # showing stale stages forever.
        logger.warning("[inbox] sync blocked for %s: %s", user_id, exc)
        raise HTTPException(status_code=409, detail=DISCONNECTED)
    return {
        "scanned": report.scanned,
        "classified": report.classified,
        "created": report.created,
        "updated": report.updated,
        "partial": report.partial,
    }

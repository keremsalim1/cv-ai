"""The one function that runs a sync.

Everything else in this feature is a pure unit or a thin client; this is where
they meet. When background scanning is added later, cron calls this same
function and nothing else moves.

Every query here carries its own `user_id` filter. The service-role key bypasses
RLS, so that filter is the only thing standing between two users' mailboxes —
see supabase_db.py.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.services.inbox_classify import classify
from app.services.inbox_connect import access_token_for
from app.services.inbox_match import match_application
from app.services.inbox_stage import next_stage
from app.services.mailbox import GmailSource

logger = logging.getLogger(__name__)


@dataclass
class SyncReport:
    scanned: int = 0
    classified: int = 0
    created: int = 0
    updated: list[dict] = field(default_factory=list)
    partial: bool = False


def _default_source(http, access_token):
    return GmailSource(http, access_token)


def sync_user_inbox(db, http, llm, user_id: str, source_factory=None) -> SyncReport:
    source_factory = source_factory or _default_source
    owner = f"eq.{user_id}"

    connections = db.select("email_connections", {"user_id": owner, "select": "*"})
    if not connections:
        return SyncReport()
    connection = connections[0]

    # Raises ConnectionError_ when the user revoked us at Google; the router
    # turns that into a message rather than a silent empty result.
    access_token = access_token_for(db, http, user_id)

    fetched = source_factory(http, access_token).fetch_new(
        connection.get("last_history_id"))

    applications = db.select("applications", {"user_id": owner, "select": "*"})
    events = db.select("application_events", {
        "user_id": owner, "select": "message_id,thread_id,application_id"})
    seen = {e["message_id"] for e in events}
    threads = {e["thread_id"]: e["application_id"] for e in events if e.get("thread_id")}

    report = SyncReport(partial=fetched.partial)

    for msg in fetched.messages:
        report.scanned += 1
        if msg.message_id in seen:
            continue

        signal = classify(msg, llm)
        if not signal.job_related:
            continue
        report.classified += 1
        if signal.stage is None:
            # Nothing to attach an event to, and no stage to record. Leave it
            # for a later sync rather than inventing an application.
            continue

        application = match_application(msg, signal, applications, threads).application
        if application is None:
            application = db.insert("applications", {
                "user_id": user_id,
                "url": "",
                "company": signal.company,
                "title": signal.title,
                "status": "external",
                "source": "email",
                "stage": signal.stage,
                "stage_updated_at": _now(),
                "qa": {},
                "changes": [],
            })
            applications.append(application)
            report.created += 1
        else:
            # Read where it came from before anything writes over it: a db layer
            # that hands back live rows would otherwise turn the report into
            # "rejected -> rejected" and lose the transition the user wants told.
            from_stage = application.get("stage")
            moved = next_stage(from_stage, signal.stage)
            if moved:
                db.update("applications",
                          {"id": f"eq.{application['id']}", "user_id": owner},
                          {"stage": moved, "stage_updated_at": _now()})
                report.updated.append({
                    "application_id": application["id"],
                    "company": application.get("company"),
                    "from_stage": from_stage,
                    "to_stage": moved,
                })
                application["stage"] = moved

        db.insert("application_events", {
            "user_id": user_id,
            "application_id": application["id"],
            "source": "email",
            "message_id": msg.message_id,
            "thread_id": msg.thread_id,
            "from_address": msg.from_address,
            "subject": msg.subject,
            "received_at": msg.received_at,
            "detected_stage": signal.stage,
            "confidence": signal.confidence,
            "evidence": signal.evidence,
        }, on_conflict="user_id,message_id")
        seen.add(msg.message_id)
        threads[msg.thread_id] = application["id"]

    patch = {"last_synced_at": _now()}
    if not fetched.partial and fetched.cursor:
        # A truncated fetch must re-read its tail next time, so the cursor only
        # advances on a clean run.
        patch["last_history_id"] = fetched.cursor
    db.update("email_connections", {"user_id": owner}, patch)

    return report


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

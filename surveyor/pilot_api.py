"""Admin-only personal pilot, unreachable through the Telegram/public deployment."""

import threading
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from surveyor import codex_pilot
from surveyor.auth import roles
from surveyor.config import settings
from surveyor.db import audit, get_db
from surveyor.pilot_samples import SAMPLES, scan_png
from surveyor.schemas import Strict

router = APIRouter(prefix="/api/ai-pilot", dependencies=[Depends(roles("admin"))])
RUNNING = threading.Lock()
LOOPBACK = {"127.0.0.1", "::1", "localhost"}


def enabled():
    return (
        settings.codex_local_pilot
        and settings.app_env == "development"
        and settings.data_mode == "synthetic"
        and urlsplit(settings.public_url).hostname in LOOPBACK
    )


def local_only(request: Request):
    if (
        not enabled()
        or not request.client
        or request.client.host not in LOOPBACK
        or request.url.hostname not in LOOPBACK
        or any(h in request.headers for h in ("forwarded", "x-forwarded-for", "x-forwarded-host", "cf-ray"))
    ):
        raise HTTPException(404, "Локальный пилот Codex недоступен.")


class PilotInput(Strict):
    sample_id: Literal["text", "scan", "missing"]


@router.get("", dependencies=[Depends(local_only)])
def status():
    return {
        **codex_pilot.connection(),
        "samples": [
            {"id": key, "title": sample["title"], "text": sample["text"]} for key, sample in SAMPLES.items()
        ],
    }


@router.get("/sample.png", dependencies=[Depends(local_only)])
def sample_image():
    return Response(scan_png(), media_type="image/png")


@router.post("/run", dependencies=[Depends(local_only)])
def run(body: PilotInput, user=Depends(roles("admin")), db=Depends(get_db)):
    if not RUNNING.acquire(blocking=False):
        raise HTTPException(409, "Другой учебный запрос уже выполняется. Дождитесь результата.")
    try:
        result = codex_pilot.recognize(body.sample_id)
        audit(
            db,
            user,
            "codex.pilot",
            body.sample_id,
            {
                "synthetic_only": True,
                "matched_fields": sum(f["matches"] for f in result["fields"]),
                "total_fields": len(result["fields"]),
            },
        )
        db.commit()
        return result
    except codex_pilot.PilotError as exc:
        raise HTTPException(503, str(exc)) from None
    finally:
        RUNNING.release()

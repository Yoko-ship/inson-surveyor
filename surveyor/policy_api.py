from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from pydantic import Field

from surveyor.auth import current_user
from surveyor.config import settings
from surveyor.reserves import classify_rnp
from surveyor.schemas import Rate, RnpInput, Strict
from surveyor.tariff_policy import catalog, check_tariff

router = APIRouter(prefix="/api/policy")


def source_path():
    return settings.storage_dir / "policies" / f"{catalog()['id']}.pdf"


@router.get("/catalog")
def policy_catalog(user=Depends(current_user)):
    return {**catalog(), "source_available": source_path().is_file()}


@router.get("/source")
def policy_source(user=Depends(current_user)):
    import hashlib

    from fastapi import HTTPException

    path = source_path()
    if not path.is_file():
        raise HTTPException(404, "Исходный PDF не установлен на этом сервере")
    if hashlib.sha256(path.read_bytes()).hexdigest() != catalog()["sha256"]:
        raise HTTPException(409, "Исходный PDF не соответствует версии каталога")
    return FileResponse(path, media_type="application/pdf", filename="INSON-tariff-policy-2025-09-23.pdf")


class TariffCheck(Strict):
    code: str = Field(pattern=r"^[0-9]{4}$")
    rate: Rate | None = None
    variant: str | None = Field(default=None, max_length=60)
    commission: Rate | None = None
    component_rates: dict[str, Rate] = Field(default_factory=dict, max_length=10)


@router.post("/check")
def policy_check(body: TariffCheck, user=Depends(current_user)):
    return check_tariff(body.code, body.rate, body.variant, body.commission, body.component_rates)


@router.post("/rnp/classify")
def rnp_classification(body: RnpInput, user=Depends(current_user)):
    return classify_rnp(body.model_dump())


@router.get("/factors")
def factor_catalog(user=Depends(current_user)):
    import json
    from pathlib import Path

    return json.loads((Path(__file__).parent / "policies" / "tariff-factors-2026-10-02.json").read_text())

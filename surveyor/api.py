import hashlib
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse
from pydantic import Field, ValidationError
from sqlalchemy import delete, select, update

from surveyor.auth import (
    DUMMY_HASH,
    create_session,
    current_user,
    digest,
    hasher,
    roles,
    user_data,
    validate_telegram,
    verify_password,
)
from surveyor.calculations import loss_summary
from surveyor.config import settings
from surveyor.db import (
    Audit,
    Calibration,
    Channel,
    ClassTemplate,
    Decision,
    Document,
    ImportBatch,
    Indicator,
    LoginAttempt,
    Loss,
    Product,
    Report,
    Session,
    Survey,
    User,
    audit,
    get_db,
    now,
    uid,
)
from surveyor.documents import parse_document, read_table
from surveyor.reports import export_docx, export_pdf, sections
from surveyor.schemas import (
    EmployeeInput,
    IndicatorInput,
    LossInput,
    ProductInput,
    Strict,
    SurveyInput,
    TemplateInput,
)
from surveyor.services import build_report, context_for, survey_for
from surveyor.sources import collect_cbu, latest_indicators, store_indicator

router = APIRouter(prefix="/api")
admin = roles("admin")
actuary = roles("actuary")
manager = roles("admin", "actuary")


def output(row, *keys):
    return {k: getattr(row, k) for k in keys}


class Login(Strict):
    login: str = Field(max_length=100)
    password: str = Field(max_length=128)


class Password(Strict):
    old_password: str = Field(max_length=128)
    new_password: str = Field(min_length=8, max_length=128)


def limit_login(db, request, login):
    # The account bucket prevents distributed attempts; IP bucket limits username spraying.
    for raw in ["account:" + login.lower(), "ip:" + (request.client.host if request.client else "unknown")]:
        key = digest(raw)
        row = db.get(LoginAttempt, key)
        if row and row.reset_at > now() and row.attempts >= 10:
            raise HTTPException(429, "Слишком много попыток. Повторите через 15 минут")
        if not row:
            row = LoginAttempt(key=key, attempts=0, reset_at=now() + timedelta(minutes=15))
            db.add(row)
        if row.reset_at <= now():
            row.attempts, row.reset_at = 0, now() + timedelta(minutes=15)
        row.attempts += 1
    db.commit()


@router.post("/auth/login")
def login(body: Login, request: Request, response: Response, db=Depends(get_db)):
    limit_login(db, request, body.login)
    user = db.scalar(select(User).where(User.login == body.login.lower()))
    valid = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if not user or not valid or not user.active:
        raise HTTPException(401, "Неверный логин или пароль")
    session = create_session(db, user, response)
    audit(db, user, "auth.login", user.id)
    db.commit()
    return {"user": user_data(user), "csrf": session.csrf}


@router.get("/auth/me")
def me(request: Request, user=Depends(current_user)):
    return {"user": user_data(user), "csrf": request.state.session.csrf, "data_mode": settings.data_mode}


@router.post("/auth/password")
def password(
    body: Password, request: Request, response: Response, user=Depends(current_user), db=Depends(get_db)
):
    limit_login(db, request, user.login)
    if not verify_password(body.old_password, user.password_hash):
        raise HTTPException(400, "Неверный текущий пароль")
    if body.old_password == body.new_password:
        raise HTTPException(422, "Новый пароль должен отличаться")
    user.password_hash = hasher.hash(body.new_password)
    user.must_change_password = False
    db.execute(delete(Session).where(Session.user_id == user.id))
    audit(db, user, "auth.password_changed", user.id)
    session = create_session(db, user, response)
    return {"user": user_data(user), "csrf": session.csrf}


@router.post("/auth/logout")
def logout(request: Request, response: Response, user=Depends(current_user), db=Depends(get_db)):
    db.delete(request.state.session)
    db.commit()
    response.delete_cookie("session")
    return {"ok": True}


class TelegramAuth(Strict):
    init_data: str = Field(max_length=10000)


@router.post("/auth/telegram")
def telegram_login(body: TelegramAuth, request: Request, response: Response, db=Depends(get_db)):
    if not settings.telegram_bot_token:
        raise HTTPException(503, "Telegram не настроен")
    limit_login(db, request, "telegram")
    telegram_id = validate_telegram(body.init_data, settings.telegram_bot_token)
    user = db.scalar(select(User).where(User.telegram_id == telegram_id, User.active.is_(True)))
    if not user:
        raise HTTPException(
            403, "Администратор должен привязать ваш Telegram ID к сотруднику. Войдите с логином и паролем."
        )
    session = create_session(db, user, response)
    return {"user": user_data(user), "csrf": session.csrf}


@router.post("/auth/telegram/link")
def telegram_link(body: TelegramAuth, user=Depends(current_user), db=Depends(get_db)):
    if not settings.telegram_bot_token:
        raise HTTPException(503, "Telegram не настроен")
    user.telegram_id = validate_telegram(body.init_data, settings.telegram_bot_token)
    audit(db, user, "telegram.linked", user.id)
    db.commit()
    return {"user": user_data(user)}


@router.get("/products")
def products(history: bool = False, user=Depends(current_user), db=Depends(get_db)):
    rows = db.scalars(select(Product).order_by(Product.effective_from.desc(), Product.code)).all()
    seen, result = set(), []
    for row in rows:
        if history or (row.code not in seen and row.effective_from <= date.today()):
            result.append({**row.data, "id": row.id})
            seen.add(row.code)
    return result


def save_product(db, body, user):
    existing = db.scalar(
        select(Product).where(Product.code == body.code, Product.effective_from == body.effective_from)
    )
    if existing:
        raise HTTPException(409, "Версия с этой датой уже существует. Выберите новую дату действия")
    from surveyor.tariff_policy import validate_product

    data = body.model_dump(mode="json")
    source = validate_product(data)
    if source:
        data["tariff_policy"] = source
    row = Product(code=body.code, effective_from=body.effective_from, data=data)
    db.add(row)
    db.flush()
    audit(db, user, "product.version_created", row.id, row.data)
    return row


@router.post("/admin/products", status_code=201)
def add_product(body: ProductInput, user=Depends(admin), db=Depends(get_db)):
    row = save_product(db, body, user)
    db.commit()
    return {**row.data, "id": row.id}


@router.get("/admin/employees")
def employees(user=Depends(admin), db=Depends(get_db)):
    return [user_data(u) for u in db.scalars(select(User).order_by(User.created_at.desc())).all()]


@router.post("/admin/employees", status_code=201)
def add_employee(body: EmployeeInput, user=Depends(admin), db=Depends(get_db)):
    data = body.model_dump(exclude={"password"})
    data["login"] = data["login"].lower()
    row = User(**data, password_hash=hasher.hash(body.password))
    db.add(row)
    db.flush()
    audit(db, user, "employee.created", row.id, data)
    db.commit()
    return user_data(row)


class EmployeeUpdate(Strict):
    active: bool
    role: Literal["employee", "underwriter", "actuary", "admin"]


@router.patch("/admin/employees/{employee_id}")
def edit_employee(employee_id: str, body: EmployeeUpdate, user=Depends(admin), db=Depends(get_db)):
    row = db.get(User, employee_id)
    if not row:
        raise HTTPException(404, "Сотрудник не найден")
    if row.id == user.id and (not body.active or body.role != "admin"):
        raise HTTPException(422, "Нельзя отключить или понизить собственную учётную запись")
    row.active, row.role = body.active, body.role
    db.execute(delete(Session).where(Session.user_id == row.id))
    audit(db, user, "employee.updated", row.id, body.model_dump())
    db.commit()
    return user_data(row)


@router.get("/templates")
def templates(user=Depends(current_user), db=Depends(get_db)):
    rows = db.scalars(select(ClassTemplate).order_by(ClassTemplate.created_at.desc())).all()
    seen, result = set(), []
    for row in rows:
        if row.class_code not in seen:
            result.append({**row.data, "id": row.id, "approved_by": row.approved_by})
            seen.add(row.class_code)
    return result


@router.post("/admin/templates", status_code=201)
def add_template(body: TemplateInput, user=Depends(manager), db=Depends(get_db)):
    row = ClassTemplate(class_code=body.class_code, data=body.model_dump(mode="json"))
    db.add(row)
    db.flush()
    audit(db, user, "template.version_created", row.id)
    db.commit()
    return {"id": row.id}


@router.post("/admin/templates/{template_id}/approve")
def approve_template(template_id: str, user=Depends(actuary), db=Depends(get_db)):
    row = db.get(ClassTemplate, template_id)
    if not row:
        raise HTTPException(404, "Шаблон не найден")
    row.approved_by, row.approved_at = user.id, now()
    audit(db, user, "template.approved", row.id)
    db.commit()
    return {"ok": True}


class NewSurvey(Strict):
    title: str = Field(min_length=1, max_length=200)


@router.post("/surveys", status_code=201)
def create_survey(body: NewSurvey, user=Depends(current_user), db=Depends(get_db)):
    row = Survey(title=body.title, owner_id=user.id)
    db.add(row)
    db.flush()
    audit(db, user, "survey.created", row.id)
    db.commit()
    return output(row, "id", "title", "status", "revision")


@router.get("/surveys")
def surveys(user=Depends(current_user), db=Depends(get_db)):
    stmt = select(Survey).order_by(Survey.created_at.desc()).limit(200)
    if user.role == "employee":
        stmt = stmt.where(Survey.owner_id == user.id)
    return [
        output(r, "id", "title", "status", "owner_id", "created_at", "revision")
        for r in db.scalars(stmt).all()
    ]


@router.get("/surveys/{survey_id}")
def survey_detail(survey_id: str, user=Depends(current_user), db=Depends(get_db)):
    row = survey_for(db, survey_id, user)
    docs = db.scalars(select(Document).where(Document.survey_id == row.id)).all()
    reports = db.scalars(
        select(Report).where(Report.survey_id == row.id).order_by(Report.created_at.desc())
    ).all()
    return {
        **output(row, "id", "title", "status", "inputs", "revision", "owner_id"),
        "documents": [output(d, "id", "filename", "extracted") for d in docs],
        "reports": [output(r, "id", "created_at") for r in reports],
    }


@router.put("/surveys/{survey_id}")
def update_survey(survey_id: str, body: SurveyInput, user=Depends(current_user), db=Depends(get_db)):
    from surveyor.services import validate_borrower_document

    row = survey_for(db, survey_id, user, write=True)
    before = row.inputs
    data = body.model_dump(mode="json", exclude={"revision"})
    validate_borrower_document(db, row.id, data)
    changed = db.execute(
        update(Survey)
        .where(Survey.id == row.id, Survey.revision == body.revision)
        .values(inputs=data, revision=body.revision + 1, status="draft")
    )
    if changed.rowcount != 1:
        raise HTTPException(409, "Осмотр изменён в другой вкладке. Обновите страницу")
    audit(db, user, "survey.inputs_changed", row.id, {"before": before, "after": data})
    db.commit()
    return {"revision": body.revision + 1}


async def upload_bytes(file):
    data = await file.read(settings.max_upload_bytes + 1)
    await file.close()
    if len(data) > settings.max_upload_bytes:
        raise HTTPException(413, "Максимальный размер файла — 15 МБ")
    if not data:
        raise HTTPException(422, "Файл пуст")
    return data


@router.post("/surveys/{survey_id}/documents", status_code=201)
async def upload_document(survey_id: str, file: UploadFile, user=Depends(current_user), db=Depends(get_db)):
    row = survey_for(db, survey_id, user, write=True)
    existing = db.scalars(select(Document).where(Document.survey_id == row.id)).all()
    if len(existing) >= 20:
        raise HTTPException(422, "Максимум 20 файлов на осмотр")
    data = await upload_bytes(file)
    filename = Path(file.filename or "file").name[:250]
    try:
        extracted = parse_document(data, filename, settings.max_document_pages)
    except ValueError:
        raise
    except Exception:
        raise HTTPException(422, "Файл повреждён или формат не поддерживается") from None
    sha = hashlib.sha256(data).hexdigest()
    if any(d.sha256 == sha for d in existing):
        raise HTTPException(409, "Этот файл уже загружен")
    path = settings.storage_dir / (uid() + Path(filename).suffix.lower())
    path.write_bytes(data)
    path.chmod(0o600)
    document = Document(survey_id=row.id, filename=filename, path=str(path), sha256=sha, extracted=extracted)
    db.add(document)
    row.revision += 1
    row.status = "draft"
    row.inputs = {**row.inputs, "manual_review_confirmed": False} if row.inputs else {}
    db.flush()
    audit(db, user, "document.uploaded", document.id, {"filename": filename, "sha256": sha})
    db.commit()
    return {**output(document, "id", "filename", "extracted"), "revision": row.revision}


@router.get("/documents/{document_id}/download")
def download_document(document_id: str, user=Depends(current_user), db=Depends(get_db)):
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(404, "Документ не найден")
    survey_for(db, doc.survey_id, user)
    return FileResponse(doc.path, filename=doc.filename, media_type="application/octet-stream")


@router.post("/calculate")
def calculator(body: SurveyInput, user=Depends(current_user), db=Depends(get_db)):
    *_, calc = context_for(db, body.model_dump(mode="json"))
    return calc


@router.post("/surveys/{survey_id}/reports", status_code=201)
def generate_report(survey_id: str, user=Depends(current_user), db=Depends(get_db)):
    row = survey_for(db, survey_id, user, write=True)
    report = build_report(db, row, user)
    return {"id": report.id, "snapshot": report.snapshot}


def report_for(db, report_id, user):
    row = db.get(Report, report_id)
    if not row:
        raise HTTPException(404, "Акт не найден")
    survey_for(db, row.survey_id, user)
    return row


@router.get("/reports/{report_id}")
def report_detail(report_id: str, user=Depends(current_user), db=Depends(get_db)):
    report = report_for(db, report_id, user)
    decisions = db.scalars(
        select(Decision).where(Decision.report_id == report.id).order_by(Decision.created_at)
    ).all()
    return {
        **output(report, "id", "snapshot", "created_at"),
        "sections": [{"title": title, "lines": lines} for title, lines in sections(report)[1]],
        "decisions": [output(d, "id", "user_id", "data", "created_at") for d in decisions],
    }


@router.get("/reports/{report_id}/export/{fmt}")
def export_report(
    report_id: str, fmt: Literal["pdf", "docx"], user=Depends(current_user), db=Depends(get_db)
):
    report = report_for(db, report_id, user)
    data = export_pdf(report) if fmt == "pdf" else export_docx(report)
    media = (
        "application/pdf"
        if fmt == "pdf"
        else "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    return Response(
        data,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="surveyor-{report.id}.{fmt}"'},
    )


class Underwriting(Strict):
    decision: Literal["approved", "changes_requested", "rejected"]
    comment: str = Field(min_length=3, max_length=3000)


@router.post("/reports/{report_id}/decision")
def decision(report_id: str, body: Underwriting, user=Depends(roles("underwriter")), db=Depends(get_db)):
    report = report_for(db, report_id, user)
    survey = db.get(Survey, report.survey_id)
    if survey.revision != report.snapshot["survey_revision"]:
        raise HTTPException(409, "Осмотр изменился после акта. Сформируйте новый акт")
    if body.decision == "approved" and report.snapshot["calculation"]["status"] != "calculated":
        raise HTTPException(422, "Нельзя утвердить акт без определённой ставки")
    db.add(Decision(report_id=report.id, user_id=user.id, data=body.model_dump()))
    survey.status = body.decision
    audit(db, user, "underwriting.decision", report.id, body.model_dump())
    db.commit()
    return {"ok": True}


@router.post("/reports/{report_id}/telegram")
async def send_report(report_id: str, user=Depends(current_user), db=Depends(get_db)):
    from surveyor.telegram import call_telegram

    report = report_for(db, report_id, user)
    if not user.telegram_id:
        raise HTTPException(422, "Сначала привяжите Telegram и нажмите /start в боте")
    payload = export_pdf(report)
    await call_telegram(
        "sendDocument",
        data={
            "chat_id": user.telegram_id,
            "caption": "Сюрвейерский акт. Подлежит подтверждению андеррайтером.",
        },
        files={"document": (f"surveyor-{report.id}.pdf", payload, "application/pdf")},
    )
    audit(db, user, "report.telegram_sent", report.id)
    db.commit()
    return {"ok": True}


@router.get("/admin/losses")
def losses(user=Depends(manager), db=Depends(get_db)):
    return loss_summary([r.data for r in db.scalars(select(Loss)).all()])


def save_loss(db, data, user):
    if not db.scalar(select(Product).where(Product.code == data.product_code)):
        raise HTTPException(422, "Неизвестный продукт")
    if data.year >= date.today().year:
        raise HTTPException(422, "Загрузите завершённый календарный год")
    row = db.scalar(select(Loss).where(Loss.product_code == data.product_code, Loss.year == data.year))
    if not row:
        row = Loss(product_code=data.product_code, year=data.year, data={})
        db.add(row)
    before = row.data
    row.data = data.model_dump(mode="json")
    db.flush()
    audit(db, user, "loss.saved", row.id, {"before": before, "after": row.data})


@router.post("/admin/losses")
def add_loss(body: LossInput, user=Depends(manager), db=Depends(get_db)):
    save_loss(db, body, user)
    db.commit()
    return {"ok": True}


class CalibrationInput(Strict):
    product_code: str = Field(max_length=60)
    target_loss_ratio: Annotated[float, Field(gt=0, le=1)]
    rationale: str = Field(min_length=10, max_length=2000)


@router.post("/admin/calibrations")
def calibrate(body: CalibrationInput, user=Depends(actuary), db=Depends(get_db)):
    from decimal import Decimal

    rows = db.scalars(
        select(Loss).where(
            Loss.product_code == body.product_code,
            Loss.year >= date.today().year - 3,
            Loss.year < date.today().year,
        )
    ).all()
    if len(rows) != 3 or any(not r.data.get("premiums") or Decimal(r.data["premiums"]) <= 0 for r in rows):
        raise HTTPException(422, "Нужны убытки и положительные премии за три последних полных года")
    ratio = sum(Decimal(r.data["payments"]) for r in rows) / sum(Decimal(r.data["premiums"]) for r in rows)
    adjustment = max(Decimal("-0.2"), min(Decimal("0.2"), ratio / Decimal(str(body.target_loss_ratio)) - 1))
    data = {
        "adjustment": str(adjustment),
        "loss_ratio": str(ratio),
        "target_loss_ratio": str(body.target_loss_ratio),
        "rationale": body.rationale,
        "losses": loss_summary([r.data for r in rows]),
    }
    row = Calibration(product_code=body.product_code, data=data, approved_by=user.id)
    db.add(row)
    db.flush()
    audit(db, user, "calibration.approved", row.id, data)
    db.commit()
    return {**data, "id": row.id}


@router.post("/admin/imports/{kind}/preview")
async def preview_import(
    kind: Literal["products", "losses"], file: UploadFile, user=Depends(admin), db=Depends(get_db)
):
    rows = read_table(await upload_bytes(file), file.filename or "")
    results, seen = [], set()
    codes = set(db.scalars(select(Product.code)).all())
    for index, row in enumerate(rows, 2):
        try:
            if "effective_from" in row:
                row["effective_from"] = str(row["effective_from"])[:10]
            if "program_rates" in row and isinstance(row["program_rates"], str):
                row["program_rates"] = json.loads(row["program_rates"])
            if kind == "products":
                item = ProductInput.model_validate(row)
                key = (item.code, item.effective_from)
                if db.scalar(
                    select(Product).where(
                        Product.code == item.code, Product.effective_from == item.effective_from
                    )
                ):
                    raise ValueError("Версия на эту дату уже существует")
                action = "update" if item.code in codes else "add"
            else:
                item = LossInput.model_validate(row)
                key = (item.product_code, item.year)
                if item.product_code not in codes:
                    raise ValueError("Неизвестный код продукта")
                if item.year >= date.today().year:
                    raise ValueError("Год должен быть завершён")
                action = (
                    "update"
                    if db.scalar(
                        select(Loss).where(Loss.product_code == item.product_code, Loss.year == item.year)
                    )
                    else "add"
                )
            if key in seen:
                raise ValueError("Повторяющаяся строка в файле")
            seen.add(key)
            results.append({"row": index, "action": action, "data": item.model_dump(mode="json")})
        except (ValidationError, ValueError) as exc:
            results.append({"row": index, "action": "error", "error": str(exc)[:1000]})
    batch = ImportBatch(user_id=user.id, kind=kind, data={"rows": results})
    db.add(batch)
    db.commit()
    return {"id": batch.id, "rows": results, "can_confirm": not any(r["action"] == "error" for r in results)}


@router.post("/admin/imports/{batch_id}/confirm")
def confirm_import(batch_id: str, user=Depends(admin), db=Depends(get_db)):
    batch = db.get(ImportBatch, batch_id)
    if not batch or batch.user_id != user.id or batch.kind not in {"products", "losses"}:
        raise HTTPException(404, "Импорт не найден")
    if batch.consumed or batch.created_at < now() - timedelta(hours=1):
        raise HTTPException(409, "Импорт уже сохранён или устарел")
    if any(r["action"] == "error" for r in batch.data["rows"]):
        raise HTTPException(422, "Сначала исправьте ошибки файла")
    claim = db.execute(
        update(ImportBatch)
        .where(ImportBatch.id == batch.id, ImportBatch.consumed.is_(False))
        .values(consumed=True)
    )
    if claim.rowcount != 1:
        raise HTTPException(409, "Импорт уже сохранён")
    for row in batch.data["rows"]:
        if batch.kind == "products":
            save_product(db, ProductInput.model_validate(row["data"]), user)
        else:
            save_loss(db, LossInput.model_validate(row["data"]), user)
    audit(db, user, "import.confirmed", batch.id)
    db.commit()
    return {"ok": True, "count": len(batch.data["rows"])}


@router.get("/sources")
def sources(user=Depends(current_user), db=Depends(get_db)):
    from surveyor.references import latest_references

    return {
        "references": latest_references(db),
        "channels": [
            output(c, "code", "data", "enabled", "last_attempt", "last_success", "error")
            for c in db.scalars(select(Channel)).all()
        ],
        "indicators": latest_indicators(db),
    }


@router.post("/admin/sources/cbu/collect")
def collect(user=Depends(manager), db=Depends(get_db)):
    return collect_cbu(db, force=True)


@router.post("/admin/sources/{channel_code}/indicators")
def add_indicator(channel_code: str, body: IndicatorInput, user=Depends(manager), db=Depends(get_db)):
    if not db.get(Channel, channel_code):
        raise HTTPException(404, "Канал не найден")
    if body.observation_date > date.today():
        raise HTTPException(422, "Дата наблюдения не может быть в будущем")
    row = store_indicator(db, channel_code, body, user)
    db.commit()
    return {"id": row.id}


@router.post("/admin/indicators/{indicator_id}/approve")
def approve_indicator(indicator_id: str, user=Depends(actuary), db=Depends(get_db)):
    row = db.get(Indicator, indicator_id)
    if not row:
        raise HTTPException(404, "Показатель не найден")
    if row.data.get("reference_only") or row.data["metric"].startswith("napp_ref_"):
        raise HTTPException(422, "Справочный показатель не может стать тарифной поправкой")
    # New version preserves the original publication and report snapshots.
    new = Indicator(
        channel_code=row.channel_code,
        data={**row.data, "approved_by": user.id, "approved_at": now().isoformat()},
    )
    db.add(new)
    db.flush()
    audit(db, user, "indicator.approved", new.id, {"previous_id": row.id})
    db.commit()
    return {"id": new.id}


@router.get("/admin/indicators/history")
def indicator_history(user=Depends(manager), db=Depends(get_db)):
    return [
        output(r, "id", "channel_code", "data", "fetched_at")
        for r in db.scalars(select(Indicator).order_by(Indicator.fetched_at.desc()).limit(1000)).all()
    ]


@router.get("/admin/audit")
def audit_log(user=Depends(admin), db=Depends(get_db)):
    return [
        output(a, "id", "user_id", "action", "entity_id", "data", "created_at")
        for a in db.scalars(select(Audit).order_by(Audit.created_at.desc()).limit(200)).all()
    ]

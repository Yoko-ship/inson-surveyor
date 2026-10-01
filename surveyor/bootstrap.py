from datetime import date

from sqlalchemy import select

from surveyor.auth import hasher
from surveyor.config import settings
from surveyor.db import Channel, ClassTemplate, Product, SessionLocal, User
from surveyor.sources import CHANNELS


def bootstrap():
    with SessionLocal() as db:
        if not db.scalar(select(User).limit(1)) and settings.bootstrap_admin_password:
            if len(settings.bootstrap_admin_password) < 12:
                raise ValueError("Bootstrap password must contain at least 12 characters")
            db.add(
                User(
                    login=settings.bootstrap_admin_login,
                    name="Администратор",
                    phone="+00000000000",
                    role="admin",
                    password_hash=hasher.hash(settings.bootstrap_admin_password),
                    must_change_password=True,
                )
            )
        for code, domain, access, note, enabled in CHANNELS:
            if not db.get(Channel, code):
                db.add(
                    Channel(
                        code=code, data={"domain": domain, "access": access, "note": note}, enabled=enabled
                    )
                )
        if settings.data_mode == "synthetic" and not db.scalar(select(Product).limit(1)):
            for code, name, cls, basis in [
                ("DEMO-AUTO", "ДЕМО · Автотранспорт", "vehicle", "annual"),
                ("DEMO-FIX", "ДЕМО · Имущество, фиксированный", "property", "fixed"),
                ("DEMO-FIRE", "ДЕМО · Огонь и стихия", "fire", "annual"),
            ]:
                db.add(
                    Product(
                        code=code,
                        effective_from=date(2020, 1, 1),
                        data={
                            "code": code,
                            "name": name,
                            "class_code": cls,
                            "rate": "0.5",
                            "min_rate": "0.3",
                            "rate_type": basis,
                            "effective_from": "2020-01-01",
                            "program_rates": {},
                            "program_basis": "annual",
                        },
                    )
                )
        if not db.scalar(select(ClassTemplate).limit(1)):
            for cls, name in [
                ("vehicle", "Автотранспорт"),
                ("property", "Имущество"),
                ("fire", "Огонь и стихия"),
            ]:
                db.add(
                    ClassTemplate(
                        class_code=cls,
                        data={
                            "class_code": cls,
                            "name": name,
                            "feature_weights": {
                                "visible_damage": 25,
                                "poor_maintenance": 25,
                                "no_protection": 20,
                                "hazardous_location": 30,
                            },
                            "moderate_threshold": 20,
                            "high_threshold": 50,
                            "multipliers": {"low": "1", "moderate": "1.15", "high": "1.35"},
                            "max_adjustment": "0.2",
                            "risk_shares": {},
                            "indicator_metrics": ["regional_risk"],
                            "clauses": [
                                "Провести осмотр объекта и подтвердить страховую стоимость.",
                                "Условия и франшиза определяются андеррайтером по правилам продукта.",
                            ],
                        },
                    )
                )
        from surveyor.source_adapters import seed_access_review, seed_napp, seed_public_channels

        seed_public_channels(db)
        seed_napp(db)
        seed_access_review(db)
        db.commit()

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator

Money = Annotated[Decimal, Field(ge=0, le=Decimal("1e18"), max_digits=22, decimal_places=4)]
Rate = Annotated[Decimal, Field(ge=0, le=100, max_digits=12, decimal_places=8)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProductInput(Strict):
    code: str = Field(min_length=1, max_length=60, pattern=r"^[A-Za-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=200)
    class_code: str = Field(min_length=1, max_length=50)
    rate: Rate
    min_rate: Rate
    rate_type: Literal["annual", "fixed", "program", "normative"]
    effective_from: date
    program_rates: dict[str, Rate] = Field(default_factory=dict, max_length=100)
    program_basis: Literal["annual", "fixed"] = "annual"
    normative_basis: Literal["annual", "fixed"] | None = None
    normative_source: HttpUrl | None = None

    @model_validator(mode="after")
    def rates(self):
        if self.rate < self.min_rate or any(v < self.min_rate for v in self.program_rates.values()):
            raise ValueError("Ставка не может быть ниже минимальной")
        if self.rate_type == "normative" and (not self.normative_basis or not self.normative_source):
            raise ValueError("Для нормативного тарифа нужны формула и ссылка на акт")
        return self


class EmployeeInput(Strict):
    login: str = Field(min_length=3, max_length=100, pattern=r"^[a-zA-Z0-9_.-]+$")
    password: str = Field(min_length=8, max_length=128)
    phone: str = Field(pattern=r"^\+[0-9]{9,15}$")
    name: str = Field(min_length=1, max_length=200)
    position: str = Field(default="", max_length=200)
    department: str = Field(default="", max_length=200)
    branch: str = Field(default="", max_length=200)
    role: Literal["employee", "underwriter", "actuary", "admin"] = "employee"
    telegram_id: str | None = Field(default=None, pattern=r"^[1-9][0-9]{4,19}$")


class Comparable(Strict):
    label: str = Field(min_length=1, max_length=200)
    price: Money
    original_price: Money | None = None
    date: date
    source: str = Field(min_length=1, max_length=500)
    currency: str = Field(default="UZS", pattern=r"^[A-Z]{3}$")
    same_item: bool = True
    edit_reason: str = Field(default="", max_length=500)


class SurveyInput(Strict):
    revision: int = Field(ge=1)
    product_code: str = Field(min_length=1, max_length=60)
    insured_sum: Money
    object_value: Money
    region: str = Field(min_length=1, max_length=100)
    term_days: int = Field(default=365, ge=1, le=36500)
    tariff_date: date = Field(default_factory=date.today)
    object_type: Literal["vehicle", "equipment", "housing", "large", "other"] = "other"
    object_description: str = Field(default="", max_length=2000)
    features: list[str] = Field(default_factory=list, max_length=100)
    program: str | None = Field(default=None, max_length=100)
    declared_rate: Rate | None = None
    declared_premium: Money | None = None
    comparables: list[Comparable] = Field(default_factory=list, max_length=100)
    purchase_price: Money | None = None
    depreciation_percent: Rate = Decimal(0)
    appraiser_value: Money | None = None
    appraiser_source: str = Field(default="", max_length=500)
    appraiser_date: date | None = None
    second_method_value: Money | None = None
    second_method_source: str = Field(default="", max_length=500)
    second_method_date: date | None = None
    overrides: dict[str, str] = Field(default_factory=dict, max_length=30)
    override_reason: str = Field(default="", max_length=1000)
    language: Literal["ru", "uz", "en"] = "ru"
    manual_review_confirmed: bool = False

    @model_validator(mode="after")
    def edits(self):
        if self.overrides and not self.override_reason:
            raise ValueError("Укажите причину правок")
        if self.insured_sum <= 0 or self.object_value <= 0:
            raise ValueError("Суммы должны быть положительными")
        return self


class TemplateInput(Strict):
    class_code: str = Field(min_length=1, max_length=50)
    name: str = Field(min_length=1, max_length=200)
    feature_weights: dict[str, Annotated[int, Field(ge=0, le=100)]] = Field(
        default_factory=dict, max_length=100
    )
    moderate_threshold: int = Field(default=20, ge=1, le=100)
    high_threshold: int = Field(default=50, ge=1, le=100)
    multipliers: dict[Literal["low", "moderate", "high"], Annotated[Decimal, Field(ge=Decimal("0.5"), le=3)]]
    clauses: list[str] = Field(default_factory=list, max_length=50)
    risk_shares: dict[str, Rate] = Field(default_factory=dict, max_length=30)
    indicator_metrics: list[str] = Field(default_factory=list, max_length=50)
    max_adjustment: Annotated[Decimal, Field(ge=0, le=Decimal("0.5"))] = Decimal("0.2")

    @model_validator(mode="after")
    def thresholds(self):
        if self.high_threshold <= self.moderate_threshold:
            raise ValueError("Порог высокого риска должен быть выше умеренного")
        if set(self.multipliers) != {"low", "moderate", "high"}:
            raise ValueError("Нужны поправки для всех трёх уровней")
        if self.risk_shares and sum(self.risk_shares.values()) != 100:
            raise ValueError("Доли рисков должны давать 100%")
        return self


class LossInput(Strict):
    product_code: str = Field(min_length=1, max_length=60)
    name: str = Field(default="", max_length=200)
    year: int = Field(ge=1990, le=2100)
    claims: int = Field(ge=0, le=1000000000)
    payments: Money
    premiums: Money | None = None
    contracts: int | None = Field(default=None, ge=0, le=1000000000)


class IndicatorInput(Strict):
    metric: str = Field(min_length=1, max_length=100)
    region: str = Field(default="all", max_length=100)
    class_code: str = Field(default="all", max_length=50)
    object_type: str = Field(default="all", max_length=50)
    period: str = Field(min_length=1, max_length=100)
    value: Annotated[Decimal, Field(ge=0, le=Decimal("1e18"))]
    unit: str = Field(min_length=1, max_length=50)
    source_url: HttpUrl
    observation_date: date
    stale_days: int = Field(default=365, ge=1, le=3650)
    rate_adjustment: Annotated[Decimal, Field(ge=Decimal("-0.5"), le=Decimal("0.5"))] = Decimal(0)
    annual_market_rate: Rate | None = None

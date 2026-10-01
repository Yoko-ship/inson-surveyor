import re
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
    policy_code: str | None = Field(default=None, pattern=r"^[0-9]{4}$")
    policy_variant: str | None = Field(default=None, max_length=60)
    policy_current_confirmed: bool = False
    policy_basis_reference: str = Field(default="", max_length=1000)
    policy_terms_reference: str = Field(default="", max_length=1000)
    policy_approval_reference: str = Field(default="", max_length=1000)
    agent_commission_percent: Rate | None = None

    @model_validator(mode="after")
    def rates(self):
        if self.rate < self.min_rate or any(v < self.min_rate for v in self.program_rates.values()):
            raise ValueError("Ставка не может быть ниже минимальной")
        if self.rate_type == "normative" and (not self.normative_basis or not self.normative_source):
            raise ValueError("Для нормативного тарифа нужны формула и ссылка на акт")
        from surveyor.tariff_policy import validate_product

        validate_product(self.model_dump(mode="json"))
        return self


class RnpInput(Strict):
    insurance_class: int | None = Field(default=None, ge=1, le=17)
    borrower_nonrepayment: bool | None = None
    crop_insurance: bool | None = None
    open_dates: bool = False
    reinsurance: Literal["none", "proportional", "non_proportional"] = "none"

    @model_validator(mode="after")
    def exceptions(self):
        if self.borrower_nonrepayment is not None and self.insurance_class != 13:
            raise ValueError("Признак ответственности заёмщика относится только к классу 13")
        if self.crop_insurance is not None and self.insurance_class != 16:
            raise ValueError("Признак страхования урожая относится только к классу 16")
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


class BorrowerInput(Strict):
    organization_name: str = Field(min_length=3, max_length=200)
    bureau_name: str = Field(min_length=2, max_length=200)
    document_id: str = Field(min_length=1, max_length=36)
    report_date: date
    score: str = Field(min_length=1, max_length=100)
    score_scale: str = Field(min_length=1, max_length=200)
    summary: str = Field(default="", max_length=3000)

    @model_validator(mode="after")
    def evidence(self):
        if not re.search(r"\b(?:ООО|АО|ОАО|ЗАО|МЧЖ|АЖ|MChJ|AJ|LLC|JSC)\b", self.organization_name, re.I):
            raise ValueError("В блоке заёмщика укажите организацию с организационно-правовой формой")
        if self.report_date > date.today():
            raise ValueError("Дата отчёта кредитного бюро не может быть в будущем")
        return self


class SurveyInput(Strict):
    revision: int = Field(ge=1)
    product_code: str = Field(min_length=1, max_length=60)
    insured_sum: Money
    object_value: Money
    region: str = Field(min_length=1, max_length=100)
    term_days: int = Field(default=365, ge=1, le=36500)
    contract_start: date | None = None
    contract_end: date | None = None
    tariff_date: date = Field(default_factory=date.today)
    object_type: Literal["vehicle", "equipment", "housing", "large", "other"] = "other"
    object_description: str = Field(default="", max_length=2000)
    reference_ids: list[str] = Field(default_factory=list, max_length=30)
    features: list[str] = Field(default_factory=list, max_length=100)
    program: str | None = Field(default=None, max_length=100)
    declared_rate: Rate | None = None
    declared_premium: Money | None = None
    comparables: list[Comparable] = Field(default_factory=list, max_length=100)
    purchase_price: Money | None = None
    purchase_source: str = Field(default="", max_length=500)
    purchase_date: date | None = None
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
    borrower: BorrowerInput | None = None
    rnp_context: RnpInput | None = None

    @model_validator(mode="after")
    def edits(self):
        if self.overrides and not self.override_reason:
            raise ValueError("Укажите причину правок")
        if self.insured_sum <= 0 or self.object_value <= 0:
            raise ValueError("Суммы должны быть положительными")
        if self.contract_start and self.contract_end:
            days = (self.contract_end - self.contract_start).days
            if not 1 <= days <= 36500:
                raise ValueError("Дата окончания должна быть позже начала; максимум 100 лет")
            if "term_days" not in self.model_fields_set:
                self.term_days = days
            elif days != self.term_days and not self.override_reason:
                raise ValueError("Срок отличается от разницы дат. Укажите причину и правило подсчёта дней")
        if self.object_type == "equipment" and self.purchase_price is not None:
            if not self.purchase_source or not self.purchase_date:
                raise ValueError("Для цены покупки нужны источник и дата")
        for observed in (self.purchase_date, self.appraiser_date, self.second_method_date):
            if observed and observed > date.today():
                raise ValueError("Дата источника оценки не может быть в будущем")
        return self


class IndicatorRule(Strict):
    baseline: Annotated[Decimal, Field(gt=0, le=Decimal("1e18"))]
    sensitivity: Annotated[Decimal, Field(ge=Decimal("-1"), le=1)]
    max_adjustment: Annotated[Decimal, Field(ge=0, le=Decimal("0.5"))] = Decimal("0.1")
    object_types: list[Literal["vehicle", "equipment", "housing", "large", "other"]] = Field(
        min_length=1, max_length=5
    )


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
    valuation_outlier_low: Annotated[Decimal, Field(gt=0, le=1)] = Decimal("0.5")
    valuation_outlier_high: Annotated[Decimal, Field(ge=1, le=10)] = Decimal("1.5")
    valuation_tolerance: Annotated[Decimal, Field(ge=0, le=1)] = Decimal("0.15")
    large_object_threshold: Money | None = None
    clauses_translations: dict[Literal["uz", "en"], list[str]] = Field(default_factory=dict)
    indicator_rules: dict[str, IndicatorRule] = Field(default_factory=dict, max_length=50)

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

    @model_validator(mode="after")
    def observation_not_future(self):
        if self.observation_date > date.today():
            raise ValueError("Дата наблюдения не может быть в будущем")
        return self


class ReferenceInput(Strict):
    title: str = Field(min_length=1, max_length=300)
    source_url: HttpUrl
    text: str = Field(min_length=1, max_length=50000)
    kind: Literal["law", "seismic", "weather", "auction", "price", "registry", "other"] = "other"
    region: str = Field(default="all", max_length=100)
    class_code: str = Field(default="all", max_length=50)
    observation_date: date | None = None
    stale_days: int = Field(default=365, ge=1, le=3650)

    @model_validator(mode="after")
    def valid_date(self):
        if self.observation_date and self.observation_date > date.today():
            raise ValueError("Дата публикации не может быть в будущем")
        return self

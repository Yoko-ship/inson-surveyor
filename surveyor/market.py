"""Dated, comparable insurance quotes supplied by an administrator or actuary."""

from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import Field, HttpUrl, model_validator

from surveyor.calculations import number
from surveyor.schemas import IndicatorInput, Rate, Strict


class MarketQuoteInput(Strict):
    class_code: str = Field(min_length=1, max_length=50)
    region: str = Field(default="all", min_length=1, max_length=100)
    object_type: Literal["vehicle", "equipment", "housing", "large", "other"]
    rate: Rate = Field(gt=0)
    basis: Literal["annual", "fixed"]
    term_days: int = Field(ge=1, le=36500)
    coverage: str = Field(min_length=5, max_length=1000)
    source_url: HttpUrl
    observation_date: date
    stale_days: int = Field(default=180, ge=1, le=3650)

    @model_validator(mode="after")
    def comparable(self):
        if self.class_code == "all":
            raise ValueError("Рыночная котировка должна относиться к конкретному классу")
        if self.observation_date > date.today():
            raise ValueError("Дата котировки не может быть в будущем")
        return self

    def indicator(self):
        annual = self.rate * Decimal(365) / self.term_days if self.basis == "fixed" else self.rate
        normalized = IndicatorInput(
            metric="market_quote",
            class_code=self.class_code,
            region=self.region,
            object_type=self.object_type,
            period=self.observation_date.isoformat(),
            value=number(annual),
            unit="% per year",
            annual_market_rate=number(annual),
            source_url=self.source_url,
            observation_date=self.observation_date,
            stale_days=self.stale_days,
        ).model_dump(mode="json")
        return {**normalized, "quote": self.model_dump(mode="json")}

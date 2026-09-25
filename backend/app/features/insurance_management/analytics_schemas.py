from datetime import datetime

from pydantic import BaseModel, Field


class AnalyticsCapabilities(BaseModel):
    advisor_business: bool
    policy_pipeline: bool


class InsuranceAnalyticsSummary(BaseModel):
    total_advisors: int | None = None
    total_business: int | None = None
    business_premium: float | None = None
    total_policy_leads: int | None = None
    total_policy_issued: int | None = None
    policy_premium: float | None = None


class PipelineStageMetric(BaseModel):
    stage: str
    count: int


class AnalyticsFilterOption(BaseModel):
    id: str
    label: str


class InsuranceAnalyticsOverview(BaseModel):
    capabilities: AnalyticsCapabilities
    summary: InsuranceAnalyticsSummary
    pipeline: list[PipelineStageMetric] = Field(default_factory=list)
    stages: list[str] = Field(default_factory=list)
    advisors: list[AnalyticsFilterOption] = Field(default_factory=list)
    products: list[AnalyticsFilterOption] = Field(default_factory=list)


class AdvisorAnalyticsRow(BaseModel):
    advisor_id: str
    advisor_code: str
    advisor_name: str
    businesses: int
    total_premium: float
    products: int


class AdvisorProductMetric(BaseModel):
    product_name: str
    businesses: int


class AdvisorBusinessAnalyticsItem(BaseModel):
    id: str
    customer_name: str | None
    customer_mobile: str | None
    policy_number: str | None
    product_name: str
    product_category: str
    premium: float
    ppt: int
    pt: int
    policy_issue_date: datetime
    comment: str | None
    created_at: datetime


class AdvisorWorkAnalytics(BaseModel):
    advisor: AdvisorAnalyticsRow
    products: list[AdvisorProductMetric] = Field(default_factory=list)
    businesses: list[AdvisorBusinessAnalyticsItem] = Field(default_factory=list)


class ProductAnalyticsRow(BaseModel):
    product_id: str
    product_name: str
    leads: int
    issued: int
    premium: float


class PolicyAnalyticsItem(BaseModel):
    id: str
    case_code: str
    customer_id: str
    customer_name: str | None
    advisor_id: str | None
    advisor_name: str | None
    product_id: str
    product_name: str
    stage: str
    premium: float | None
    created_at: datetime


class ProductWorkAnalytics(BaseModel):
    product: ProductAnalyticsRow
    leads: list[PolicyAnalyticsItem] = Field(default_factory=list)

from typing import Literal
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

class CampaignCreate(StrictModel):
    query: str = Field(min_length=8, max_length=4000)
    mode: Literal['demo','live'] = 'demo'

class CampaignPlan(StrictModel):
    title: str
    target_count: int = Field(ge=1, le=50)
    geography: str
    ideal_customer: str
    qualification_criteria: list[str] = Field(min_length=1)
    search_queries: list[str] = Field(min_length=1, max_length=10)

class Candidate(StrictModel):
    company_name: str = Field(min_length=1)
    url: str

class Discovery(StrictModel):
    companies: list[Candidate]

class Evidence(StrictModel):
    source_id: UUID
    quote: str = Field(min_length=12, max_length=1500)
    claim: str = Field(min_length=1)

class Enrichment(StrictModel):
    industry: str
    summary: str
    product: str
    geography: str
    signals: list[str]

class Qualification(StrictModel):
    score: int = Field(ge=0, le=100)
    verdict: Literal['strong_fit','possible_fit','not_a_fit','insufficient_evidence']
    reasons: list[str] = Field(min_length=1)
    evidence: list[Evidence] = Field(min_length=1)

class Draft(StrictModel):
    subject: str = Field(min_length=1, max_length=240)
    body: str = Field(min_length=1, max_length=6000)

class ResearchResult(StrictModel):
    lead_id: UUID
    enrichment: Enrichment
    qualification: Qualification
    draft: Draft | None

class ResearchBatch(StrictModel):
    leads: list[ResearchResult] = Field(min_length=1, max_length=5)

class DraftEdit(Draft):
    expected_revision: int = Field(ge=1)

class Review(StrictModel):
    revision: int = Field(ge=1)
    decision: Literal['approved','rejected']

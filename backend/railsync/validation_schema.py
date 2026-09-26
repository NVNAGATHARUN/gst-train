"""Input declarations and limits; no scheduling predicates are shared with the validator."""
from typing import Literal
from pydantic import AwareDatetime, Field, model_validator
from .requests import StrictModel

class CoverageDeclaration(StrictModel):
    source: Literal['OCCUPANCY','COA','FREIGHT','NETWORK','REQUESTS','RESOURCES','COMMITMENTS']
    track_id: str | None = None
    start_at: AwareDatetime
    end_at: AwareDatetime
    complete: bool
    evidence_reference: str = Field(min_length=1,max_length=200)

    @model_validator(mode='after')
    def ordered(self):
        if self.start_at>=self.end_at:raise ValueError('positive coverage interval required')
        if (self.source in ['OCCUPANCY','COA','FREIGHT']) != (self.track_id is not None):
            raise ValueError('traffic coverage needs a track; other coverage is corridor-wide')
        return self

class ValidationContext(StrictModel):
    scope: Literal['SIMULATED','IMPORTED']
    facts_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    received_at: AwareDatetime
    valid_until: AwareDatetime
    coverage: list[CoverageDeclaration] = Field(min_length=1,max_length=1000)
    coa_semantics: Literal['ACCESS_ENVELOPE','TRAFFIC_FREE','UNKNOWN']
    clearance_before_minutes: int = Field(ge=0,le=60)
    clearance_after_minutes: int = Field(ge=0,le=60)
    protect_freight_envelope: bool
    commitments_known_empty: bool
    rule_reference: str = Field(min_length=1,max_length=200)

    @model_validator(mode='after')
    def valid(self):
        if self.received_at>=self.valid_until:raise ValueError('positive validity interval required')
        return self

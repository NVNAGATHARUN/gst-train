"""Versioned, explicit prototype rules. These are not railway operating standards."""
from typing import Literal
from pydantic import AwareDatetime, Field, model_validator
from .requests import StrictModel

Department = Literal['ENGINEERING', 'TRD', 'SNT']
Mode = Literal['ALLOW_PARALLEL', 'ALLOW_SEQUENTIAL', 'FORBID', 'UNKNOWN']

class Period(StrictModel):
    start_at: AwareDatetime
    end_at: AwareDatetime

    @model_validator(mode='after')
    def ordered(self):
        if self.end_at <= self.start_at:
            raise ValueError('positive interval required')
        return self

class Qualification(Period):
    skill: str = Field(min_length=1, max_length=60)

class Duty(Period):
    track_id: str

class ResourceProfile(StrictModel):
    source_mode: Literal['SIMULATED', 'IMPORTED']
    rule_reference: str = Field(min_length=1, max_length=200)
    departments: list[Department] = Field(min_length=1)
    qualifications: list[Qualification] = Field(min_length=1, max_length=100)
    calendar: list[Period] = Field(min_length=1, max_length=1000)
    home_track: str
    history: Period
    duties: list[Duty] = Field(max_length=1000)
    min_rest_minutes: int = Field(ge=0, le=1440)
    max_duty_minutes_per_24h: int = Field(gt=0, le=1440)
    pool_id: str | None = None

    @model_validator(mode='after')
    def valid_calendar(self):
        for periods in [self.calendar, self.duties]:
            ordered = sorted(periods, key=lambda p: p.start_at)
            if any(a.end_at > b.start_at for a, b in zip(ordered, ordered[1:])):
                raise ValueError('calendar/duties must not overlap')
        if any(d.start_at < self.history.start_at or d.end_at > self.history.end_at for d in self.duties):
            raise ValueError('duty outside declared history')
        return self

class WorkSignature(StrictModel):
    department: Department
    issue_type: str
    power_state: Literal['ANY', 'ON', 'OFF']
    signalling_state: Literal['ANY', 'CONNECTED', 'DISCONNECTED']

class PairRule(StrictModel):
    id: str
    left: WorkSignature
    right: WorkSignature
    footprint_relation: Literal['SAME', 'OVERLAP', 'DISJOINT']
    mode: Mode
    shared_setup: bool
    shared_restoration: bool

class GroupRule(StrictModel):
    id: str
    members: list[WorkSignature] = Field(min_length=3, max_length=4)
    mode: Mode

class TravelRule(StrictModel):
    resource_type: str
    from_track: str
    to_track: str
    minutes: int = Field(ge=0, le=1440)

class CapacityPeriod(Period):
    capacity: int = Field(ge=0, le=1000)

class ResourcePool(StrictModel):
    id: str
    resource_type: str
    calendar: list[CapacityPeriod] = Field(min_length=1, max_length=1000)

    @model_validator(mode='after')
    def disjoint(self):
        ordered = sorted(self.calendar, key=lambda p: p.start_at)
        if any(a.end_at > b.start_at for a, b in zip(ordered, ordered[1:])):
            raise ValueError('overlapping capacity periods')
        return self

class CoordinationPolicy(StrictModel):
    source_mode: Literal['SIMULATED', 'IMPORTED']
    rule_reference: str = Field(min_length=1, max_length=200)
    pairs: list[PairRule] = Field(max_length=1000)
    groups: list[GroupRule] = Field(max_length=1000)
    travel: list[TravelRule] = Field(max_length=1000)
    pools: list[ResourcePool] = Field(max_length=100)

    @model_validator(mode='after')
    def unique_rules(self):
        from .requests import digest
        pair_keys = [(tuple(sorted([digest(r.left.model_dump()), digest(r.right.model_dump())])), r.footprint_relation) for r in self.pairs]
        group_keys = [tuple(sorted(digest(m.model_dump()) for m in r.members)) for r in self.groups]
        travel_keys = [(r.resource_type, r.from_track, r.to_track) for r in self.travel]
        for keys in [pair_keys, group_keys, travel_keys, [p.id for p in self.pools], [r.id for r in self.pairs + self.groups]]:
            if len(keys) != len(set(keys)):
                raise ValueError('duplicate or ambiguous rule')
        return self

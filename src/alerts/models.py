from pydantic import BaseModel


class AlertRule(BaseModel):
    id: str
    name: str
    severity: list[str]


class AlertRecord(BaseModel):
    id: str
    state: str
    severity: str
    title: str
    user_id: str | None = None
    rule_id: str | None = None
    subject_id: str | None = None
    kind: str | None = None
    snoozed_until: str | None = None
    resolved_at: str | None = None

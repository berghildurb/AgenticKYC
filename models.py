from dataclasses import dataclass, field
from typing import Optional
import uuid
from datetime import datetime, timezone


def _new_id() -> str:
    return str(uuid.uuid4())[:8].upper()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class Submission:
    full_name: str
    date_of_birth: str
    nationality: str
    country_of_birth: str
    country_of_residence: str
    occupation: str
    employer: str
    source_of_funds: str
    expected_transaction_volume: str
    pep_status: bool
    beneficial_ownership: str
    id: str = field(default_factory=_new_id)
    timestamp: str = field(default_factory=_now)
    # pending → analyzed → approved / rejected
    status: str = "pending"
    risk_brief: Optional[dict] = None
    decision: Optional[dict] = None

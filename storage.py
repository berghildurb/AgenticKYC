import json
from dataclasses import asdict, fields as dc_fields
from pathlib import Path

from models import Submission


def _deserialise(data: dict) -> Submission:
    """Migrate old schema and drop unknown keys before constructing a Submission."""
    # Migrate single-dispute format (dispute: {...} or dispute: null)
    if "dispute" in data:
        old = data.pop("dispute")
        if old and "disputes" not in data:
            data["disputes"] = [old]
            data["dispute_count"] = 1
    # Drop keys that no longer exist in the dataclass
    known = {f.name for f in dc_fields(Submission)}
    data = {k: v for k, v in data.items() if k in known}
    return Submission(**data)

SUBMISSIONS_DIR = Path("data/submissions")


def _ensure_dir() -> None:
    SUBMISSIONS_DIR.mkdir(parents=True, exist_ok=True)


def save_submission(submission: Submission) -> None:
    _ensure_dir()
    path = SUBMISSIONS_DIR / f"{submission.id}.json"
    with open(path, "w") as f:
        json.dump(asdict(submission), f, indent=2)


def load_submission(submission_id: str) -> Submission:
    path = SUBMISSIONS_DIR / f"{submission_id}.json"
    with open(path) as f:
        data = json.load(f)
    return _deserialise(data)


def load_all_submissions() -> list[Submission]:
    _ensure_dir()
    submissions = []
    for path in sorted(SUBMISSIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        with open(path) as f:
            data = json.load(f)
        submissions.append(_deserialise(data))
    return submissions


def update_submission(submission: Submission) -> None:
    save_submission(submission)

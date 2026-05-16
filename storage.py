import json
from dataclasses import asdict
from pathlib import Path

from models import Submission

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
    return Submission(**data)


def load_all_submissions() -> list[Submission]:
    _ensure_dir()
    submissions = []
    for path in sorted(SUBMISSIONS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
        with open(path) as f:
            data = json.load(f)
        submissions.append(Submission(**data))
    return submissions


def update_submission(submission: Submission) -> None:
    save_submission(submission)

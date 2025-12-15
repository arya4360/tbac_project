import json
from pathlib import Path
from datetime import datetime
import uuid
import contextlib

# Simple in-memory approvals store: approval_id -> {'status':'pending'|'approved', 'requested_by': user_id, 'reason': str}
APPROVALS = {}

# File to persist approvals across runs (simple JSON dict)
_APPROVALS_FILE = Path(__file__).resolve().parent.parent / 'approvals.json'
_APPROVALS_AUDIT = Path(__file__).resolve().parent.parent / 'approvals_audit.log'


def _load_approvals():
    # load into the existing APPROVALS dict so external references remain valid
    try:
        if _APPROVALS_FILE.exists():
            with open(str(_APPROVALS_FILE), 'r', encoding='utf-8') as f:
                data = json.load(f)
                APPROVALS.clear()
                APPROVALS.update({str(k): v for k, v in data.items()})
    except Exception:
        APPROVALS.clear()


def _save_approvals():
    # write atomically: write to temp then rename
    tmp = _APPROVALS_FILE.with_suffix('.tmp')
    try:
        # ensure parent directory exists
        tmp.parent.mkdir(parents=True, exist_ok=True)
        with open(str(tmp), 'w', encoding='utf-8') as f:
            json.dump(APPROVALS, f, default=str, indent=2)
            f.flush()
            try:
                import os
                os.fsync(f.fileno())
            except Exception:
                pass
        # replace target
        tmp.replace(_APPROVALS_FILE)
    except Exception:
        # best-effort; do not raise from persistence failure in demo
        with contextlib.suppress(Exception):
            if tmp.exists():
                tmp.unlink()


def _write_approvals_audit(entry: dict):
    try:
        with open(str(_APPROVALS_AUDIT), 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def create_approval(requested_by: str, toolcall: dict) -> str:
    """Create a persistent approval request and return the approval id."""
    aid = str(uuid.uuid4())
    APPROVALS[aid] = {
        'status': 'pending',
        'requested_by': requested_by,
        'toolcall': toolcall,
        'requested_at': datetime.utcnow().isoformat()
    }
    _save_approvals()
    # write audit entry
    _write_approvals_audit({'ts': datetime.utcnow().isoformat(), 'approval_id': aid, 'event': 'requested', 'requested_by': requested_by, 'toolcall': toolcall})
    return aid


def approve_approval(approval_id: str, approver_id: str) -> bool:
    """Mark an approval as approved and persist; return True if success."""
    appr = APPROVALS.get(approval_id)
    if not appr:
        return False
    appr['status'] = 'approved'
    appr['approved_by'] = approver_id
    appr['approved_at'] = datetime.utcnow().isoformat()
    _save_approvals()
    # write audit entry
    _write_approvals_audit({'ts': datetime.utcnow().isoformat(), 'approval_id': approval_id, 'event': 'approved', 'approved_by': approver_id, 'requested_by': appr.get('requested_by'), 'toolcall': appr.get('toolcall')})
    return True


# load approvals at import time
_load_approvals()

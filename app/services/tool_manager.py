from app.core.security import check_tool_authorization
from app.core.models import ToolCall
from typing import Dict
import json
from datetime import datetime
from pathlib import Path
import importlib

# Mock tool implementations (kept local to avoid circular imports)
class MockGitHub:
    def read_repo(self, user_id, repo='main'):
        tc = ToolCall(tool_name='GitHub', action='read_repo', parameters={'repo': repo})
        if not check_tool_authorization(user_id, tc):
            return {'status': 'denied', 'message': 'Not authorized to read repo'}
        return {'status': 'ok', 'data': f'Logs from {repo}... (mock)'}

    def write_code(self, user_id, repo='main', content=''):
        tc = ToolCall(tool_name='GitHub', action='write_code', parameters={'repo': repo, 'content': content})
        if not check_tool_authorization(user_id, tc):
            return {'status': 'denied', 'message': 'Not authorized to write code'}
        return {'status': 'ok', 'data': f'Committed to {repo} (mock)'}

class MockFileSystem:
    def read_file(self, user_id, path='/'):
        tc = ToolCall(tool_name='FileSystem', action='read_file', parameters={'path': path})
        if not check_tool_authorization(user_id, tc):
            return {'status': 'denied', 'message': 'Not authorized to read file'}
        return {'status': 'ok', 'data': f'Contents of {path} (mock)'}

    def write_file(self, user_id, path='/', content=''):
        tc = ToolCall(tool_name='FileSystem', action='write_file', parameters={'path': path, 'content': content})
        if not check_tool_authorization(user_id, tc):
            return {'status': 'denied', 'message': 'Not authorized to write file'}
        return {'status': 'ok', 'data': f'Wrote to {path} (mock)'}

class MockDeployment:
    def deploy(self, user_id, env='staging'):
        tc = ToolCall(tool_name='Deployment', action='deploy', parameters={'env': env})
        if not check_tool_authorization(user_id, tc):
            return {'status': 'denied', 'message': 'Not authorized to deploy'}
        return {'status': 'ok', 'data': f'Deployed to {env} (mock)'}

class MockDB:
    def migrate(self, user_id, script=''):
        tc = ToolCall(tool_name='DB', action='migrate', parameters={'script': script})
        if not check_tool_authorization(user_id, tc):
            return {'status': 'denied', 'message': 'Not authorized to migrate DB'}
        return {'status': 'ok', 'data': 'DB migration applied (mock)'}

class MockSecrets:
    def get_secret(self, user_id, name=''):
        tc = ToolCall(tool_name='Secrets', action='read_secret', parameters={'name': name})
        if not check_tool_authorization(user_id, tc):
            return {'status': 'denied', 'message': 'Not authorized to access secrets'}
        return {'status': 'ok', 'data': f'secret:{name} (mock)'}

class MockCRM:
    def create_lead(self, user_id, lead_data=None):
        tc = ToolCall(tool_name='CRM', action='create_lead', parameters={'lead': lead_data})
        if not check_tool_authorization(user_id, tc):
            return {'status': 'denied', 'message': 'Not authorized to create lead'}
        return {'status': 'ok', 'data': 'Lead created (mock)'}

# Create single instances
_GH = MockGitHub()
_FS = MockFileSystem()
_DEP = MockDeployment()
_DB = MockDB()
_SE = MockSecrets()
_CRM = MockCRM()

_AUDIT_LOG = Path(__file__).resolve().parent.parent / 'audit.log'


def _write_audit(entry: dict):
    """Persist audit entry to Django model when available, otherwise fallback to JSONL file."""
    # Try to use Django model if app is configured, else fallback
    try:
        from app.models import AuditEntry
        # Create a DB-backed audit entry
        try:
            AuditEntry.objects.create(
                user=entry.get('user', ''),
                tool=entry.get('toolcall', {}).get('tool', ''),
                action=entry.get('toolcall', {}).get('action', ''),
                params=entry.get('toolcall', {}).get('params', {}),
                decision=entry.get('decision', ''),
                message=entry.get('message', '')
            )
            return
        except Exception:
            # fall through to file-based audit if DB write fails
            pass
    except Exception:
        pass

    # Fallback: append to audit.log
    try:
        with open(str(_AUDIT_LOG), 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry) + "\n")
    except Exception:
        pass


def _requires_approval(tool, action):
    return (tool == 'Deployment' and 'deploy' in (action or '').lower()) or (tool == 'DB' and 'migrate' in (action or '').lower())


def execute_tool_call(user_id: str, tc: ToolCall) -> Dict:
    """Authoritative execution entrypoint for tool calls with approvals.

    - Enforces P.E.P.2 via check_tool_authorization.
    - Dispatches to the appropriate mock implementation.
    - Returns a normalized dict: {'status','data','message'}
    - Writes an append-only audit log for decisions.
    """
    # import data module at runtime to pick up reloads/monkeypatching in tests
    approvals_mod = None
    ApprovalModel = None
    try:
        # prefer Django-backed approvals when available
        from app.models import Approval as ApprovalModel
        approvals_mod = None
    except Exception:
        # fall back to the legacy approvals module
        approvals_mod = importlib.import_module('app.core.approvals')

    # Final authorization
    allowed = check_tool_authorization(user_id, tc)
    if not allowed:
        res = {'status': 'denied', 'message': 'Not authorized to perform tool call'}
        _write_audit({
            'ts': datetime.utcnow().isoformat(),
            'user': user_id,
            'toolcall': {'tool': tc.tool_name, 'action': tc.action, 'params': tc.parameters},
            'decision': res['status'],
            'message': res['message']
        })
        return res

    # Approval flow for high-risk actions
    if _requires_approval(tc.tool_name, tc.action):
        approval_id = (tc.parameters or {}).get('approval_id')
        if not approval_id:
            # create a persistent request id and return pending
            if ApprovalModel is not None:
                # create DB-backed approval
                import uuid as _uuid
                aid = str(_uuid.uuid4())
                try:
                    ApprovalModel.objects.create(
                        approval_id=aid,
                        requested_by=user_id,
                        tool=tc.tool_name,
                        action=tc.action,
                        params=tc.parameters or {},
                        status='pending'
                    )
                    new_id = aid
                except Exception:
                    # fallback to legacy approvals.create_approval
                    if approvals_mod:
                        new_id = approvals_mod.create_approval(user_id, {'tool': tc.tool_name, 'action': tc.action, 'params': tc.parameters})
                    else:
                        new_id = aid
            else:
                new_id = approvals_mod.create_approval(user_id, {'tool': tc.tool_name, 'action': tc.action, 'params': tc.parameters})

            res = {'status': 'pending_approval', 'message': 'Action requires approval', 'approval_id': new_id}
            _write_audit({'ts': datetime.utcnow().isoformat(), 'user': user_id, 'toolcall': {'tool': tc.tool_name, 'action': tc.action, 'params': tc.parameters}, 'decision': res['status'], 'message': res.get('message')})
            return res
        # if approval id present, check status
        appr = None
        if ApprovalModel is not None:
            try:
                appr_obj = ApprovalModel.objects.filter(approval_id=approval_id).first()
                if appr_obj:
                    appr = {'status': appr_obj.status}
                else:
                    appr = None
            except Exception:
                appr = None
        else:
            appr = approvals_mod.APPROVALS.get(approval_id)

        if not appr or appr.get('status') != 'approved':
            res = {'status': 'pending_approval', 'message': 'Approval not granted yet', 'approval_id': approval_id}
            _write_audit({'ts': datetime.utcnow().isoformat(), 'user': user_id, 'toolcall': {'tool': tc.tool_name, 'action': tc.action, 'params': tc.parameters}, 'decision': res['status'], 'message': res.get('message')})
            return res

    # proceed to dispatch as before
    tool = tc.tool_name
    action = tc.action or ''
    params = tc.parameters or {}

    # Dispatch as before and audit the result
    if tool == 'GitHub':
        if 'read' in action:
            result = _GH.read_repo(user_id, repo=params.get('repo','main'))
        else:
            result = _GH.write_code(user_id, repo=params.get('repo','main'), content=params.get('content',''))
    elif tool == 'FileSystem':
        if 'read' in action:
            result = _FS.read_file(user_id, path=params.get('path','/'))
        else:
            result = _FS.write_file(user_id, path=params.get('path','/'), content=params.get('content',''))
    elif tool == 'Deployment':
        result = _DEP.deploy(user_id, env=params.get('env','staging'))
    elif tool == 'DB':
        result = _DB.migrate(user_id, script=params.get('script',''))
    elif tool == 'Secrets':
        result = _SE.get_secret(user_id, name=params.get('name',''))
    elif tool == 'CRM':
        result = _CRM.create_lead(user_id, lead_data=params.get('lead'))
    else:
        result = {'status': 'error', 'message': 'Unknown tool'}

    _write_audit({
        'ts': datetime.utcnow().isoformat(),
        'user': user_id,
        'toolcall': {'tool': tc.tool_name, 'action': tc.action, 'params': tc.parameters},
        'decision': result.get('status'),
        'message': result.get('message')
    })
    return result

# add helper endpoints for approvals in demo_cli or API if needed

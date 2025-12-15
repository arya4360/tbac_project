from app.core.models import ToolCall
from app.services.tool_manager import execute_tool_call
import importlib
import app.core.approvals as approvals_mod
import app.core.data as data_mod


def test_deploy_create_approve_execute(tmp_path, monkeypatch):
    # Use temp approvals file for isolation
    # configure approvals file via approvals module
    monkeypatch.setattr('app.core.approvals._APPROVALS_FILE', tmp_path / 'approvals.json')
    importlib.reload(approvals_mod)
    # ensure approvals view from data module is in sync
    importlib.reload(data_mod)
    approvals_mod.APPROVALS.clear()

    # Step 1: create a deploy toolcall -> should return pending_approval with id
    tc = ToolCall(tool_name='Deployment', action='deploy', parameters={'env':'staging'})
    res = execute_tool_call('eng01', tc)
    assert res.get('status') == 'pending_approval'
    aid = res.get('approval_id')
    assert aid in approvals_mod.APPROVALS

    # Step 2: approve via helper
    ok = approvals_mod.approve_approval(aid, 'mgr01')
    assert ok is True
    assert approvals_mod.APPROVALS[aid]['status'] == 'approved'

    # Step 3: retry with approval id
    tc.parameters = dict(tc.parameters or {})
    tc.parameters['approval_id'] = aid
    res2 = execute_tool_call('eng01', tc)
    assert res2.get('status') == 'ok'

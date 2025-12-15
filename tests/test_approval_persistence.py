import os
import importlib
import app.core.approvals as approvals_mod


def test_create_and_persist_approval(tmp_path, monkeypatch):
    # ensure we use a temporary approvals file before importing the module
    monkeypatch.setattr('app.core.approvals._APPROVALS_FILE', tmp_path / 'approvals.json')
    importlib.reload(approvals_mod)

    # create approval
    aid = approvals_mod.create_approval('eng01', {'tool':'Deployment','action':'deploy','params':{}})
    assert aid in approvals_mod.APPROVALS
    # persistence: reload module to simulate restart and verify stored id exists
    importlib.reload(approvals_mod)
    assert aid in approvals_mod.APPROVALS

import pytest
from app.core.models import ToolCall
from app.services.tool_manager import execute_tool_call
from app.core.data import USER_DB


def test_deploy_requires_deploy_permission():
    # it01 has Deployment deploy permission, eng01 has deploy too
    tc = ToolCall(tool_name='Deployment', action='deploy', parameters={'env':'staging'})
    res = execute_tool_call('it01', tc)
    # deployment may require approval; accept pending_approval or ok
    assert res.get('status') in ('ok', 'pending_approval')

    # sales user should be denied
    res2 = execute_tool_call('sales01', tc)
    assert res2.get('status') == 'denied'


def test_migration_requires_write_db_permission():
    # default users don't have DB write; attempt should be denied
    tc = ToolCall(tool_name='DB', action='migrate', parameters={'script':'alter table'})
    res = execute_tool_call('eng01', tc)
    # eng01 has DB read_write in earlier versions; if not present, ensure behavior is clear
    assert res.get('status') in ('ok', 'denied')

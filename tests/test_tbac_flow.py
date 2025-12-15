import pytest
from app.core.data import USER_DB
from app.core.models import ToolCall
from app.core import security
from app.services.tool_manager import execute_tool_call


def test_pep1_denies_feature_write_for_it_user():
    # Priya (it01) shouldn't be allowed to perform Feature_Development (requires GitHub write)
    assert not security.check_task_authorization('it01', 'Feature_Development')


def test_pep2_denies_filesystem_access_to_sales_on_engineering_folder():
    # sales01 should not access /Engineering/...
    tc = ToolCall(tool_name='FileSystem', action='read_file', parameters={'path': '/Engineering/secret.txt'})
    res = execute_tool_call('sales01', tc)
    assert res.get('status') == 'denied'


def test_pep1_allows_feature_for_engineer_and_pep2_executes():
    # eng01 should be allowed to do Feature_Development and execute GitHub write
    assert security.check_task_authorization('eng01', 'Feature_Development')
    tc = ToolCall(tool_name='GitHub', action='write_code', parameters={'repo':'main','content':'x'})
    res = execute_tool_call('eng01', tc)
    assert res.get('status') == 'ok'

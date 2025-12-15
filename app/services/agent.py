from app.core.models import ToolCall, AgentResponse
from app.services.tool_manager import execute_tool_call
import re


def _extract_env(prompt: str) -> str:
    # naive extraction of env names like 'staging' or 'production'
    if not prompt:
        return 'staging'
    p = prompt.lower()
    if 'production' in p or 'prod' in p:
        return 'production'
    if 'staging' in p:
        return 'staging'
    if 'demo' in p or 'dev' in p:
        return 'demo'
    return 'staging'


def _extract_repo(prompt: str) -> str:
    # naive repo extraction: look for 'main' or explicit repo tokens
    if not prompt:
        return 'main'
    if 'main branch' in prompt.lower():
        return 'main'
    m = re.search(r"repo[:=]\s*([\w-]+)", prompt, flags=re.IGNORECASE)
    if m:
        return m.group(1)
    return 'main'


def execute_task(user_id: str, prompt: str, task_name: str) -> AgentResponse:
    """Refactored agent: build ToolCall(s) and delegate execution to execute_tool_call.

    This makes the tool manager the single authoritative P.E.P.2 enforcement point.
    """
    try:
        # extract parameters
        env = _extract_env(prompt)
        repo = _extract_repo(prompt)

        if task_name == 'Feature_Development':
            tc = ToolCall(tool_name='GitHub', action='write_code', parameters={'repo': repo, 'content': 'README content'})
            res = execute_tool_call(user_id, tc)
            if res.get('status') == 'denied':
                return AgentResponse(status='denied', message=res.get('message'))
            return AgentResponse(status='ok', message='Feature development executed (mock)', result=res)

        if task_name in ('Production_Support', 'Incident_Resolution'):
            tc1 = ToolCall(tool_name='GitHub', action='read_repo', parameters={'repo': repo})
            gh_res = execute_tool_call(user_id, tc1)
            if gh_res.get('status') == 'denied':
                return AgentResponse(status='denied', message=gh_res.get('message'))

            path = '/IT/logs.txt' if task_name == 'Incident_Resolution' else '/Engineering/logs.txt'
            tc2 = ToolCall(tool_name='FileSystem', action='read_file', parameters={'path': path})
            fs_res = execute_tool_call(user_id, tc2)
            if fs_res.get('status') == 'denied':
                return AgentResponse(status='denied', message=fs_res.get('message'))

            return AgentResponse(status='ok', message=f'{task_name} executed (mock)', result={'github': gh_res, 'filesystem': fs_res})

        if task_name == 'Infrastructure_Maintenance':
            tc = ToolCall(tool_name='Deployment', action='deploy', parameters={'env': env})
            res = execute_tool_call(user_id, tc)
            if res.get('status') == 'denied':
                return AgentResponse(status='denied', message=res.get('message'))
            return AgentResponse(status='ok', message='Infrastructure maintenance executed (mock)', result=res)

        if task_name == 'Lead_Generation':
            tc = ToolCall(tool_name='CRM', action='create_lead', parameters={'lead': {'source':'genai'}})
            res = execute_tool_call(user_id, tc)
            if res.get('status') == 'denied':
                return AgentResponse(status='denied', message=res.get('message'))
            return AgentResponse(status='ok', message='Lead created (mock)', result=res)

        if task_name == 'Proposal_Development':
            tc = ToolCall(tool_name='FileSystem', action='read_file', parameters={'path':'/Sales/proposal.docx'})
            res = execute_tool_call(user_id, tc)
            if res.get('status') == 'denied':
                return AgentResponse(status='denied', message=res.get('message'))
            return AgentResponse(status='ok', message='Proposal data retrieved (mock)', result=res)

        return AgentResponse(status='error', message='Unknown task')
    except Exception as e:
        return AgentResponse(status='error', message=f'Agent execution failed: {e}')

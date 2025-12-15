"""Demo CLI that exercises routing, P.E.P.1, and P.E.P.2 and prints audit-style logs."""
from app.core.approvals import APPROVALS, create_approval, approve_approval
from datetime import datetime
from app.core.models import ToolCall
from app.services import router, agent
from app.core import security
from app.services.tool_manager import execute_tool_call
import time

SCENARIOS = [
    # IT scenarios
    ('it01', 'Check the deployment logs for the last service incident.'),
    ('it01', 'Fix the bug in the main function and commit the change.'),
    ('it01', 'Run maintenance scripts on the server'),

    # Engineering scenarios
    ('eng01', 'Push a new README file to the main branch.'),
    ('eng01', 'Create a new API endpoint and commit the implementation'),
    ('eng01', 'Migrate user data to the new schema'),

    # Sales scenarios
    ('sales01', 'Prepare a proposal document for customer'),
    ('sales01', 'Generate a list of leads for the EMEA region'),
    
]

DENIAL_SCENARIOS = [
    # These should be denied at P.E.P.1 (task-level) because user lacks required task permissions
    ('sales01', 'Push a new README file to the main branch.'),   # Sales has no GitHub write
    ('se01', 'Push a new README file to the main branch.'),      # Sales Engineer has GitHub read only
    ('it01', 'Create a new API endpoint and commit the implementation'),  # IT shouldn't write code
    ('se01', 'Prepare a demo environment for the customer'),
    ('se01', 'Check deployment logs for the demo environment'),

    # Security persona
    ('sec01', 'Retrieve database credentials'),

    # Manager
    ('mgr01', 'Approve deployment to production'),
]


def audit(msg: str):
    print(f"[{datetime.utcnow().isoformat()}] {msg}")


def _auto_approve_and_retry(user_id: str, tc: ToolCall):
    # execute the call first time
    res = execute_tool_call(user_id, tc)
    if res.get('status') == 'pending_approval':
        approval_id = res.get('approval_id')
        audit(f'Approval requested id={approval_id} for user={user_id} action={tc.action}')
        # auto-approve for demo purposes (simulate manager approval)
        approve_approval(approval_id, 'mgr01')
        audit(f'Auto-approved approval_id={approval_id} by mgr01')
        # retry the tool call with approval_id
        tc.parameters = dict(tc.parameters or {})
        tc.parameters['approval_id'] = approval_id
        res2 = execute_tool_call(user_id, tc)
        return res2
    return res


def run():
    audit('Starting demo scenarios')
    for user_id, prompt in SCENARIOS:
        audit(f'Prompt received from {user_id}: "{prompt}"')
        r = router.route_prompt(prompt)
        if not r or r.get('task') is None:
            audit(f'Router could not route prompt: {r.get("error") if r else "no response"}')
            continue
        task = r.get('task')
        audit(f'Routed to task: {task}')

        # P.E.P.1 check
        pep1 = security.check_task_authorization(user_id, task)
        audit(f'P.E.P.1 (task-level) authorization for {user_id} -> {task}: {pep1}')
        if not pep1:
            audit('Denied at P.E.P.1. Skipping agent execution.')
            continue

        # Execute task via agent
        resp = agent.execute_task(user_id, prompt, task)
        # If agent returned pending_approval at task level (rare), handle it
        if isinstance(resp.result, dict) and resp.result.get('status') == 'pending_approval':
            approval_id = resp.result.get('approval_id')
            audit(f'Agent returned pending_approval: {resp.result}')
            # Attempt to reconstruct the original ToolCall from stored APPROVALS entry
            stored = APPROVALS.get(approval_id)
            if stored and 'toolcall' in stored:
                tc_info = stored['toolcall']
                tc = ToolCall(tool_name=tc_info.get('tool'), action=tc_info.get('action'), parameters=tc_info.get('params'))
                audit(f'Reconstructed ToolCall for approval_id={approval_id}: {tc.tool_name} {tc.action} {tc.parameters}')
                # auto-approve for demo
                approve_approval(approval_id, 'mgr01')
                audit(f'Auto-approved approval_id={approval_id} by mgr01')
                # retry with approval id
                tc.parameters = dict(tc.parameters or {})
                tc.parameters['approval_id'] = approval_id
                retry_res = execute_tool_call(user_id, tc)
                audit(f'Retry result after approval: {retry_res}')
            else:
                audit('Could not reconstruct ToolCall from APPROVALS; skipping auto-approve')
        audit(f'AgentResponse: status={resp.status} message="{resp.message}" result={resp.result}')

    # Denial scenarios that demonstrate P.E.P.1 denials
    audit('Running explicit denial scenarios (expect P.E.P.1 denials)')
    for user_id, prompt in DENIAL_SCENARIOS:
        audit(f'Prompt received from {user_id}: "{prompt}"')
        r = router.route_prompt(prompt)
        if not r or r.get('task') is None:
            audit(f'Router could not route prompt: {r.get("error") if r else "no response"}')
            continue
        task = r.get('task')
        audit(f'Routed to task: {task}')
        pep1 = security.check_task_authorization(user_id, task)
        audit(f'P.E.P.1 authorization: {pep1}')
        if not pep1:
            audit('Correctly denied at P.E.P.1')
        else:
            resp = agent.execute_task(user_id, prompt, task)
            audit(f'AgentResponse (unexpected allowed): {resp}')

    # Demonstrate P.E.P.2 denials and edge cases via direct tool calls
    audit('Demonstrating P.E.P.2 denials and edge cases (direct tool calls)')

    # sales trying to write code -> should be denied
    tc = ToolCall(tool_name='GitHub', action='write_code', parameters={'repo':'main','content':'x'})
    res = execute_tool_call('sales01', tc)
    audit(f'sales01 GitHub.write_code -> {res}')

    # eng trying to read Sales folder -> denied by FILESYSTEM_POLICY
    tc2 = ToolCall(tool_name='FileSystem', action='read_file', parameters={'path': '/Sales/proposal.docx'})
    res2 = execute_tool_call('eng01', tc2)
    audit(f'eng01 FileSystem.read_file /Sales -> {res2}')

    # traversal attempt by IT user
    tc3 = ToolCall(tool_name='FileSystem', action='read_file', parameters={'path': '/Engineering/../IT/secret.txt'})
    res3 = execute_tool_call('it01', tc3)
    audit(f'it01 traversal attempt -> {res3}')

    # Demonstrate approval flow: trigger a deploy which will request approval, auto-approve and retry
    audit('Demonstrating approval flow for deployment')
    tc4 = ToolCall(tool_name='Deployment', action='deploy', parameters={'env': 'staging'})
    res4 = _auto_approve_and_retry('eng01', tc4)
    audit(f'Deployment flow result: {res4}')

    # Demonstrate a P.E.P.2 filesystem denial: sales user trying to read Engineering folder
    audit('Demonstrating P.E.P.2 denial: sales user reading Engineering folder')
    tc5 = ToolCall(tool_name='FileSystem', action='read_file', parameters={'path': '/Engineering/secret.txt'})
    res5 = execute_tool_call('sales01', tc5)
    audit(f'execute_tool_call result: {res5}')


if __name__ == '__main__':
    run()

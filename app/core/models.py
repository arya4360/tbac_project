from dataclasses import dataclass, field
from typing import Dict, Any, Optional

@dataclass
class User:
    id: str
    name: str
    team: str
    permissions: Dict[str, str]

@dataclass
class Task:
    name: str
    required_tools: Dict[str, str]

@dataclass
class ToolCall:
    tool_name: str
    action: str
    parameters: Optional[Dict[str, Any]] = field(default_factory=dict)

@dataclass
class AgentResponse:
    status: str
    message: str
    result: Any = None

    def dict(self):
        return {'status': self.status, 'message': self.message, 'result': self.result}

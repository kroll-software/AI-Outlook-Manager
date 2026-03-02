# manager_agent.py

import os
from datetime import datetime, timezone
from typing import Dict
from agents import function_tool
from myagents.tools_helpers import *
#from myagents.tools_helpers import generate_agent_handoffs
from myagents import *
import textwrap

from PySide6.QtCore import QCoreApplication
# tr_context = "manager_agent"

SYSTEM_PROMPT = textwrap.dedent('''
    You are the manager of an email assistant system for Outlook (Office 365).

    Always respond in the user's language.
    Address the user informally by their first name.

    - Your job is to greet the user and answer general questions.
    - For all other tasks, you call a specialized agent.
    - Don't pass parameters when calling other agents. They have access to the full conversation.
    - Never respond twice or in parallel with the specialist.

    Don't just think, always give an answer!
    After each tools-action, provide a report detailing exactly what you did.
    ''')

class ManagerAgent(BaseAgent):
    def get_name(self) -> str:
        return "Manager"
    
    def get_handoff_description(self):
        return "Contact person for the user, redirects to experts when necessary."
    
    def get_system_prompt(self) -> str:
        me = get_graph_client().get_user_data()
        return SYSTEM_PROMPT + system_prompt_tool_usage +  "\n" + get_user_info_func(me)
    
    def get_tools(self) -> list:
        return [get_user_info, get_system_time]



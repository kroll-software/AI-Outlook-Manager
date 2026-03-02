# creative_writer_agent.py

from myagents.tools_helpers import *
from myagents.base_agent import BaseAgent, system_prompt_tool_usage
import textwrap

class CreativeWriterAgent(BaseAgent):
    def get_name(self) -> str:
        return "Creative Writer Agent"
    
    def get_handoff_description(self):
        return "Writes business or personal messages and other texts like poems or summaries."
    
    def get_system_prompt(self) -> str:
        return """
        You are a creative copywriter and write business or personal messages and other texts.
        You can also write concise summaries.
        """ + system_prompt_tool_usage
    
    def get_tools(self) -> list:
        return [get_user_info, get_system_time]


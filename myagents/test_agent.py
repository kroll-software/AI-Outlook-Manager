# test_agent.py

import random
from myagents.tools_helpers import *
from myagents.base_agent import BaseAgent, system_prompt_tool_usage

class MemoryTestAgent(BaseAgent):
    def get_name(self) -> str:
        return "Memory Test Agent"
    
    def get_handoff_description(self):
        return "Performs internal memory tests"
    
    def get_system_prompt(self) -> str:
        return """
        You are a test-agent to help debugging the agent framework chat-memory.
        Perform tool-calls in a loop.
        """ + system_prompt_tool_usage
    
    def get_tools(self) -> list:
        return [perform_test]


_book_paragraphs = []

def read_doc():
    global _book_paragraphs
    file_path = "docs/The Odyssey by Homer.txt"
    try:
        with open(file_path, 'r', encoding='utf-8') as file:
            text = file.read()
        _book_paragraphs.clear()
        _book_paragraphs.extend(text.split("\n\n"))
    except Exception as e:
        print(f"Error: {str(e)}")

def get_random_text(length: int = 100) -> str:
    global _book_paragraphs
    if not _book_paragraphs:
        read_doc()        
    text = ""
    while len (text) < length:
        text += "\n" + random.choice(_book_paragraphs)
    return text

@function_tool
def perform_test(i: int) -> str:
    """
    Returns test-data for the loop-variable 'i'.
    Ensure to call it with the correct i for subsequent calls.
    """

    print(f"perform_test {i}")
    
    random_text = get_random_text()
    return f"test {i}: {random_text}"
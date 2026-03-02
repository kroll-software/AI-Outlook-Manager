from abc import ABC, abstractmethod
from agents import Agent, ModelSettings
import core.model_provider
import textwrap

system_prompt_tool_usage = """

## Tool Call Format

Use this strict format whenever calling a tool:

{
  "tool_calls": [
    {
      "name": "tool_name",
      "arguments": { "key": "value" }
    }
  ]
}

### Rules:
- Make sure you only use existing tools.
- Double check that the tool is present and that you are using the correct parameters.
- Analyze exactly which agent you need to forward to perform a specific action.
- Forgive tool call errors and retry later, as they are usually only temporary.

---

"""

class BaseAgent(ABC):
    def __init__(self):
        self._agent = None
        self._last_model = None
        self.prepare_agent()

    def get_agent(self) -> Agent:
        return self._agent    

    def prepare_agent(self):
        current_model = self.get_model()
        self._agent = Agent(
            name=self.get_name(),
            handoff_description=textwrap.dedent(self.get_handoff_description()),
            instructions=textwrap.dedent(self.get_system_prompt()),
            tools=self.get_tools(),
            model=current_model,
            model_settings = self.get_model_settings(),
        )
        self._last_model = current_model    

    def update_settings(self):
        self._agent.instructions = self.get_system_prompt()
        self._agent.model_settings = self.get_model_settings()        

        self._last_model = self.get_model()
        self._agent.model = self._last_model


    def get_model(self) -> Agent:
        return core.model_provider.get_model()

    @abstractmethod
    def get_name(self) -> str:
        pass

    @abstractmethod
    def get_handoff_description(self):
        pass

    @abstractmethod
    def get_system_prompt(self) -> str:
        pass

    @abstractmethod
    def get_tools(self) -> list:
        pass

    def get_model_settings(self) -> ModelSettings:
        return ModelSettings(
            #temperature=0.6,   # not supported by GPT-5
            #top_p=0.95,            
            #top_k=0,
            #max_tokens=1024,  # optional
        )

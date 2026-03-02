import os
import json
import time
import uuid
import logging
import tiktoken
from copy import deepcopy
from typing import List, Dict, Optional, Callable, Tuple
from core.utils import remove_thinking_blocks, makedir
from core.model_provider import get_model
from agents import Agent, Runner, RunConfig, ModelSettings, custom_span
from agents.memory import Session
from core.local_trace_processor import add_tokens_from_run_result
#import asyncio
from typing import List, Dict, Optional, Literal

# Logger für dieses Modul mit dem Modulnamen
logger = logging.getLogger(__name__)

# Level und Format definieren, Ausgabe ins Terminal
'''
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)  # root-handler wird automatisch erstellt :contentReference[oaicite:1]{index=1}
'''

class ChatMemory:
    def __init__(self, ctx_size: int = 4096, file_path: str = ".settings/history.json", discard_user_messages: bool = False, static_tokens = 0):
        self.ctx_size = ctx_size        
        self.static_tokens = static_tokens
        self.summarize_content = False  # Optional summarize content in single posts
        self._set_token_limit()        
        self._token_count = 0
        self.chat_store: List[Dict] = []
        self.chat_store_full: List[Dict] = []
        self._create_summary_agent()
        self.file_path = file_path
        self.discard_user_messages = discard_user_messages
        self._encoding = tiktoken.get_encoding("cl100k_base")
        logger.debug("ChatMemory initialized with ctx_size=%d", self.ctx_size)        
        
        self._file = None
        if file_path:
            self._load() # zuerst
            dirname = os.path.dirname(file_path)
            if dirname:
                makedir(dirname)

    def _set_token_limit(self):
        min_ctx = 2048
        #max_ctx = 32768
        #max_ctx = 128_000
        max_ctx = 100_000_000
        self.token_limit = max(min_ctx, min(self.ctx_size // 2 - self.static_tokens, max_ctx))        

    def add_entry(self, role: str, content):
        message = {"role": role, "content": content}    
        self.put(message)

    async def put(self, message: Dict) -> None:
        message = deepcopy(message)
        if "status" in message and message["status"] == "completed" and "role" in message and "content" in message:
            # assistant response with thinking tags
            content_list = message["content"]
            new_content_list = []
            for part in content_list:
                if "text" in part:
                    original = part["text"]
                    cleaned = remove_thinking_blocks(original)                    
                    cleaned = cleaned.strip()
                    if self.summarize_content and self._count_tokens(cleaned) > self.token_limit // 4:                
                        cleaned = await self._summarize_text(cleaned)
                    if cleaned:
                        part["text"] = cleaned
                        new_content_list.append(part)

            if len(new_content_list) == 0:
                # leerer Content, message verwerfen
                return
            message["content"] = new_content_list

        elif "call_id" in message and "output" in message:
            # result of a function call
            output = message["output"]            
            if self.summarize_content and self._count_tokens(output) > self.token_limit // 10:                
                summary = await self._summarize_text(output)
                message["output"] = summary
        elif "role" in message and "content" in message:
            # is always user message
            if message["role"] == "user" and self.discard_user_messages:
                return
            content = message["content"]
            if not content:
                return
            if self.summarize_content and self._count_tokens(content) > self.token_limit // 4:                
                summary = await self._summarize_text(content)
                message["content"] = summary

        if "id" in message and message["id"] == "__fake_id__":
            message["id"] = str(uuid.uuid4())

        self.chat_store.append(message)
        self.chat_store_full.append(deepcopy(message))
        self._token_count += self._count_messages_tokens([message])        
        self._append_message_to_file(message)
    
    def _create_summary_agent(self):        
        self.summary_agent = Agent(
            name="Summary Agent",
            instructions="You are a summarization agent. You write accurate summaries of conversations. Never call tools!",
            tools=[],
            handoffs=[],
            model=get_model()
        )

    async def _summarize_text(self, text):
        try:
            settings = ModelSettings(tool_choice="none")
            config = RunConfig(model_settings=settings)
            with custom_span(name="Memory Summary", data={"step": "summarize text"}):
                result = await Runner.run(self.summary_agent, text, run_config=config)
            add_tokens_from_run_result(result)
            summary = remove_thinking_blocks(result.final_output)
        except Exception as e:
            print(f"Error in _summarize_text: {str(e)}")
            summary = text        
        return summary

    async def _summarize_messages(self, messages: List[Dict]) -> str:
        history = deepcopy(messages)    
        prompt = {"role": "assistant", "content": "Give a detailed summary of the entire chat-history."}
        history.append(prompt)
        try:
            settings = ModelSettings(tool_choice="none")
            config = RunConfig(model_settings=settings)
            with custom_span(name="Memory Summary", data={"step": "summarize messages"}):
                result = await Runner.run(self.summary_agent, history, run_config=config)
            add_tokens_from_run_result(result)
            return remove_thinking_blocks(result.final_output)    
        except Exception as e:
            print(f"Error in _summarize_messages: {str(e)}")
            return ""
        
    def _append_message_to_file(self, message: Dict):
        # Logge die Nachricht als JSON
        if not self.file_path or not message:
            return        
        try:
            if not self._file:
                self._file = open(self.file_path, 'a', encoding='utf-8')
            json.dump(message, self._file, ensure_ascii=False)
            self._file.write('\n')
            self._file.flush()
            os.fsync(self._file.fileno())
        except Exception as e:
            logger.error("Error writing to Chat-Memory file: %s", e, exc_info=True)

    async def get_all(self) -> List[Dict]:
        await self._shrink_messages(self.chat_store)
        return deepcopy(self.chat_store)

    def count(self):
        return len(self.chat_store)
    
    def count_full(self):
        return len(self.chat_store_full)

    def reset(self) -> None:
        logger.debug("ChatMemory reset")
        self.chat_store.clear()
        self.chat_store_full.clear()
        self._token_count = 0
        
        try:
            if self._file:
                self._file.close()
                self._file = None

            if os.path.exists(self.file_path):
                os.remove(self.file_path)
        except Exception as e:
            logger.error("Error deleting Chat-Memory file: %s", e, exc_info=True)

    def get_token_count(self) -> int:
        return self._token_count

    def _count_messages_tokens(self, messages: List[Dict]) -> int:        
        content = json.dumps(messages, ensure_ascii=False)
        return self._count_tokens(content)
    
    def _count_tokens(self, content: str) -> int:
        if not content:
            return 0
        return len(self._encoding.encode(content))    

    async def _shrink_messages(self, messages: List[Dict]):
        working_copy = deepcopy(messages)
        full = []
        total_tokens = 0

        partial_limit = self.token_limit // 2

        while working_copy:
            last = working_copy[-1]
            tokens = self._count_messages_tokens([last])
            if total_tokens + tokens > partial_limit and last.get("role") == "assistant":
                break
            full.insert(0, last)
            working_copy.pop()
            total_tokens += tokens

        message_tokens = self._count_messages_tokens(working_copy)
        if message_tokens + total_tokens > self.token_limit and len(working_copy) > 1:
            summary = await self._summarize_messages(working_copy)
            logger.debug("ChatMemory: %d messages summarized.", len(working_copy))

            if summary:
                #sys_message = [{"role": "system", "content": summary}]
                sys_message = [{"role": "assistant", "content": summary}]
                sys_tokens = self._count_messages_tokens(sys_message)            

                self.chat_store = sys_message + full
                self._token_count = sys_tokens + total_tokens

                self._rewrite_file()
            else:
                self.chat_store = working_copy + full
                self._token_count = message_tokens + total_tokens    
        else:
            self.chat_store = working_copy + full
            self._token_count = message_tokens + total_tokens    

    def _rewrite_file(self):
        # Datei komplett neu schreiben
        if not self.file_path or not self._file:
            return        
        try:
            self._file.close()
            self._file = None
            with open(self.file_path, 'w', encoding='utf-8') as f:
                for msg in self.chat_store:
                    json.dump(msg, f, ensure_ascii=False)
                    f.write('\n')
                f.flush()
                os.fsync(f.fileno())
        except Exception as e:
            logger.error("Error rewriting ChatMemory file after shrink: %s", e, exc_info=True)

    def update_context_size(self, new_ctx_size: int):
        if new_ctx_size != self.ctx_size:
            self.ctx_size = new_ctx_size
            self._set_token_limit()
            self._create_summary_agent()    
            logger.debug("ChatMemory neue ctx_size=%d", self.ctx_size)    

    def _load(self) -> None:
        if not os.path.exists(self.file_path):
            return
        try:
            logger.debug("Loading ChatMemory from %s", self.file_path)
            messages = []
            with open(self.file_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        msg = json.loads(line)
                        messages.append(msg)
            self.chat_store = messages
            self.chat_store_full = deepcopy(messages)
            self._token_count = self._count_messages_tokens(messages)
        except Exception as e:
            logger.error("Error loading ChatMemory from: %s", e, exc_info=True)  

    def __del__(self):
        try:
            if self._file:
                self._file.close()
                self._file = None
        except Exception:
            pass


class ChatMemorySession(Session):
    """Session-compatible wrapper for ChatMemory."""

    def __init__(self, session_id: str, chat_memory: ChatMemory):
        self.session_id = session_id
        self.chat_memory = chat_memory

    async def get_items(self, limit: Optional[int] = None) -> List[dict]:
        messages = await self.chat_memory.get_all()
        if limit is not None:
            messages = messages[-limit:]
        return messages

    async def add_items(self, items: List[dict]) -> None:
        for message in items:
            await self.chat_memory.put(message)

    async def pop_item(self) -> Optional[dict]:
        if self.chat_memory.chat_store:
            return self.chat_memory.chat_store.pop()
        return None

    async def clear_session(self) -> None:
        self.chat_memory.reset()

    def get_session_id(self) -> str:
        return self.session_id
    
    def get_chat_memory(self) -> ChatMemory:
        return self.chat_memory

# core/chat_history.py

import os
import time
import json
import logging
from typing import List, Dict, Any, Optional
from core.utils import makedir

# Logger für dieses Modul mit dem Modulnamen
logger = logging.getLogger(__name__)

class ChatHistory:
    def __init__(self, logfile_dir: Optional[str] = "logfiles"):
        self.entries: List[Dict[str, Any]] = []
        self.logfile_dir = logfile_dir
        makedir(self.logfile_dir)
        self.logfile_name = self._new_logfile_name()        
        self._file = None        

    def _new_logfile_name(self) -> str:        
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        return os.path.join(self.logfile_dir, f"{timestamp}-chat.json")    

    def get_logfile_name(self):
        return self.logfile_name

    def add_entry(self, role: str, name: str, content: str, **kwargs):
        entry = {"role": role, "name": name, "content": content}
        entry.update(kwargs)
        self.entries.append(entry)

        # Logge als JSON-Zeile        
        self._append_message_to_file(entry)

    def _append_message_to_file(self, message: Dict):        
        if not self.logfile_name or not message:
            return        
        try:
            if not self._file:
                self._file = open(self.logfile_name, 'a', encoding='utf-8')

            json.dump(message, self._file, ensure_ascii=False)  # ToDo: Error
            self._file.write('\n')
            self._file.flush()
            os.fsync(self._file.fileno())
        except Exception as e:
            logger.error("Error writing to chat-history file: %s", e, exc_info=True)

    def get_all(self) -> List[Dict[str, Any]]:
        return self.entries    

    def get_last_user_message(self) -> Optional[str]:
        for entry in reversed(self.entries):
            if entry["role"] == "user":
                return entry["content"]
        return None

    def reset(self):
        self.entries.clear()
        self._close_file()
        self.logfile_name = self._new_logfile_name()    

    def load_from_file(self, filename: str):
        if not os.path.exists(filename):
            return
        try:
            logger.debug("Loading chat-history from %s", filename)            
            with open(filename, 'r', encoding='utf-8') as f:
                for line in f:
                    try:
                        self.entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
            self.logfile_name = filename
        except Exception as e:
            logger.error("Error loading chat-history: %s", e, exc_info=True)  

    def _close_file(self):
        try:
            if self._file:
                self._file.close()
                self._file = None
        except Exception:
            pass

    def __del__(self):
        self._close_file()
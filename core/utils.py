import os
import time
from datetime import date, datetime
import re
import json
from collections.abc import Mapping
from agents.items import MessageOutputItem
from typing import Any
from pathlib import Path
import platform
import subprocess
import ctypes


def get_user_data_dir(app_name="OutlookManager"):
    system = platform.system()

    if system == "Windows":
        # z. B. C:\Users\<User>\AppData\Roaming\OutlookManager
        base = Path(os.getenv("APPDATA", Path.home() / "AppData" / "Roaming")) / "Kroll-Software"
    elif system == "Linux":
        # z. B. ~/.config/OutlookManager
        base = os.getenv("XDG_CONFIG_HOME", Path.home() / ".config")
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        print("Unknown Operating System")
        return ""

    return Path(base) / app_name

def makedir(dir: str | Path):
    if not dir:
        return
    try:
        path = Path(dir)
        if not path.exists():
            print(f"Creating directory '{path}' ...")
            path.mkdir(parents=True, exist_ok=True)
    except Exception as e:
        print(f"Error creating directory: {str(e)}")

def is_removable_drive(path=".") -> bool:
    system = platform.system()
    abs_path = str(Path(path).resolve())

    if system == "Windows":
        # Windows: GetDriveTypeW nutzen
        root = os.path.splitdrive(abs_path)[0] + "\\"
        DRIVE_REMOVABLE = 2
        drive_type = ctypes.windll.kernel32.GetDriveTypeW(root)
        return drive_type == DRIVE_REMOVABLE

    elif system in ("Linux", "Darwin"):  # Darwin = macOS
        try:
            result = subprocess.run(["df", abs_path], capture_output=True, text=True, check=True)
            lines = result.stdout.strip().splitlines()
            if len(lines) < 2:
                return False
            device = lines[1].split()[0]  # z. B. "/dev/sdb1"
        except Exception:
            return False

        # Prüfen, ob Device ein USB-Gerät ist
        by_id = Path("/dev/disk/by-id")
        if by_id.exists():
            for entry in by_id.iterdir():
                if "usb" in entry.name and entry.is_symlink():
                    if os.path.realpath(entry) == device:
                        return True

        # macOS Fallback: USB-Volumes liegen oft unter /Volumes
        if system == "Darwin" and abs_path.startswith("/Volumes/"):
            return True

        return False

    else:
        print(f"[WARN] OS '{system}' not supported.")
        return False


def is_running_from_removable_drive() -> bool:
    """Prüft, ob das aktuelle Arbeitsverzeichnis auf einem Wechseldatenträger liegt."""
    return is_removable_drive(Path.cwd())

def get_settings_dir(app_name="OutlookManager") -> str:
    cwd = Path.cwd()

    if is_running_from_removable_drive():
        # Portable Mode: im Programmverzeichnis speichern
        return str(cwd)

    # Normaler Mode: im User-Config-Verzeichnis
    return str(get_user_data_dir(app_name=app_name))

def remove_thinking_blocks(text: str) -> str:
    if not text:
        return ""
    text = text.strip()
    if "</think>" in text:
        text = text.rsplit("</think>", 1)[-1].strip()
    return "" if text.startswith("<think>") else text

def extract_thinking_blocks(text: str) -> list[str]:
    """Extrahiert alle Inhalte innerhalb von <think>...</think> als Liste."""
    matches = re.findall(r"<think>(.*?)</think>", text, flags=re.DOTALL | re.IGNORECASE)
    return [m.strip() for m in matches]

def get_response(result) -> str:
    return remove_thinking_blocks(result.final_output)
   
def get_response_message(result):
    return {"role": "assistant", "content": get_response(result)}

def get_history_as_list(result):
    history = []
    for item in result.to_input_list():
        history.append({
            "role": item.get("role"),
            "content": item.get("content")
        })
    return history

def shorten_text(text: Any, max_len: int = 80) -> str:
    s = str(text)
    return s if len(s) <= max_len else s[:max_len - 3] + "..."

def shorten_value(value: Any, max_len: int = 80) -> str:
    try:
        if isinstance(value, (str, int, float, bool)) or value is None:
            s = str(value)
        elif isinstance(value, (date, datetime)):
            s = value.isoformat()
        elif isinstance(value, (bytes, bytearray)):
            s = f"<{len(value)} bytes>"
        else:
            # Fallback: JSON (z. B. für dict/list), notfalls default=str
            s = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    except Exception:
        s = str(value)

    return s if len(s) <= max_len else s[:max_len - 3] + "..."

def score2stars(score: float) -> str:    
    return "⭐" * round(score) 

def is_empty_message(msg: str):
    if not msg:
        return True    
    return not msg.strip(" \n")

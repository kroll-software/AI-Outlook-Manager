# setting_manager.py

import os
import json
from cryptography.fernet import Fernet
from core.utils import makedir

# ⚠️ Beispiel: Fester Schlüssel in dieser Datei.
# Besser wäre es, diesen separat zu speichern oder aus einer sicheren Quelle zu laden.
_SECRET_KEY = b"gyop1eNWp81OkUpwAdgbIKNFYEHsQl-P8w-eM8XKE9U="  # Fernet.generate_key()
_cipher = Fernet(_SECRET_KEY)

_settings_path = os.path.join(".settings", "settings.json")
_settings = {}

# _SECRET_KEY generieren mit
# print(Fernet.generate_key().decode())

def get_settings_path():
    global _settings_path
    return _settings_path

def load_settings(settings_path : str = None):
    global _settings_path
    global _settings

    if settings_path:
        _settings_path = settings_path

    if os.path.exists(_settings_path):
        try:
            with open(_settings_path, "r", encoding="utf-8") as f:
                _settings = json.load(f)
        except Exception as e:
            print(f"[WARN] Error loading sessions: {e}")
            _settings = {}
    else:
        _settings = {}
    return _settings

def save_settings(settings: dict = None):
    global _settings
    data = _settings.copy()
    if settings:
        data.update(settings)
    _settings = data  # Merge-Ergebnis speichern
    try:
        makedir(os.path.dirname(_settings_path))
        
        with open(_settings_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[WARN] Error saving sessions: {e}")


def get_settings() -> dict:
    global _settings
    return _settings

def get_setting(key: str, default_value=None, encrypted: bool = False):
    global _settings
    val = _settings.get(key)
    if val is None:
        return default_value

    if encrypted:
        try:
            return _cipher.decrypt(val.encode("utf-8")).decode("utf-8")
        except Exception as e:
            print(f"[WARN] Error encrypting value for {key}: {e}")
            return default_value
    return val

def set_setting(key: str, value, do_save: bool = True, encrypted: bool = False):
    global _settings
    if encrypted and value is not None:
        try:
            val = _cipher.encrypt(str(value).encode("utf-8")).decode("utf-8")
        except Exception as e:
            print(f"[WARN] Error decrypting value for {key}: {e}")
            val = value
    else:
        val = value

    _settings[key] = val
    if do_save:
        save_settings()

def encrypt_value(value):
    try:
        val = _cipher.encrypt(str(value).encode("utf-8")).decode("utf-8")
        return val
    except Exception as e:
        print(f"[WARN] Error encrypting value for: {e}")
        return value
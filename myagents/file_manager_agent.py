# file_manager_agent


import os
import re
from agents import function_tool
from myagents.tools_helpers import *
from myagents.base_agent import BaseAgent, system_prompt_tool_usage
from core.utils import makedir
import datetime
from pathlib import Path
from directory_tree import DisplayTree
from typing import List, Optional
from markitdown import MarkItDown
from core.setting_manager import get_setting

from PySide6.QtCore import QCoreApplication
# tr_context = "file_manager_agent"

class FileManagerAgent(BaseAgent):    
    def get_name(self) -> str:
        return "File Manager Agent"

    def get_handoff_description(self):
        return "Can read and write files and manage Dirs in a workspace."

    def get_system_prompt(self) -> str:
        return """
            You are the File Manager Agent.
            
            Your job is to maintain local files, which includes to
            - read and write text files with any extension
            - read any MS-Office file or PDF
            - list, create and delete directories in your workspace

            Your root is your workspace-directory.
            You can't access files outside your workspace.
            """ + system_prompt_tool_usage

    def get_tools(self) -> list:
        return [
            list_dirs,
            read_text_file,
            read_office_file,
            read_pdf_file,
            write_text_file,
            delete_file,
            make_dir,
            delete_dir,
            get_system_time,
            get_user_info,
        ]


# --- Tool Helpers ---
def fix_path(file_path: str) -> str:
    workspace = get_setting("workspace_dir", "./workspace")
    workspace_path = Path(workspace).resolve()

    # künstliches Prefix "root/" entfernen
    if file_path.startswith("root/"):
        file_path = file_path[len("root/"):]

    file_path = file_path.replace("/", os.sep)

    p = Path(file_path)

    # Nur relative Pfade sind erlaubt
    if p.is_absolute():
        raise ValueError("absolute paths not allowed")

    resolved_path = (workspace_path / p).resolve()

    if not resolved_path.is_relative_to(workspace_path):
        raise ValueError("invalid path")

    return str(resolved_path)


# --- Tool Functions ---

@function_tool
def list_dirs() -> str:    
    ''' List directories and files in the workspace '''     
    parameters = []
    if not confirm_tools_call(QCoreApplication.translate("file_manager_agent", "Dateien und Verzeichnisse im Workspace auflisten"), parameters, False):
        return cancelled_by_user_message()

    workspace = get_setting("workspace_dir", "./workspace")
    s = DisplayTree(workspace, stringRep=True, showHidden=True, sortBy=2)

    # Nur den Ordnernamen des Workspace als Ankerpunkt nehmen
    workspace_dir = os.path.basename(os.path.normpath(workspace))
    s = "root" + s[len(workspace_dir):]

    return s


@function_tool
def read_text_file(file_path: str) -> str:
    ''' Read a text-file (*.txt, *.eml, *.md, *.py, ...) from the workspace '''    
    parameters: List[Dict[str, str]] = []    
    parameters.append({"name": "file_path", "value": file_path})
    if not confirm_tools_call(QCoreApplication.translate("file_manager_agent", "Textdatei im Workspace lesen"), parameters, False):
        return cancelled_by_user_message()

    try:
        file_path = fix_path(file_path)
        with open(file_path, 'r', encoding='utf-8') as file:
            return file.read()
    except Exception as e:
        return e.msg if hasattr(e, "msg") else str(e)
    
@function_tool
def read_office_file(file_path: str) -> str:
    ''' 
    Read a MS-Office file (*.docx, *.xls, *.xlsx, *.pptx, *.html and others) from the workspace.
    This tool returns the contents in Markdown.
    '''
    parameters: List[Dict[str, str]] = []    
    parameters.append({"name": "file_path", "value": file_path})
    if not confirm_tools_call(QCoreApplication.translate("file_manager_agent", "Office-Datei im Workspace lesen"), parameters, False):
        return cancelled_by_user_message()
    
    try:
        file_path = fix_path(file_path)
        md = MarkItDown()
        result = md.convert(file_path)
        text = result.text_content
        return text        
    except Exception as e:
        return e.msg if hasattr(e, "msg") else str(e)
    
@function_tool
def read_pdf_file(file_path: str) -> str:
    ''' 
    Read a PDF files (*.pdf) from the workspace.
    This tool returns the contents in Markdown.
    '''
    parameters: List[Dict[str, str]] = []    
    parameters.append({"name": "file_path", "value": file_path})
    if not confirm_tools_call(QCoreApplication.translate("file_manager_agent", "PDF-Datei im Workspace lesen"), parameters, False):
        return cancelled_by_user_message()
    try:
        file_path = fix_path(file_path)
        md = MarkItDown()
        result = md.convert(file_path)
        text = result.text_content
        return text        
    except Exception as e:
        return e.msg if hasattr(e, "msg") else str(e)

@function_tool
def write_text_file(file_path: str, content: str) -> str:
    ''' Write a text-file (*.txt, *.eml, *.md, *.py, ...) to the workspace '''
    parameters: List[Dict[str, str]] = []    
    parameters.append({"name": "file_path", "value": file_path})
    parameters.append({"name": "content", "value": content})
    if not confirm_tools_call(QCoreApplication.translate("file_manager_agent", "Textdatei im Workspace schreiben"), parameters, True):
        return cancelled_by_user_message()
    try:             
        file_path = fix_path(file_path)
        with open(file_path, 'w', encoding='utf-8') as file:
            file.write(content)
        return "OK"
    except Exception as e:
        return e.msg if hasattr(e, "msg") else str(e)  

@function_tool
def delete_file(file_path: str) -> str:
    ''' Delete a file from the workspace '''
    parameters: List[Dict[str, str]] = []    
    parameters.append({"name": "file_path", "value": file_path})    
    if not confirm_tools_call(QCoreApplication.translate("file_manager_agent", "Datei im Workspace löschen"), parameters, True):
        return cancelled_by_user_message()
    try:
        file_path = fix_path(file_path)
        os.remove(file_path)
        return f"File {file_path} deleted successfully."
    except FileNotFoundError:
        return f"Error: File {file_path} not found."
    except PermissionError:
        return f"Error: Permission denied to delete file {file_path}."
    except Exception as e:
        return e.msg if hasattr(e, "msg") else str(e)

@function_tool
def make_dir(path: str) -> str:
    ''' Make a new directory in the workspace '''
    parameters: List[Dict[str, str]] = []    
    parameters.append({"name": "path", "value": path})    
    if not confirm_tools_call(QCoreApplication.translate("file_manager_agent", "Verzeichnis im Workspace erstellen"), parameters, True):
        return cancelled_by_user_message()
    try:                
        path = fix_path(path)
        os.mkdir(path)
        return "OK"
    except Exception as e:
        return e.msg if hasattr(e, "msg") else str(e)

@function_tool    
def delete_dir(path: str) -> str:
    ''' Delete a directory in the workspace '''
    parameters: List[Dict[str, str]] = []    
    parameters.append({"name": "path", "value": path})    
    if not confirm_tools_call(QCoreApplication.translate("file_manager_agent", "Verzeichnis im Workspace löschen"), parameters, True):
        return cancelled_by_user_message()
    try:                
        path = fix_path(path)
        os.rmdir(path)
        return "OK"
    except Exception as e:
        return e.msg if hasattr(e, "msg") else str(e)
# outlook_tasks_agent.py

import os
import re
from typing import Optional, Literal
from agents import function_tool
from myagents.tools_helpers import *
from myagents.base_agent import BaseAgent, system_prompt_tool_usage
from core.graph_auth_client import get_graph_client

from PySide6.QtCore import QCoreApplication
# tr_context = "outlook_tasks_agent"

class OutlookTasksAgent(BaseAgent):
    def get_name(self) -> str:
        return "Outlook Tasks Agent"
    
    def get_handoff_description(self):
        return "Performs many actions with Outlook Tasks in Outlook 365."
    
    def get_system_prompt(self) -> str:
        return """
            Use your tools to manage Tasks in Outlook 365, as requested by user.
            """ + system_prompt_tool_usage
    
    def get_tools(self) -> list:
        return [
            create_task,
            update_task,
            delete_task,
            search_tasks,

            get_user_info,
            get_system_time
        ]


# ----------------------------------------------------
# Tool: Create task
# ----------------------------------------------------
@function_tool
def create_task(
        title: str,
        body: Optional[str] = None,
        due_date: Optional[str] = None,
        importance: Optional[Literal["low", "normal", "high"]] = None,
        status: Optional[Literal["notStarted", "inProgress", "completed", "waitingOnOthers", "deferred"]] = None
    ) -> str:
    """
    Create a new Outlook task.
    - title: short title (required)
    - body: optional description
    - due_date: optional due date in ISO 8601 format (e.g. '2025-09-01T12:00:00Z')
    - importance: optional ('low', 'normal', 'high')
    - status: optional task status ('notStarted','inProgress','completed','waitingOnOthers','deferred')
    Returns the created task info as JSON string.
    """
    gc = get_graph_client()
    if not gc.is_logged_in():
        return not_connected_message()

    params_for_ui = [{"name": "subject", "value": title}]
    if body: params_for_ui.append({"name": "body", "value": body})
    if due_date: params_for_ui.append({"name": "due_date", "value": due_date})
    if importance: params_for_ui.append({"name": "importance", "value": importance})
    if status: params_for_ui.append({"name": "status", "value": status})

    if not confirm_tools_call(QCoreApplication.translate("outlook_tasks_agent", "Aufgabe erstellen"), params_for_ui, True):
        return cancelled_by_user_message()

    result = gc.create_task(
        title=title,
        body=body,
        due_date=due_date,
        importance=importance,
        status=status
    )
    if not result.success:
        return result.combined_error()
    return f"Created task '{title}' with id {result.data.get('id')}"    


# ----------------------------------------------------
# Tool: Update task
# ----------------------------------------------------
@function_tool
def update_task(
        task_id: str,
        title: Optional[str] = None,
        body: Optional[str] = None,
        due_date: Optional[str] = None,
        importance: Optional[Literal["low", "normal", "high"]] = None,
        status: Optional[Literal["notStarted", "inProgress", "completed", "waitingOnOthers", "deferred"]] = None
    ) -> str:
    """
    Update an existing Outlook task.
    - task_id: ID of the task to update
    - title, body, due_date, importance, status: optional updates
    - importance: optional ('low', 'normal', 'high')
    - status: optional task status ('notStarted','inProgress','completed','waitingOnOthers','deferred')
    Returns a status string.
    """
    gc = get_graph_client()
    if not gc.is_logged_in():
        return not_connected_message()

    params_for_ui = [{"name": "task_id", "value": task_id}]
    if title: params_for_ui.append({"name": "subject", "value": title})
    if body: params_for_ui.append({"name": "body", "value": body})
    if due_date: params_for_ui.append({"name": "due_date", "value": due_date})
    if importance: params_for_ui.append({"name": "importance", "value": importance})
    if status: params_for_ui.append({"name": "status", "value": status})

    if not confirm_tools_call(QCoreApplication.translate("outlook_tasks_agent", "Aufgabe aktualisieren"), params_for_ui, True):
        return cancelled_by_user_message()

    result = gc.update_task(
        task_id=task_id,
        title=title,
        body=body,
        due_date=due_date,
        importance=importance,
        status=status
    )
    if not result.success:
        return result.combined_error()
    return "Task was successfully updated."    

# ----------------------------------------------------
# Tool: Delete task
# ----------------------------------------------------
@function_tool
def delete_task(task_id: str) -> str:
    """
    Delete a task by ID.
    Returns "deleted" if successful, or "error".
    """
    gc = get_graph_client()
    if not gc.is_logged_in():
        return not_connected_message()

    params_for_ui = [{"name": "task_id", "value": task_id}]
    if not confirm_tools_call(QCoreApplication.translate("outlook_tasks_agent", "Aufgabe löschen"), params_for_ui, True):
        return cancelled_by_user_message()

    result = gc.delete_task(task_id)
    if not result.success:
        return result.combined_error()
    return "Task was successfully deleted."

# ----------------------------------------------------
# Tool: Search tasks
# ----------------------------------------------------
@function_tool
def search_tasks(search_text: Optional[str] = None) -> str:
    """
    Search tasks by optional text (subject, body).
    - search_text: filter string
    Returns JSON with count and indexed results.
    """
    gc = get_graph_client()
    if not gc.is_logged_in():
        return not_connected_message()

    params_for_ui = []
    if search_text: params_for_ui.append({"name": "search_text", "value": search_text})

    if not confirm_tools_call(QCoreApplication.translate("outlook_tasks_agent", "Aufgabe suchen"), params_for_ui, False):
        return cancelled_by_user_message()

    result = gc.search_tasks(query=search_text or None)
    if not result.success:
        return result.combined_error()

    data = result.data
    results: List[Dict] = []    
    for idx, t in enumerate(data, start=1):
        results.append({
            "index": idx,
            "id": t.get("id"),
            "title": t.get("title"),
            "status": t.get("status"),
            "importance": t.get("importance"),
            "dueDateTime": t.get("dueDateTime")            
        })

    return json.dumps({
        "count": len(results),
        "results": results
    }, ensure_ascii=False, indent=2)

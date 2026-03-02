# tools_helpers.py

from datetime import datetime, timezone
import re
import json
import inspect
from agents import function_tool
from agents import handoff, Agent
from typing import List, Dict, Optional, Callable, Any
from core.graph_auth_client import get_graph_client
from urllib.parse import quote

from PySide6.QtCore import QCoreApplication
from core.graph_auth_client import ApiResult

# tr_context = "tools_helpers"

# Typ für Callback definieren: tool_name, parameterliste, requires_confirmation → bool
ToolConfirmationHandler = Callable[[str, List[Dict[str, str]], bool], bool]

_confirmation_handler: Optional[ToolConfirmationHandler] = None

def register_tool_confirmation_handler(handler: ToolConfirmationHandler):
    global _confirmation_handler
    _confirmation_handler = handler

def confirm_tools_call(tool_name: str, parameters: List[Dict[str, str]], requires_confirmation: bool = True) -> bool:
    if _confirmation_handler:
        return _confirmation_handler(tool_name, parameters, requires_confirmation)
    return True

def not_connected_message() -> str:
    return "The user must first log in to use this tool."

def cancelled_by_user_message() -> str:
    return "Cancelled by user."

def get_or_create_folder(client, display_name):
    folders = client.get("/me/mailFolders").json().get("value", [])
    for folder in folders:
        if folder["displayName"].lower() == display_name.lower():
            return folder["id"]
    new_folder = client.post("/me/mailFolders", json={"displayName": display_name})
    return new_folder.json()["id"]


def generate_tool_description(tool) -> str:
    """Erzeugt Beschreibung aus FunctionTool-Objekt (Agent SDK)."""
    try:
        func = tool.on_invoke_tool  # nicht: _on_invoke_tool!
    except AttributeError:
        raise TypeError(f"{tool} does not contain a callable function (on_invoke_tool is missing)")

    import inspect
    doc = inspect.getdoc(func) or ""
    sig = inspect.signature(func)
    params = list(sig.parameters)
    summary = doc.strip().splitlines()[0] if doc else f"Tool: {tool.name}"
    param_text = ", ".join(params)
    return f"{summary} Requires: {param_text}."

def generate_agent_handoffs(agent: Agent) -> list:
    """
    Erzeugt automatisch Handoffs für alle Tools eines Agenten mit passender Beschreibung.
    Gibt eine Liste von handoff(...) Objekten zurück.
    """
    handoffs = []
    for tool in agent.tools:
        description = generate_tool_description(tool)
        handoffs.append(
            handoff(agent, tool_description_override=description)
        )
    return handoffs


def get_user_info_func(me: Dict) -> str:
    user_str = "User Info:\n"

    if not me:
        return user_str + "--- not logged in ---\n\n"

    displayName = me.get("displayName", "[unknown]")
    user_str += f"Display name: {displayName}\n"

    givenName = me.get("givenName", "[unknown]")
    user_str += f"First name: {givenName}\n"

    surname = me.get("surname", "[unknown]")
    user_str += f"Last name: {surname}\n"

    preferredLanguage = me.get("preferredLanguage", "[german]")
    user_str += f"User language: {preferredLanguage}\n"
    
    email = me.get("userPrincipalName", "[unknown]")
    user_str += f"User email sender address: {email}\n"
    user_str += "\n"
    
    return user_str


# Tool: User-info
@function_tool
def get_user_info() -> str:
    '''
    retreive the user's name, email-address, language, ...    
    '''
    if not confirm_tools_call(QCoreApplication.translate("tools_helpers", "User-Info abfragen"), None, False):
        return cancelled_by_user_message()
    user_info = get_graph_client().get_user_data()
    return get_user_info_func(user_info)

# Tool: Systemzeit
@function_tool
def get_system_time() -> str:
    """
    Returns the current local system date and time.    
    """
    if not confirm_tools_call(QCoreApplication.translate("tools_helpers", "Systemzeit abfragen"), None, False):
        return cancelled_by_user_message()
    # Lokale Zeit mit korrekter Zeitzone (inkl. Sommerzeit)
    local_dt = datetime.now().astimezone()
    utc_dt = datetime.utcnow().replace(tzinfo=timezone.utc)

    # Formatierte Ausgabe – weltweit verständlich
    local_str = local_dt.strftime("%A, %d %B %Y, %H:%M:%S %Z")
    return f"Local date and time: {local_str}"

def format_emails(messages):
    """
    Format emails as JSON, replacing folder IDs with names.
    Adds recipient, sent_date, body_preview, index and summary.
    - messages: list of email dicts from Graph API
    - folder_lookup: optional dict {folder_id: folder_name} for custom folders
    """
    if not messages:
        return json.dumps({"emails": [], "summary": {"count": 0}}, ensure_ascii=False, indent=2)

    results = []
    show_body = len(messages) <= 10
    for idx, msg in enumerate(messages, start=1):
        subject = msg.get("subject", "(no subject)")
        sender = msg.get("from", {}).get("emailAddress", {}).get("address", "unknown")
        recipients = [
            r.get("emailAddress", {}).get("address", "")
            for r in msg.get("toRecipients", []) or []
        ]
        recipient = ", ".join([r for r in recipients if r]) or "unknown"

        message_id = msg.get("id", "unknown")
        folder_id = msg.get("parentFolderId", "unknown")
        received = msg.get("receivedDateTime", "unknown")
        sent = msg.get("sentDateTime", received)
        preview = msg.get("bodyPreview", "")
        importance = msg.get("importance", "normal")
        isDraft = msg.get("isDraft")
        isRead = msg.get("isRead")

        if show_body:
            results.append({
                "index": idx,
                "id": message_id,
                "subject": subject,
                "sender": sender,
                "recipient": recipient,
                "folder_id": folder_id,
                "sent_date": sent,
                "received_date": received,                
                "importance": importance,
                "isDraft": isDraft,
                "isRead": isRead,
                "body_preview": preview
            })
        else:
            results.append({
                "index": idx,
                "id": message_id,
                "subject": subject,
                "sender": sender,
                "recipient": recipient,
                "folder_id": folder_id,
                "sent_date": sent,
                "received_date": received,                
                "importance": importance,
                "isDraft": isDraft,
                "isRead": isRead                
            })

    return json.dumps({
        "emails": results,
        "summary": {"count": len(results)}
    }, ensure_ascii=False, indent=2)

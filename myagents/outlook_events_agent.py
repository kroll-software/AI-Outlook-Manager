# events_calendar_agent.py

import os
import re
from typing import Optional
from agents import function_tool
from myagents.tools_helpers import *
from myagents.base_agent import BaseAgent, system_prompt_tool_usage
from core.graph_auth_client import get_graph_client

from PySide6.QtCore import QCoreApplication
# tr_context = "outlook_events_agent"

class OutlookEventsAgent(BaseAgent):
    def get_name(self) -> str:
        return "Outlook Events and Calendars Agent"
    
    def get_handoff_description(self):
        return "Performs many actions with events and calendars in Outlook 365 using the MS-Graph API."
    
    def get_system_prompt(self) -> str:
        return """
            Use your tools to manage events and calendars in Outlook 365, as requested by user.
            """ + system_prompt_tool_usage
    
    def get_tools(self) -> list:
        return [
            create_event,
            delete_event_by_id,
            update_event_by_id,
            search_events,

            get_user_info,
            get_system_time
        ]


# ----------------------------------------------------
# Tool: Create calendar event
# ----------------------------------------------------
@function_tool
def create_event(subject: str, 
        start_date: str, 
        end_date: str,
        attendees: Optional[str] = None,
        body: Optional[str] = None) -> str:
    """
    Create a new calendar event in Outlook.
    All parameters must be strings.
    - subject: title of the event
    - start_date: ISO datetime string (e.g. "2025-08-25T10:00:00Z")
    - end_date: ISO datetime string
    - attendees: comma separated email addresses
    - body: description text
    Returns the created event info as JSON string.
    """
    gc = get_graph_client()
    if not gc.is_logged_in():
        return not_connected_message()
    
    params_for_ui = []
    if subject: params_for_ui.append({"name": "subject", "value": subject})
    if start_date: params_for_ui.append({"name": "start_date", "value": start_date})
    if end_date: params_for_ui.append({"name": "end_date", "value": end_date})
    if body: params_for_ui.append({"name": "body", "value": body})    

    if not confirm_tools_call("Termin erstellen", params_for_ui, True):
        return cancelled_by_user_message()

    att_list = [a.strip() for a in attendees.split(",") if a.strip()]
    
    result = gc.create_event(
        subject=subject,
        start=datetime.fromisoformat(start_date.replace("Z", "+00:00")),
        end=datetime.fromisoformat(end_date.replace("Z", "+00:00")),
        attendees=att_list,
        body=body
    )
    if not result.success:
        return result.combined_error()
    return f"Created event '{subject}' with id {result.data.get('id')}"

# ----------------------------------------------------
# Tool: Delete calendar event
# ----------------------------------------------------
@function_tool
def delete_event_by_id(event_id: str) -> str:
    """
    Delete a calendar event by ID.
    Returns "deleted" if successful, or "error".
    """
    gc = get_graph_client()
    if not gc.is_logged_in():
        return not_connected_message()

    params_for_ui = []
    if event_id: params_for_ui.append({"name": "event_id", "value": event_id})

    if not confirm_tools_call(QCoreApplication.translate("outlook_events_agent", "Termin löschen"), params_for_ui, True):
        return cancelled_by_user_message()

    
    result = gc.delete_event(event_id)
    if not result.success:
        return result.combined_error()
    return "Event was successfully deleted."

# ----------------------------------------------------
# Tool: Search events
# ----------------------------------------------------
@function_tool
def search_events(start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        search_text: Optional[str] = None,
        attendee: Optional[str] = None) -> str:
    """
    Search calendar events in a time range with optional filters.
    All parameters are strings.
    - start: ISO datetime string (e.g. "2025-08-25T00:00:00Z")
    - end: ISO datetime string
    - search_text: optional text filter
    - attendee: optional attendee email
    Returns JSON with count and indexed results.
    """
    gc = get_graph_client()
    if not gc.is_logged_in():
        return not_connected_message()

    params_for_ui = []
    if start_date: params_for_ui.append({"name": "start_date", "value": start_date})
    if end_date: params_for_ui.append({"name": "end_date", "value": end_date})
    if search_text: params_for_ui.append({"name": "search_text", "value": search_text})
    if attendee: params_for_ui.append({"name": "attendee", "value": attendee})

    if not confirm_tools_call(QCoreApplication.translate("outlook_events_agent", "Termine suchen"), params_for_ui, False):
        return cancelled_by_user_message()

    start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
    end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
    
    result = gc.search_events(start=start_dt, end=end_dt,
                            search_text=search_text or None,
                            attendee=attendee or None)
    if not result.success:
        return result.combined_error()
    
    events = result.data
    results: List[Dict] = []
    for idx, ev in enumerate(events, start=1):
        results.append({
            "index": idx,
            "id": ev.get("id"),
            "subject": ev.get("subject"),
            "start": ev.get("start", {}).get("dateTime"),
            "end": ev.get("end", {}).get("dateTime"),
            "organizer": ev.get("organizer", {}).get("emailAddress", {}).get("address"),
            "location": ev.get("location", {}).get("displayName"),
            "attendees": [
                att.get("emailAddress", {}).get("address")
                for att in ev.get("attendees", [])
            ],
            "isAllDay": ev.get("isAllDay"),
            "isCancelled": ev.get("isCancelled"),
            "createdDateTime": ev.get("createdDateTime"),
            "lastModifiedDateTime": ev.get("lastModifiedDateTime"),
        })

    return json.dumps({
        "count": len(results),
        "results": results
    }, ensure_ascii=False, indent=2)


@function_tool
def update_event_by_id(event_id: str,
        subject: Optional[str] = None,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        attendees: Optional[str] = None,
        body: Optional[str] = None) -> str:
    """
    Update an existing calendar event in Outlook.
    All parameters are strings.
    - event_id: ID of the event to update
    - subject: new title
    - start_date: new start ISO datetime string
    - end_date: new end ISO datetime string
    - attendees: comma-separated email addresses
    - body: new description text
    Returns a status string.
    """
    gc = get_graph_client()
    if not gc.is_logged_in():
        return not_connected_message()

    params_for_ui = [{"name": "event_id", "value": event_id}]
    if subject: params_for_ui.append({"name": "subject", "value": subject})
    if start_date: params_for_ui.append({"name": "start_date", "value": start_date})
    if end_date: params_for_ui.append({"name": "end_date", "value": end_date})
    if body: params_for_ui.append({"name": "body", "value": body})

    if not confirm_tools_call(QCoreApplication.translate("outlook_events_agent", "Termin aktualisieren"), params_for_ui, True):
        return cancelled_by_user_message()

    start_dt = datetime.fromisoformat(start_date.replace("Z", "+00:00")) if start_date else None
    end_dt = datetime.fromisoformat(end_date.replace("Z", "+00:00")) if end_date else None
    att_list = [a.strip() for a in attendees.split(",") if a.strip()] if attendees else None
    
    result = gc.update_event(
        event_id=event_id,
        subject=subject,
        start=start_dt,
        end=end_dt,
        attendees=att_list,
        body=body
    )
    if not result.success:
        return result.combined_error()
    return "Event was successfully updated."    
    

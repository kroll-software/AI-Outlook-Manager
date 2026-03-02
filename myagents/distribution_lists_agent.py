# distribution_lists_agent.py

import os
import re
from typing import Optional
from agents import function_tool
from myagents.tools_helpers import *
from myagents.base_agent import BaseAgent, system_prompt_tool_usage
from core.utils import makedir
from core.contact_db import ContactDB, get_contact_db
from core.graph_auth_client import get_graph_client

from PySide6.QtCore import QCoreApplication
# tr_context = "distribution_list_agent"

class DistributionListsAgent(BaseAgent):
    def get_name(self) -> str:
        return "Distribution Lists Agent"
    
    def get_handoff_description(self):
        return """
        - Maintains Distribution-Lists in a local database.
        - Can send an email to a list.
        - Can add filtered Outlook emails to a list.
        - Can add filtered Outlook contacts to a list.
        """
    
    def get_system_prompt(self) -> str:
        return """
            Use your tools to manage Distribution-Lists.
            """ + system_prompt_tool_usage
    
    def get_tools(self) -> list:
        return [
            create_distribution_list,
            delete_distribution_list,
            list_distribution_lists,
            add_email_to_distribution_list,
            add_outlook_emails_to_distribution_list,
            add_outlook_contacts_to_distribution_list,
            remove_email_from_distribution_list,
            get_emails_from_distribution_list,
            copy_emails_between_distribution_lists,
            move_emails_between_distribution_lists,
            send_email_to_distribution_list,
            
            get_user_info,
            get_system_time
        ]


##### Distribution List Tools #####

@function_tool
def create_distribution_list(list_name: str) -> str:
    """Create a new local Distribution List."""
    # ---- UI-Confirm (falls gewünscht) ----
    params_for_ui = []
    if list_name: params_for_ui.append({"name": "list_name", "value": list_name})    
    if not confirm_tools_call(QCoreApplication.translate("distribution_list_agent", "Verteilerliste erstellen"), params_for_ui, True):        
        return cancelled_by_user_message()
        
    try:
        get_contact_db().create_list(list_name)
        return f"List '{list_name}' created."
    except Exception as e:
        return f"Error creating list: {str(e)}"

@function_tool
def delete_distribution_list(list_name: str) -> str:
    """Delete a local Distribution List."""   
    params_for_ui = []
    if list_name: params_for_ui.append({"name": "list_name", "value": list_name})    
    if not confirm_tools_call("Verteilerliste löschen", params_for_ui, True):
        return cancelled_by_user_message()
        
    try:
        get_contact_db().delete_list(list_name)
        return f"List '{list_name}' deleted."
    except Exception as e:
        return f"Error deleting list: {str(e)}"

@function_tool
def list_distribution_lists() -> str:
    """List all local Distribution Lists."""
    params_for_ui = []    
    if not confirm_tools_call(QCoreApplication.translate("distribution_list_agent", "Verteilerlisten auflisten"), params_for_ui, False):
        return cancelled_by_user_message()
    try:
        ret = get_contact_db().list_lists()        
        return json.dumps(ret, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Error listing list: {str(e)}"

@function_tool
def add_email_to_distribution_list(list_name: str, email: str, displayname: Optional[str] = None) -> str:
    """Add an email to a local Distribution List."""    

    params_for_ui = []
    if email: params_for_ui.append({"name": "email", "value": email})    
    if list_name: params_for_ui.append({"name": "list_name", "value": list_name})    
    if displayname: params_for_ui.append({"name": "displayname", "value": displayname})    
    if not confirm_tools_call(QCoreApplication.translate("distribution_list_agent", "Email zur Verteilerliste hinzufügen"), params_for_ui, False):
        return cancelled_by_user_message()
    
    try:
        get_contact_db().add_email_to_list(email, list_name, displayname)
        return f"Added {email} to list '{list_name}'."
    except Exception as e:
        return f"Error adding email to list: {str(e)}"

@function_tool
def remove_email_from_distribution_list(email: str, list_name: str) -> str:
    """Remove an email from a local Distribution List."""    

    params_for_ui = []
    if email: params_for_ui.append({"name": "email", "value": email})    
    if list_name: params_for_ui.append({"name": "list_name", "value": list_name})        
    if not confirm_tools_call(QCoreApplication.translate("distribution_list_agent", "Email von Verteilerliste löschen"), params_for_ui, False):
        return cancelled_by_user_message()
        
    try:
        get_contact_db().remove_email_from_list(email, list_name)
        return f"Removed {email} from list '{list_name}'."
    except Exception as e:
        return f"Error removing email from list: {str(e)}"

@function_tool
def get_emails_from_distribution_list(list_name: str, regex_filter: str = None) -> str:
    """
    Get all emails from a local Distribution List, optionally filtered by regex.
    Example: regex_filter=".*\\.ch$" returns only .ch addresses.
    """    
    
    params_for_ui = []    
    if list_name: params_for_ui.append({"name": "list_name", "value": list_name})    
    if regex_filter: params_for_ui.append({"name": "regex_filter", "value": regex_filter})    
    if not confirm_tools_call(QCoreApplication.translate("distribution_list_agent", "Verteilerliste abfragen"), params_for_ui, False):
        return cancelled_by_user_message()

    try:
        emails = get_contact_db().get_emails(list_name)
        if regex_filter:
            pattern = re.compile(regex_filter)
            emails = [e for e in emails if pattern.search(e)]        
        return json.dumps(emails, ensure_ascii=False, indent=2)
    except Exception as e:
        return f"Error getting emails from list: {str(e)}"


@function_tool
def move_emails_between_distribution_lists(source_list_name: str, target_list_name: str, regex_filter: str = None) -> str:
    """
    Move all emails from one list to another, optionally filtered by regex.
    Example: regex_filter=".*\\.ch$" moves only addresses ending with .ch
    """    

    params_for_ui = []    
    if source_list_name: params_for_ui.append({"name": "source_list_name", "value": source_list_name})    
    if target_list_name: params_for_ui.append({"name": "target_list_name", "value": target_list_name})    
    if regex_filter: params_for_ui.append({"name": "regex_filter", "value": regex_filter})    
    if not confirm_tools_call(QCoreApplication.translate("distribution_list_agent", "Emails zwischen Verteilerlisten verschieben"), params_for_ui, False):
        return cancelled_by_user_message()
    
    try:
        db_instance = get_contact_db()
        emails = db_instance.get_emails(source_list_name)
        if regex_filter:
            pattern = re.compile(regex_filter)
            emails = [e for e in emails if pattern.search(e)]
        
        db_instance.create_list(target_list_name)
        for email in emails:
            db_instance.add_email_to_list(email, target_list_name)
            db_instance.remove_email_from_list(email, source_list_name)
        
        return f"Moved {len(emails)} emails from '{source_list_name}' to '{target_list_name}'."
    except Exception as e:
        return f"Error moving emails between lists: {str(e)}"
    
@function_tool
def copy_emails_between_distribution_lists(source_list_name: str, target_list_name: str, regex_filter: str = None) -> str:
    """
    Copy all emails from one list to another, optionally filtered by regex.
    Example: regex_filter=".*\\.ch$" copies only addresses ending with .ch
    """    

    params_for_ui = []    
    if source_list_name: params_for_ui.append({"name": "source_list_name", "value": source_list_name})    
    if target_list_name: params_for_ui.append({"name": "target_list_name", "value": target_list_name})    
    if regex_filter: params_for_ui.append({"name": "regex_filter", "value": regex_filter})    
    if not confirm_tools_call(QCoreApplication.translate("distribution_list_agent", "Emails zwischen Verteilerlisten kopieren"), params_for_ui, False):
        return cancelled_by_user_message()
        
    try:
        db_instance = get_contact_db()
        emails = db_instance.get_emails(source_list_name)
        if regex_filter:
            pattern = re.compile(regex_filter)
            emails = [e for e in emails if pattern.search(e)]
        
        db_instance.create_list(target_list_name)
        for email in emails:
            db_instance.add_email_to_list(email, target_list_name)            
        
        return f"Copied {len(emails)} emails from '{source_list_name}' to '{target_list_name}'."
    except Exception as e:
        return f"Error copying emails to list: {str(e)}"
    

@function_tool
def add_outlook_emails_to_distribution_list(
    list_name: str,
    outlook_folder_id: Optional[str] = None,    
    exact_sender_address: Optional[str] = None,
    sender_address_regex_filter: Optional[str] = None,
    exact_recipient_address: Optional[str] = None,
    recipient_address_regex_filter: Optional[str] = None,
    subject_substring: Optional[str] = None,
    body_substring: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    has_attachments: Optional[bool] = None,
    is_read: Optional[bool] = None,
) -> str:
    """
    Add all matching emails from Outlook to a Distribution List.
    Any filters are optional.
    """
    gc = get_graph_client()
    if not gc.is_logged_in():
        return not_connected_message()

    
    result = gc.query_emails(
        folder_id=outlook_folder_id,
        exact_sender_address=exact_sender_address,
        sender_address_regex_filter=sender_address_regex_filter,
        exact_recipient_address=exact_recipient_address,
        recipient_address_regex_filter=recipient_address_regex_filter,
        subject_substring=subject_substring,
        body_substring=body_substring,
        start_date=start_date,
        end_date=end_date,
        has_attachments=has_attachments,
        is_read=is_read,
        top=None
    )

    if not result.success:
        return f"Status {result.status}: {result.error}"

    messages = result.data
    if not messages:
        return "No matching emails found."    

    # ---- UI-Confirm (falls gewünscht) ----
    params_for_ui = []
    if outlook_folder_id: params_for_ui.append({"name": "outlook_folder_id", "value": gc.resolve_folder_name(outlook_folder_id)})
    if exact_sender_address: params_for_ui.append({"name": "exact_sender_address", "value": exact_sender_address})
    if sender_address_regex_filter: params_for_ui.append({"name": "sender_address_regex_filter", "value": sender_address_regex_filter})
    if exact_recipient_address: params_for_ui.append({"name": "exact_recipient_address", "value": exact_recipient_address})
    if recipient_address_regex_filter: params_for_ui.append({"name": "recipient_address_regex_filter", "value": recipient_address_regex_filter})
    if subject_substring: params_for_ui.append({"name": "subject_substring", "value": subject_substring})
    if body_substring: params_for_ui.append({"name": "body_substring", "value": body_substring})
    if start_date or end_date: params_for_ui.append({"name": "period", "value": f"{start_date} .. {end_date}"})
    if has_attachments is not None: params_for_ui.append({"name": "has_attachments", "value": str(has_attachments)})
    if is_read is not None: params_for_ui.append({"name": "is_read", "value": str(is_read)})    
    
    if not confirm_tools_call(f"{len(messages)} {QCoreApplication.translate("distribution_list_agent", "Emails aus Outlook zur Verteilerliste zufügen")}", params_for_ui, True):
        return cancelled_by_user_message()    

    new_count = 0
    existing_count = 0
    error_count = 0
    errors = []

    db = get_contact_db()

    for msg in messages:
        email = msg.get("from", {}).get("emailAddress", {}).get("address")
        displayname = msg.get("from", {}).get("emailAddress", {}).get("name")

        if not email:
            continue  # skip if no sender info

        try:            
            was_new = db.add_email_to_list(email, list_name, displayname)

            if was_new:
                new_count += 1
            else:
                existing_count += 1
        except Exception as e:
            errors.append(str(e))
            error_count += 1

    return json.dumps({    
        "summary": f"Added {new_count} new addresses to list '{list_name}', {existing_count} were already present.",
        "errors": errors,
    }, ensure_ascii=False, indent=2)


@function_tool
def add_outlook_contacts_to_distribution_list(list_name: str, search_text: Optional[str] = None) -> str:
    """
    Search Outlook Contacts by optional text (name, email, company).
    - search_text: filter string
    Add them to the specified Distribution List.
    """
    gc = get_graph_client()
    if not gc.is_logged_in():
        return not_connected_message()    

    result = gc.search_contacts(query=search_text or None)        
    if not result.success:
        return f"Status {result.status}: {result.error}"
    
    if not result.data:
        return "No matching contacts found."
    
    params_for_ui = []
    if list_name: params_for_ui.append({"name": "distribution_list_name", "value": list_name})
    if search_text: params_for_ui.append({"name": "search_text", "value": search_text})

    if not confirm_tools_call(f"{len(result.data)} {QCoreApplication.translate("distribution_list_agent", "Kontakte zur Verteilerliste hinzufügen")}", params_for_ui, True):
        return cancelled_by_user_message()    
    
    new_count = 0
    existing_count = 0
    error_count = 0
    errors = []

    db = get_contact_db() 
    for c in result.data:
        email = c.get("emailAddresses", [{}])[0].get("address") if c.get("emailAddresses") else None
        displayname = c.get("displayName")

        if not email:
            continue  # skip if no sender info

        try:            
            was_new = db.add_email_to_list(email, list_name, displayname)

            if was_new:
                new_count += 1
            else:
                existing_count += 1
        except Exception as e:
            errors.append(str(e))
            error_count += 1
        

    return json.dumps({    
        "summary": f"Added {new_count} new addresses to list '{list_name}', {existing_count} were already present.",
        "errors": errors,
    }, ensure_ascii=False, indent=2)


@function_tool
def send_email_to_distribution_list(list_name: str, subject: str, body: str) -> str:
    """
    Send an email to all members in a local Distribution List.
    """ 

    gc = get_graph_client()
    if not gc.is_logged_in():
        return not_connected_message()

    try:
        emails = get_contact_db().get_emails(list_name)        
    except Exception as e:
        return f"Error getting emails from list: {str(e)}"
    
    if not emails:
        return f"The specified list is empty, nothing to send."
    
    params_for_ui = []
    if list_name: params_for_ui.append({"name": "list_name", "value": list_name})    
    if subject: params_for_ui.append({"name": "subject", "value": subject})    
    if body: params_for_ui.append({"name": "body", "value": body})
    params_for_ui.append({"name": "count", "value": len(emails)})
    
    if not confirm_tools_call(QCoreApplication.translate("distribution_list_agent", "Email an Verteilerliste senden"), params_for_ui, True):
        return cancelled_by_user_message()
    
    success = 0
    for email in emails:
        result = gc.send_mail(to=email, subject=subject, body=body)
        if result.success:
            success += 1

    return f"{success} / {len(emails)} emails have been sent."
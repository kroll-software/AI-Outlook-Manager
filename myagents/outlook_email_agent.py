# outlook_email_agent.py

import os
import re
from typing import Optional
from agents import function_tool
from myagents.tools_helpers import *
from myagents.base_agent import BaseAgent, system_prompt_tool_usage
from core.graph_auth_client import get_graph_client

from PySide6.QtCore import QCoreApplication
# tr_context = "outlook_email_agent"

class OutlookEmailAgent(BaseAgent):
    def get_name(self) -> str:
        return "Outlook Email Agent"
    
    def get_handoff_description(self):
        return "Performs many actions with emails in Outlook 365 using the MS-Graph API."
    
    def get_system_prompt(self) -> str:
        return """
            Use your tools to manage emails in Outlook 365, as requested by user.
            Analyse what the user **exactly** wants.

            Reference folders by their ID or a Well-Known-Folder Name:
            - msgfolderroot
            - inbox
            - drafts
            - outbox
            - sentitems
            - deleteditems
            - archive
            - junkemail
            - conversationhistory

            """ + system_prompt_tool_usage
    
    def get_tools(self) -> list:
        return [        
            get_email_by_id,            
            send_email,
            reply_email_by_id,
            forward_email_by_id,
            delete_email_by_id,
            delete_emails_by_filter,
            archive_email_by_id,
            set_email_read_status_by_id,
            
            search_emails,            
            copy_emails_to_folder,
            move_emails_to_folder,

            list_folders,
            create_folder,
            move_folder,
            rename_folder,
            delete_folder,
            count_emails_in_folder,            

            get_user_info,
            get_system_time
        ]


@function_tool
def get_email_by_id(message_id: str) -> str:
    """
    Retrieves the full content of an email based on its ID.

    Parameters:
    - message_id: The unique ID of the email.
    """

    gc = get_graph_client()
    if not gc.is_logged_in():
        return not_connected_message()    

    if not confirm_tools_call(QCoreApplication.translate("outlook_email_agent", "E-Mail lesen"), [{"name": "message_id", "value": message_id}], False):
        return cancelled_by_user_message()

    result = gc.read_mail(message_id)
    if not result.success:
        return result.combined_error()

    subject = result.data.get("subject", "(no subject)")
    sender = result.data.get("sender", {}).get("emailAddress", {}).get("name", "unknown")
    body = result.data.get("body", {}).get("content", "[no content]")

    return f"Subject: {subject}\nSender: {sender}\n\nContent:\n{body}"    


# Tool: Sende E-Mail
@function_tool
def send_email(to: str, subject: str, body: str) -> str:
    """
    Sends an email to a specific address.

    Parameters:
    - to: Recipient address
    - subject: Subject line
    - body: Message text (as plain text)
    """
    
    gc = get_graph_client()
    if not gc.is_logged_in():
        return not_connected_message()

    parameters = [
        {"name": "to", "value": to},
        {"name": "subject", "value": subject},
        {"name": "body", "value": body}
    ]

    if not confirm_tools_call(QCoreApplication.translate("outlook_email_agent", "E-Mail senden"), parameters, True):
        return cancelled_by_user_message()

    result = gc.send_mail(to=to, subject=subject, body=body)
    if not result.success:
        return result.combined_error()
    return f"Email successfully sent to {to}."

@function_tool
def reply_email_by_id(message_id: str, comment: str, reply_all: bool = False) -> str:
    """
    Reply to a single email by its ID.
    If reply_all is True, reply will be sent to all recipients.
    Parameter "comment" is the body-text of your reply mail.
    """
    gc = get_graph_client()
    if not gc.is_logged_in():
        return not_connected_message()
    
    params_for_ui = []
    if message_id: params_for_ui.append({"name": "message_id", "value": message_id})
    if comment: params_for_ui.append({"name": "comment", "value": comment})
    if reply_all: params_for_ui.append({"name": "reply_all", "value": reply_all})    

    if not confirm_tools_call(QCoreApplication.translate("outlook_email_agent", "E-Mail beantworten"), params_for_ui, True):
        return cancelled_by_user_message()

    if reply_all:
        result = gc.reply_all_mail(message_id, comment)
    else:
        result = gc.reply_mail(message_id, comment)
    
    if not result.success:
        return result.combined_error()
    return "Reply sent successfully."

@function_tool
def forward_email_by_id(message_id: str, to: str) -> str:
    """
    Forwards an email to a specific address.

    Parameters:
    - message_id: ID of the email
    - to: Recipient address    
    """
    
    gc = get_graph_client()
    if not gc.is_logged_in():
        return not_connected_message()

    parameters = [
        {"name": "message_id", "value": message_id},
        {"name": "to", "value": to},
    ]

    if not confirm_tools_call(QCoreApplication.translate("outlook_email_agent", "E-Mail weiterleiten"), parameters, True):
        return cancelled_by_user_message()

    result = gc.forward_mail(message_id=message_id, recipient=to)
    if not result.success:
        return result.combined_error()
    
    return f"Email successfully forwarded to {to}."    

@function_tool
def search_emails(
    folder_id: Optional[str] = None,
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
    top: int = 10,
) -> str:
    """
    Search for emails with multiple options:
    - folder_id: restrict search to a specific Outlook folder (ID or well-known name)
    - exact_sender_address: exact match of sender address
    - sender_address_regex_filter: regex filter against sender address
    - exact_recipient_address: exact match of recipient address (To, Cc, Bcc)
    - recipient_address_regex_filter: regex filter against recipient addresses
    - subject_substring: substring in subject (fulltext search)
    - body_substring: substring in body (fulltext search)
    - start_date / end_date: filter by receivedDateTime (ISO 8601: YYYY-MM-DD)
    - has_attachments: filter mails with/without attachments
    - is_read:  filter mails which are read/unread
    - top: max number of results to return (default 10)
    """

    gc = get_graph_client()
    if not gc.is_logged_in():
        return not_connected_message()

    # ---- UI-Confirm (falls gewünscht) ----
    params_for_ui = []
    if folder_id: params_for_ui.append({"name": "folder_id", "value": gc.resolve_folder_name(folder_id)})
    if exact_sender_address: params_for_ui.append({"name": "exact_sender_address", "value": exact_sender_address})
    if sender_address_regex_filter: params_for_ui.append({"name": "sender_address_regex_filter", "value": sender_address_regex_filter})
    if exact_recipient_address: params_for_ui.append({"name": "exact_recipient_address", "value": exact_recipient_address})
    if recipient_address_regex_filter: params_for_ui.append({"name": "recipient_address_regex_filter", "value": recipient_address_regex_filter})
    if subject_substring: params_for_ui.append({"name": "subject_substring", "value": subject_substring})
    if body_substring: params_for_ui.append({"name": "body_substring", "value": body_substring})
    if start_date or end_date: params_for_ui.append({"name": "period", "value": f"{start_date} .. {end_date}"})
    if has_attachments is not None: params_for_ui.append({"name": "has_attachments", "value": str(has_attachments)})
    if is_read is not None: params_for_ui.append({"name": "is_read", "value": str(is_read)})
    if top is not None: params_for_ui.append({"name": "top", "value": str(top)})

    if not confirm_tools_call(QCoreApplication.translate("outlook_email_agent", "Emails suchen"), params_for_ui, False):
        return cancelled_by_user_message()

    # Suche über zentrale Funktion
    result = gc.query_emails(
        folder_id=folder_id,
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
        top=top,
    )

    if not result.success:
        return result.combined_error()
    return format_emails(result.data)

@function_tool
def delete_email_by_id(message_id: str) -> str:
    """
    Delete a single email by its ID
    """
    gc = get_graph_client()
    if not gc.is_logged_in():
        return not_connected_message()
    
    # ---- UI-Confirm (falls gewünscht) ----
    params_for_ui = []
    if message_id: params_for_ui.append({"name": "message_id", "value": message_id})    

    if not confirm_tools_call(QCoreApplication.translate("outlook_email_agent", "Email löschen"), params_for_ui, True):
        return cancelled_by_user_message()
    
    result = gc.delete_mail(message_id)
    if not result.success:
        return result.combined_error()
    return "Email successfully deleted."    

@function_tool
def archive_email_by_id(message_id: str) -> str:
    """
    Archive a single email by its ID
    """
    gc = get_graph_client()
    if not gc.is_logged_in():
        return not_connected_message()
    
    # ---- UI-Confirm (falls gewünscht) ----
    params_for_ui = []
    if message_id: params_for_ui.append({"name": "message_id", "value": message_id})    

    if not confirm_tools_call(QCoreApplication.translate("outlook_email_agent", "Email archivieren"), params_for_ui, True):
        return cancelled_by_user_message()

    result = gc.archive_mail(message_id)
    if not result.success:
        return result.combined_error()    
    return "Email successfully deleted."


@function_tool
def set_email_read_status_by_id(message_id: str, is_read: bool) -> str:
    """
    Mark an email as read or unread.
    - message_id: ID of the email
    - is_read: True = mark as read, False = mark as unread
    """
    gc = get_graph_client()
    if not gc.is_logged_in():
        return not_connected_message()
    
    # ---- UI-Confirm (falls gewünscht) ----
    params_for_ui = []
    if message_id: params_for_ui.append({"name": "message_id", "value": message_id})
    if is_read: params_for_ui.append({"name": "is_read", "value": is_read})

    if not confirm_tools_call(QCoreApplication.translate("outlook_email_agent", "Email als gelesen markieren"), params_for_ui, True):
        return cancelled_by_user_message()
    
    result = gc.set_email_read_status(message_id, is_read)
    if not result.success:
        return result.combined_error()
    return f"Email successfully marked as {'read' if is_read else 'unread'}."    


@function_tool
def delete_emails_by_filter(
    folder_id: Optional[str] = None,    
    exact_sender_address: Optional[str] = None,
    sender_address_regex_filter: Optional[str] = None,
    exact_recipient_address: Optional[str] = None,
    recipient_address_regex_filter: Optional[str] = None,
    subject_substring: Optional[str] = None,
    body_substring: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    has_attachments: Optional[bool] = None,
    is_read: Optional[bool] = None
) -> str:
    """
    Search for emails with multiple options:
    - folder_id: restrict search to a specific Outlook folder (ID or well-known name)
    - exact_sender_address: exact match of sender address
    - sender_address_regex_filter: regex filter against sender address
    - exact_recipient_address: exact match of recipient address (To, Cc, Bcc)
    - recipient_address_regex_filter: regex filter against recipient addresses
    - subject_substring: substring in subject (fulltext search)
    - body_substring: substring in body (fulltext search)
    - start_date / end_date: filter by receivedDateTime (ISO 8601: YYYY-MM-DD)
    - has_attachments: filter mails with/without attachments
    - is_read:  filter mails which are read/unread
    - top: max number of results to return (default 10)
    
    """

    gc = get_graph_client()
    if not gc.is_logged_in():
        return not_connected_message()    

    # Suche über zentrale Funktion
    result = gc.query_emails(
        folder_id=folder_id,
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
        return result.combined_error()

    messages = result.data
    if not messages or len(messages) == 0:
        return "No matching emails found."

    # ---- UI-Confirm (falls gewünscht) ----
    params_for_ui = []
    if folder_id: params_for_ui.append({"name": "folder_id", "value": gc.resolve_folder_name(folder_id)})
    if exact_sender_address: params_for_ui.append({"name": "exact_sender_address", "value": exact_sender_address})
    if sender_address_regex_filter: params_for_ui.append({"name": "sender_address_regex_filter", "value": sender_address_regex_filter})
    if exact_recipient_address: params_for_ui.append({"name": "exact_recipient_address", "value": exact_recipient_address})
    if recipient_address_regex_filter: params_for_ui.append({"name": "recipient_address_regex_filter", "value": recipient_address_regex_filter})
    if subject_substring: params_for_ui.append({"name": "subject_substring", "value": subject_substring})
    if body_substring: params_for_ui.append({"name": "body_substring", "value": body_substring})
    if start_date or end_date: params_for_ui.append({"name": "period", "value": f"{start_date} .. {end_date}"})
    if has_attachments is not None: params_for_ui.append({"name": "has_attachments", "value": str(has_attachments)})
    if is_read is not None: params_for_ui.append({"name": "is_read", "value": str(is_read)})    
    
    if not confirm_tools_call(f"{len(messages)} {QCoreApplication.translate("outlook_email_agent", "Emails löschen?")}", params_for_ui, True):
        return cancelled_by_user_message()
    
    success = 0
    errors = []
    for msg in messages:
        result = gc.delete_mail(msg["id"])
        if result.success:
            success += 1
        else:
            errors.append(result.combined_error())

    return json.dumps({    
        "summary": f"Deleted {success}/{len(messages)} emails.",
        "errors": errors,
    }, ensure_ascii=False, indent=2)    


@function_tool
def copy_emails_to_folder(
    target_folder_id: str,
    source_folder_id: Optional[str] = None,    
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
    **Copy** all matching emails into another folder.
    Don't confuse *copy* and *move*.

    Args:
        - target_folder_id (str): Target folder ID or well-known name, where emails should be copied.
        - source_folder_id (Optional[str]): Source folder ID or well-known name. If omitted, search across all folders.
        - exact_sender_address (Optional[str]): Match emails from this exact sender.
        - sender_address_regex_filter (Optional[str]): Apply regex filter against sender email.
        - exact_recipient_address (Optional[str]): Match emails to this exact recipient.
        - recipient_address_regex_filter (Optional[str]): Apply regex filter against recipient email.
        - subject_substring (Optional[str]): Search for substring in subject.
        - body_substring (Optional[str]): Search for substring in body.
        - start_date (Optional[str]): Only include mails received after this date (YYYY-MM-DD).
        - end_date (Optional[str]): Only include mails received before this date (YYYY-MM-DD).
        - has_attachments (Optional[bool]): If True, only mails with attachments. If False, only without.
        - is_read:  filter mails which are read/unread

    Returns:
        str: Summary of the operation (how many emails were copied).

    Notes:
        - This function first queries all matching emails with `query_emails`.
        - Then asks for user confirmation, showing how many messages would be copied.
        - Finally performs the copy operation using Microsoft Graph.
    """
    gc = get_graph_client()
    if not gc.is_logged_in():
        return not_connected_message()

    # Step 1: Query all emails
    result = gc.query_emails(
        folder_id=source_folder_id,
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
        top=None  # important: fetch ALL
    )

    if not result.success:
        return result.combined_error()

    messages = result.data
    if not messages:
        return "No matching emails found."

    # ---- UI-Confirm (falls gewünscht) ----
    params_for_ui = []
    if target_folder_id: params_for_ui.append({"name": "target_folder_id", "value": gc.resolve_folder_name(target_folder_id)})
    if source_folder_id: params_for_ui.append({"name": "source_folder_id", "value": gc.resolve_folder_name(source_folder_id)})
    if exact_sender_address: params_for_ui.append({"name": "exact_sender_address", "value": exact_sender_address})
    if sender_address_regex_filter: params_for_ui.append({"name": "sender_address_regex_filter", "value": sender_address_regex_filter})
    if exact_recipient_address: params_for_ui.append({"name": "exact_recipient_address", "value": exact_recipient_address})
    if recipient_address_regex_filter: params_for_ui.append({"name": "recipient_address_regex_filter", "value": recipient_address_regex_filter})
    if subject_substring: params_for_ui.append({"name": "subject_substring", "value": subject_substring})
    if body_substring: params_for_ui.append({"name": "body_substring", "value": body_substring})
    if start_date or end_date: params_for_ui.append({"name": "period", "value": f"{start_date} .. {end_date}"})
    if has_attachments is not None: params_for_ui.append({"name": "has_attachments", "value": str(has_attachments)})
    if is_read is not None: params_for_ui.append({"name": "is_read", "value": str(is_read)})

    if not confirm_tools_call(f"{len(messages)} {QCoreApplication.translate("outlook_email_agent", "Emails in Ordner kopieren")}", params_for_ui, True):
        return cancelled_by_user_message()    

    # Step 3: Perform copy
    success = 0
    errors = []
    for msg in messages:        
        result = gc.move_or_copy_mail(msg["id"], target_folder_id, move=False)        
        if result.success:
            success += 1
        else:
            errors.append(result.combined_error())

    return json.dumps({    
        "summary": f"Copied {success}/{len(messages)} emails to folder '{target_folder_id}'.",
        "errors": errors,
    }, ensure_ascii=False, indent=2)    


@function_tool
def move_emails_to_folder(
    target_folder_id: str,
    source_folder_id: Optional[str] = None,    
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
    **Move** all matching emails into another folder.
    Don't confuse *move* and *copy*.

    Same parameters and behavior as `copy_emails_to_folder`, except messages will be **moved** instead of copied.
    """
    gc = get_graph_client()
    if not gc.is_logged_in():
        return not_connected_message()

    result = gc.query_emails(
        folder_id=source_folder_id,
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
        return result.combined_error()

    messages = result.data
    if not messages:
        return "No matching emails found."

    # ---- UI-Confirm (falls gewünscht) ----
    params_for_ui = []
    if target_folder_id: params_for_ui.append({"name": "target_folder_id", "value": gc.resolve_folder_name(target_folder_id)})
    if source_folder_id: params_for_ui.append({"name": "source_folder_id", "value": gc.resolve_folder_name(source_folder_id)})
    if exact_sender_address: params_for_ui.append({"name": "exact_sender_address", "value": exact_sender_address})
    if sender_address_regex_filter: params_for_ui.append({"name": "sender_address_regex_filter", "value": sender_address_regex_filter})
    if exact_recipient_address: params_for_ui.append({"name": "exact_recipient_address", "value": exact_recipient_address})
    if recipient_address_regex_filter: params_for_ui.append({"name": "recipient_address_regex_filter", "value": recipient_address_regex_filter})
    if subject_substring: params_for_ui.append({"name": "subject_substring", "value": subject_substring})
    if body_substring: params_for_ui.append({"name": "body_substring", "value": body_substring})
    if start_date or end_date: params_for_ui.append({"name": "period", "value": f"{start_date} .. {end_date}"})
    if has_attachments is not None: params_for_ui.append({"name": "has_attachments", "value": str(has_attachments)})
    if is_read is not None: params_for_ui.append({"name": "is_read", "value": str(is_read)})

    if not confirm_tools_call(f"{len(messages)} {QCoreApplication.translate("outlook_email_agent", "Emails in Ordner verschieben")}", params_for_ui, True):
        return cancelled_by_user_message()    

    success = 0
    errors = []
    for msg in messages:
        result = gc.move_or_copy_mail(msg["id"], target_folder_id, move=True)
        if result.success:
            success += 1            
        else:
            errors.append(result.combined_error())

    return json.dumps({    
        "summary": f"Moved {success}/{len(messages)} emails to folder '{target_folder_id}'.",
        "errors": errors,
    }, ensure_ascii=False, indent=2)


@function_tool
def create_folder(parent_folder_id: str, display_name: str) -> str:
    """
    Create a new Outlook mail folder under the specified parent folder.
    parent_folder_id must be a valid folder ID or a well-known name.
    """
    gc = get_graph_client()
    if not gc.is_logged_in():
        return not_connected_message()

    if not confirm_tools_call(QCoreApplication.translate("outlook_email_agent", "Ordner erstellen"), [{"name": "parent_folder_id", "value": gc.resolve_folder_name(parent_folder_id)}, {"name": "display_name", "value": display_name}, ], True):
        return cancelled_by_user_message()
    
    result = gc.create_folder(parent_folder_id, display_name)
    if not result.success:
        return result.combined_error()
    return f"Created folder '{display_name}' with id {result.data.get('id')}"    

@function_tool
def delete_folder(folder_id: str) -> str:
    """
    Delete an Outlook mail folder by its ID.
    Will not delete well-known system folders.
    """

    gc = get_graph_client()
    if not gc.is_logged_in():
        return not_connected_message()
    
    if gc.is_well_known_folder(folder_id):
        return f"Cannot delete system folder '{folder_id}'."    
    
    if not confirm_tools_call(QCoreApplication.translate("outlook_email_agent", "Ordner löschen"), [{"name": "folder_id", "value": gc.resolve_folder_name(folder_id)}], True):
        return cancelled_by_user_message()
    
    result = gc.delete_folder(folder_id)
    if not result.success:
        return result.combined_error()
    
    return f'Deleted folder "{folder_id}"'

@function_tool
def move_folder(folder_id: str, destination_folder_id: str) -> str:
    """
    Move an Outlook mail folder to a different destination folder by their ID.
    System folders cannot be moved.
    """
    
    gc = get_graph_client()
    if not gc.is_logged_in():
        return not_connected_message()
    
    if gc.is_well_known_folder(folder_id):
        return f"Cannot move system folder '{folder_id}'."

    if not confirm_tools_call(QCoreApplication.translate("outlook_email_agent", "Ordner verschieben"), [{"name": "folder_id", "value": gc.resolve_folder_name(folder_id)}, {"name": "destination_folder_id", "value": gc.resolve_folder_name(destination_folder_id)}], True):
        return cancelled_by_user_message()
    
    result = gc.move_folder(folder_id, destination_folder_id)
    if not result.success:
        return result.combined_error()
    
    return f"Moved folder {folder_id} to new parent {destination_folder_id}"


@function_tool
def rename_folder(folder_id: str, new_name: str) -> str:
    """
    Rename an Outlook mail folder.
    System folders cannot be renamed.
    """
    
    gc = get_graph_client()
    if not gc.is_logged_in():
        return not_connected_message()
    
    if gc.is_well_known_folder(folder_id):
        return f"Cannot rename system folder '{folder_id}'."
    
    if not new_name:
        return f"Invalid parameter value for '{new_name}'."

    if not confirm_tools_call(QCoreApplication.translate("outlook_email_agent", "Ordner umbenennen"), [{"name": "folder_id", "value": gc.resolve_folder_name(folder_id)}, {"name": "new_name", "value": new_name}], True):
        return cancelled_by_user_message()
    
    result = gc.rename_folder(folder_id, new_name)
    if not result.success:
        return result.combined_error()
    
    return f"Folder {folder_id} successfully renamed to {new_name}"
    

@function_tool
#def list_folders(parent_folder_id: str = None) -> str:
def list_folders() -> str:
    """
    List all Outlook folders and their IDs.    
    """
    gc = get_graph_client()
    if not gc.is_logged_in():
        return not_connected_message()    

    #if not confirm_tools_call(QCoreApplication.translate("outlook_email_agent", "Ordner auflisten"), [{"name": "parent_folder_id", "value": gc.resolve_folder_name(parent_folder_id)}], False):
    if not confirm_tools_call(QCoreApplication.translate("outlook_email_agent", "Ordner auflisten"), None, False):
        return cancelled_by_user_message()

    result = gc.list_folders(None)
    if not result.success:
        return result.combined_error()
    
    if not result.data:
        return "No folders found."
        
    return json.dumps(result.data, ensure_ascii=False, indent=2)    

@function_tool
def count_emails_in_folder(folder_id: str) -> str:
    """
    Count emails in a specific folder using Graph API folder properties.
    Much faster than fetching messages, since we only ask for totalItemCount.

    Parameters:
      - folder_id: Folder ID or Well-Known Name.
    """

    gc = get_graph_client()
    if not gc.is_logged_in():
        return not_connected_message()    

    if not confirm_tools_call(QCoreApplication.translate("outlook_email_agent", "Emails in Ordner zählen"), [{"name": "folder_id", "value": gc.resolve_folder_name(folder_id)}], False):
        return cancelled_by_user_message()

    result = gc.count_emails_in_folder(folder_id)
    if not result.success:
        return result.combined_error()
    
    ret = {
        "folder": result.data.get("displayName", folder_id),
        "totalItemCount": result.data.get("totalItemCount", 0),
        "unreadItemCount": result.data.get("unreadItemCount", 0),            
    }            
    return json.dumps(ret, ensure_ascii=False, indent=2)
    
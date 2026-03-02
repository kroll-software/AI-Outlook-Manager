# outlook_contacts_agent.py

import os
import re
from typing import Optional
from agents import function_tool
from myagents.tools_helpers import *
from myagents.base_agent import BaseAgent, system_prompt_tool_usage
from core.graph_auth_client import get_graph_client

from PySide6.QtCore import QCoreApplication
# tr_context = "outlook_contacts_agent"

class OutlookContactsAgent(BaseAgent):
    def get_name(self) -> str:
        return "Outlook Contacts Agent"
    
    def get_handoff_description(self):
        return "Performs many actions with Outlook Contacts in Outlook 365."
    
    def get_system_prompt(self) -> str:
        return """
            Use your tools to manage Contacts in Outlook 365, as requested by user.
            """ + system_prompt_tool_usage
    
    def get_tools(self) -> list:
        return [
            create_contact,
            update_contact,
            delete_contact,            
            search_contacts,
            
            get_user_info,
            get_system_time
        ]


# ----------------------------------------------------
# Tool: Create contact
# ----------------------------------------------------
@function_tool
def create_contact(given_name: str,
        surname: str,
        email: str,
        business_phone: Optional[str] = None,
        mobile_phone: Optional[str] = None,
        company: Optional[str] = None) -> str:
    """
    Create a new contact in Outlook.
    All parameters must be strings.
    - given_name: first name
    - surname: last name
    - email: primary email address
    - business_phone: optional business phone
    - mobile_phone: optional mobile phone
    - company: optional company name
    Returns the created contact info as JSON string.
    """
    gc = get_graph_client()
    if not gc.is_logged_in():
        return not_connected_message()

    params_for_ui = [
        {"name": "given_name", "value": given_name},
        {"name": "surname", "value": surname},
        {"name": "email", "value": email},
    ]
    if business_phone: params_for_ui.append({"name": "business_phone", "value": business_phone})
    if mobile_phone: params_for_ui.append({"name": "mobile_phone", "value": mobile_phone})
    if company: params_for_ui.append({"name": "company", "value": company})

    if not confirm_tools_call(QCoreApplication.translate("outlook_contacts_agent", "Kontakt erstellen"), params_for_ui, True):
        return cancelled_by_user_message()
        
    result = gc.create_contact(
        given_name=given_name,
        surname=surname,
        email=email,
        business_phone=business_phone,
        mobile_phone=mobile_phone,
        company_name=company
    )
    if not result.success:
        return result.combined_error()    
    return f"Created contact '{email}' with id {result.data.get('id')}"

# ----------------------------------------------------
# Tool: Delete contact
# ----------------------------------------------------
@function_tool
def delete_contact(contact_id: str) -> str:
    """
    Delete a contact by ID.
    Returns "deleted" if successful, or "error".
    """
    gc = get_graph_client()
    if not gc.is_logged_in():
        return not_connected_message()

    params_for_ui = [{"name": "contact_id", "value": contact_id}]
    if not confirm_tools_call(QCoreApplication.translate("outlook_contacts_agent", "Kontakt löschen"), params_for_ui, True):
        return cancelled_by_user_message()

    result = gc.delete_contact(contact_id)
    if not result.success:
        return result.combined_error()
    return "Contact was successfully deleted."    


# ----------------------------------------------------
# Tool: Update contact
# ----------------------------------------------------
@function_tool
def update_contact(contact_id: str,
        given_name: Optional[str] = None,
        surname: Optional[str] = None,
        email: Optional[str] = None,
        business_phone: Optional[str] = None,
        mobile_phone: Optional[str] = None,
        company: Optional[str] = None) -> str:
    """
    Update an existing contact in Outlook.
    All parameters are strings.
    - contact_id: ID of the contact to update
    - given_name, surname, email, business_phone, mobile_phone, company: optional updates
    Returns a status string.
    """
    gc = get_graph_client()
    if not gc.is_logged_in():
        return not_connected_message()

    params_for_ui = [{"name": "contact_id", "value": contact_id}]
    if given_name: params_for_ui.append({"name": "given_name", "value": given_name})
    if surname: params_for_ui.append({"name": "surname", "value": surname})
    if email: params_for_ui.append({"name": "email", "value": email})
    if business_phone: params_for_ui.append({"name": "business_phone", "value": business_phone})
    if mobile_phone: params_for_ui.append({"name": "mobile_phone", "value": mobile_phone})
    if company: params_for_ui.append({"name": "company", "value": company})

    if not confirm_tools_call(QCoreApplication.translate("outlook_contacts_agent", "Kontakt aktualisieren"), params_for_ui, True):
        return cancelled_by_user_message()

    result = gc.update_contact(
        contact_id=contact_id,
        given_name=given_name,
        surname=surname,
        email=email,
        business_phone=business_phone,
        mobile_phone=mobile_phone,
        company_name=company
    )
    if not result.success:
        return result.combined_error()    
    return "Contact was successfully updated."    


# ----------------------------------------------------
# Tool: Search contacts
# ----------------------------------------------------
@function_tool
def search_contacts(search_text: Optional[str] = None) -> str:
    """
    Search Outlook Contacts by optional text (name, email, company).
    - search_text: filter string
    Returns JSON with count and indexed results.
    """
    gc = get_graph_client()
    if not gc.is_logged_in():
        return not_connected_message()

    params_for_ui = []
    if search_text: params_for_ui.append({"name": "search_text", "value": search_text})

    if not confirm_tools_call(QCoreApplication.translate("outlook_contacts_agent", "Kontakte suchen"), params_for_ui, False):
        return cancelled_by_user_message()

    result = gc.search_contacts(query=search_text or None)        
    if not result.success:
        return result.combined_error()

    data = result.data
    results: List[Dict] = []    
    for idx, c in enumerate(data, start=1):
        results.append({
            "index": idx,
            "id": c.get("id"),
            "givenName": c.get("givenName"),
            "surname": c.get("surname"),
            #"email": c.get("emailAddresses", [{}])[0].get("address") if c.get("emailAddresses") else None,
            "email": c.get("email"),
            "businessPhones": c.get("businessPhones"),
            "mobilePhone": c.get("mobilePhone"),
            "companyName": c.get("companyName"),
        })

    return json.dumps({
        "count": len(results),
        "results": results
    }, ensure_ascii=False, indent=2)

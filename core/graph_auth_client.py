# auth/graph_auth_client.py

import os
import logging
import json
import re
from dataclasses import dataclass
from datetime import datetime
from threading import Thread, Event
from urllib.parse import quote
from typing import Optional, Dict, List, Any
from requests import Response
from msgraph.core import GraphClient
from azure.identity import (
    InteractiveBrowserCredential,
    TokenCachePersistenceOptions
)
from config import CLIENT_ID, TENANT_ID
from core.id_map_db import get_idmap_db

logger = logging.getLogger("graph_auth")

SCOPES = [
    "https://graph.microsoft.com/User.Read",
    "https://graph.microsoft.com/Mail.ReadWrite",
    "https://graph.microsoft.com/Mail.Send",
    "https://graph.microsoft.com/Calendars.ReadWrite",
    "https://graph.microsoft.com/Contacts.ReadWrite",
    "https://graph.microsoft.com/MailboxSettings.Read",
    "https://graph.microsoft.com/MailboxFolder.ReadWrite",
    "https://graph.microsoft.com/Notes.ReadWrite",
    "https://graph.microsoft.com/Notes.ReadWrite.All",
    "https://graph.microsoft.com/Tasks.ReadWrite"
]


@dataclass
class ApiResult:
    success: bool
    status: Optional[int] = None
    reason: Optional[str] = None
    data: Any = None
    error: Optional[str] = None

    def combined_error(self) -> str:        
        msg = ""
        if self.status and self.status > 0:
            msg += f"Status {self.status}: "
        if self.reason:
            msg += f"{self.reason} "
        if self.error:
            msg += f"Error: {self.error}"        
        return msg.strip()
    
    def __str__(self) -> str:
        if self.success:
            return f"Success (status={self.status})"
        return self.combined_error()

    @classmethod
    def ok(cls, data: Any = None, status: int = 200, reason: str = None) -> "ApiResult":
        return cls(success=True, status=status, reason=reason, data=data, error=None)

    @classmethod
    def fail(
        cls,
        error: str,
        status: Optional[int] = None,
        reason: str = None,
        data: Any = None,
    ) -> "ApiResult":
        return cls(success=False, status=status, reason=reason, data=data, error=error)

class GraphAuthClient:
    def __init__(self):
        self._credential = None
        self._client: Optional[GraphClient] = None
        self._user_data = None
        self._cancel_event = Event()
        self._login_running = False        
        self._id_map = get_idmap_db()
        self._folder_map = {}
        
        self._cache_options = TokenCachePersistenceOptions(
            name="outlook_gui_token",
            allow_unencrypted_storage=True  # ⚠️ Nur für Entwicklung
        )

        self.WELL_KNOWN_FOLDERS = {
            "msgfolderroot",
            "inbox",             
            "drafts",
            "outbox",
            "sentitems",  
            "deleteditems",
            "archive",
            "junkemail",                         
            "conversationhistory"
        }        

    def login_async(self, callback):
        if self._login_running:
            print("Trying to login while login is running.")
            return  # Schon ein Login aktiv

        self._login_running = True
        self._cancel_event.clear()

        def worker():
            try:
                cred = InteractiveBrowserCredential(
                    client_id=CLIENT_ID,
                    tenant_id=TENANT_ID,
                    cache_persistence_options=self._cache_options
                )
                token = cred.get_token(*SCOPES)  # blockiert
                if not self._cancel_event.is_set():
                    self._credential = cred
                    self._client = GraphClient(credential=cred, scopes=SCOPES)
                    user = self.get_user_data()                    
                    callback(True, user)
                else:
                    print("Login thread ended unsuccessfully.")
                    #callback(False, None)
            except Exception as e:
                callback(False, None)
            finally:
                self._login_running = False

        Thread(target=worker, daemon=True).start()

    def cancel_login(self):
        self._cancel_event.set()        

    def logout(self, clear_cache: bool = False):
        # Laufenden Login abbrechen
        if self._cancel_event:
            self._cancel_event.set()

        if not self.is_logged_in():
            logger.info("Logout aufgerufen, aber keine aktive Anmeldung vorhanden.")
            return

        if clear_cache and self._cache_options:
            try:
                # Je nach Plattform ist der Speicherort unterschiedlich.
                # azure-identity legt unter Windows/macOS/Linux OS-spezifisch ab.
                # Ein expliziter Lösch-Call existiert leider nicht,
                # daher einfache Variante: Cache-Datei ermitteln und entfernen.
                cache_file = self._get_cache_file_path()
                if cache_file and os.path.exists(cache_file):
                    os.remove(cache_file)
                    logger.info("Token-Cache gelöscht: %s", cache_file)
            except Exception as e:
                logger.warning("Token-Cache konnte nicht gelöscht werden: %s", str(e))

        self._credential = None
        self._client = None
        self._user_data = None

    def _get_cache_file_path(self) -> str | None:
        """
        Liefert den Pfad zur Cache-Datei für Token.
        ⚠️ azure-identity hat keinen offiziellen API-Zugriff darauf,
           daher ermitteln wir grob anhand der Plattform.
        """
        name = self._cache_options.name
        home = os.path.expanduser("~")

        if os.name == "nt":  # Windows
            return os.path.join(home, f"{name}.bin")
        elif os.name == "posix":
            return os.path.join(home, f".IdentityService/{name}.bin")
        else:
            return None

    def is_logged_in(self) -> bool:
        #return self._credential is not None and self._client is not None    
        return self._client is not None    

    def get_client(self) -> Optional[GraphClient]:
        return self._client    

    def get_user_data(self) -> Optional[dict]:
        if not self._client:
            return None
        if not self._user_data:
            try:
                response = self._client.get("/me")
                data = response.json()
                if "error" in data:
                    logger.error("Error calling /me: %s", json.dumps(data["error"], ensure_ascii=False, indent=2))
                    return None
                self._user_data = data
            except Exception as e:
                logger.exception("Error accessing /me: %s", str(e))
                return None
        return self._user_data    
    
    # --- intern: EWS→REST ID-Übersetzung (Fallback) ---
    def translate_to_rest_id(self, message_id: str) -> Optional[str]:
        """
        Try to convert a non-REST (e.g., EWS) message id to a Graph REST id using translateExchangeIds.
        """
        if not self._client:
            return None
        payload = {
            "inputIds": [message_id],
            "sourceIdType": "ewsId",
            "targetIdType": "restId"
        }
        try:
            resp = self._client.post("/me/translateExchangeIds", json=payload)
            if resp.status_code == 200:
                items = resp.json().get("value", [])
                if items and items[0].get("targetId"):
                    return items[0]["targetId"]
            return None
        except:
            return None
    
    def resolve_folder_name(self, short_folder_id) -> str:        
        return self._folder_map.get(short_folder_id, short_folder_id)
    
    def reset_folder_map(self):
        self._folder_map.clear()

    def response_ok(self, response: Response) -> bool:
        return response and 200 <= response.status_code < 300

    def response2result(self, response: Response, data = None) -> ApiResult:
        if response is None:        
            return ApiResult.fail("no response.", status=0)

        try:
            if data is None:
                data = response.json()
        except Exception:
            data = None

        if 200 <= response.status_code < 300:
            return ApiResult.ok(
                data=data,
                status=response.status_code
            )
        else:
            # Graph liefert meist detailierte Fehlermeldungen in JSON
            try:
                err = response.json()
                msg = err.get("error", {}).get("message", response.text)
            except Exception:
                msg = response.text
            return ApiResult.fail(
                error=msg,
                status=response.status_code,
                reason=response.reason
            )
        
    def exception2result(self, e: Exception, status: int = 0) -> ApiResult:
        return ApiResult.fail(str(e))
      
    def is_well_known_folder(self, folder: str) -> bool:
        return folder.lower() in self.WELL_KNOWN_FOLDERS

    def create_folder(self, parent_folder_id: str, display_name: str) -> ApiResult:        
        try:
            if not parent_folder_id in self.WELL_KNOWN_FOLDERS:
                parent_folder_id = self._id_map.expand_id(parent_folder_id)
            
            response = self._client.post(f"/me/mailFolders/{parent_folder_id}/childFolders", json={
                "displayName": display_name
            })

            data = response.json()
            data["id"] = self._id_map.shorten_id(data.get("id"))
            data["parentFolderId"] = self._id_map.shorten_id(data.get("parentFolderId"))
            data.pop("@odata.context", None)
            self._folder_map[data.get("id")] = data.get("displayName")

            return self.response2result(response, data=data)
        except Exception as e:
            return self.exception2result(e)
        
    def delete_folder(self, folder_id: str) -> ApiResult:
        try:
            if not folder_id in self.WELL_KNOWN_FOLDERS:
                folder_id = self._id_map.expand_id(folder_id)

            response = self._client.delete(f"/me/mailFolders/{folder_id}")            
            return self.response2result(response)
        except Exception as e:
            return self.exception2result(e)
        
    def move_folder(self, folder_id: str, destination_folder_id: str) -> ApiResult:        
        try:
            if not folder_id in self.WELL_KNOWN_FOLDERS:
                folder_id = self._id_map.expand_id(folder_id)

            if not destination_folder_id in self.WELL_KNOWN_FOLDERS:
                destination_folder_id = self._id_map.expand_id(destination_folder_id)
            
            response = self._client.post(f"/me/mailFolders/{folder_id}/move", json={
                "destinationId": destination_folder_id
            })
            return self.response2result(response)            
        except Exception as e:
            return self.exception2result(e)
        
    def rename_folder(self, folder_id: str, new_name: str) -> ApiResult:
        try:
            if not folder_id in self.WELL_KNOWN_FOLDERS:
                folder_id = self._id_map.expand_id(folder_id)

            response = self._client.patch(
                f"/me/mailFolders/{folder_id}",
                json={"displayName": new_name}
            )
            return self.response2result(response)
        except Exception as e:
            return self.exception2result(e)

    def list_folders(self, parent_folder_id: str = None) -> ApiResult:
        """
        Listet alle Mail-Ordner (inkl. Unterordner, rekursiv).
        Holt bei Bedarf mehrere Seiten via @odata.nextLink.
        Liefert am Ende (über response2result) die erste Response, die für den
        angegebenen Parent geladen wurde, und die gesamte Folder-Liste.
        """

        def fetch_page(url: str):
            response = self._client.get(url)
            data = response.json()
            folders = data.get("value", [])
            next_link = data.get("@odata.nextLink")
            return response, folders, next_link

        def collect_folders(parent_id: str = None):
            if parent_id:
                url = f"/me/mailFolders/{parent_id}/childFolders"
            else:
                url = "/me/mailFolders"

            all_folders = []
            next_url = url
            first_response = None
            last_response = None

            while next_url:
                response, folders, next_url = fetch_page(next_url)
                if first_response is None:
                    first_response = response
                last_response = response

                for f in folders:
                    clean = dict(f)  # Kopie, damit wir nicht im Original rumschreiben                    
                    clean["id"] = self._id_map.shorten_id(clean.get("id"))
                    clean["parentFolderId"] = self._id_map.shorten_id(clean.get("parentFolderId"))
                    all_folders.append(clean)

                    # Rekursiv Kinder holen — korrekt entpacken und nur die Folder-Liste erweitern
                    if f.get("childFolderCount") and int(f["childFolderCount"]) > 0:
                        _, child_folders = collect_folders(f.get("id"))
                        if child_folders:
                            all_folders.extend(child_folders)

            # gib die erste gelesene Response (falls vorhanden) zurück,
            # sonst die letzte (falls etwas schief ging)
            return (first_response or last_response), all_folders

        try:
            if not parent_folder_id in self.WELL_KNOWN_FOLDERS:
                parent_folder_id = self._id_map.expand_id(parent_folder_id)

            root_clean = None
            if parent_folder_id in [None, "", "/", "msgfolderroot"]:
                # Rootfolder separat abholen
                root_response = self._client.get("/me/mailFolders/msgfolderroot")
                if not self.response_ok(root_response):
                    return self.response2result(root_response)

                root_data = root_response.json()
                root_clean = dict(root_data)
                root_clean["id"] = self._id_map.shorten_id(root_clean.get("id"))
                root_clean["parentFolderId"] = self._id_map.shorten_id(root_clean.get("parentFolderId"))

            response, all_folders = collect_folders(parent_folder_id)

            # Root an den Anfang setzen
            if root_clean:
                all_folders.insert(0, root_clean)

            if parent_folder_id in [None, "", "/", "msgfolderroot"]:
                self._folder_map.clear()
            for f in all_folders:
                id = f.get("id")
                name = f.get("displayName")                
                self._folder_map[id] = name

            return self.response2result(response, data=all_folders)
        except Exception as e:
            return self.exception2result(e)

        
    def count_emails_in_folder(self, folder_id: str) -> ApiResult:
        try:
            if not folder_id in self.WELL_KNOWN_FOLDERS:
                folder_id = self._id_map.expand_id(folder_id)

            response = self._client.get(
                f"/me/mailFolders/{folder_id}?$select=displayName,totalItemCount,unreadItemCount"
            )
            return self.response2result(response)
        except Exception as e:
            return self.exception2result(e)


    def move_or_copy_mail(self, message_id: str, target_folder: str, move: bool = False) -> ApiResult:
        """
        Move or copy a mail to another folder using Microsoft Graph API.

        Args:
            mail_id: The REST-compatible ID of the message to move or copy.
            target_folder: The target folder name or ID.
            move: If True, the message will be moved. If False, it will be copied.

        Returns:
            dict with keys:
            - success (bool)
            - status (int | None)
            - action ("move"|"copy")
            - mail_id (str)
            - target_folder (str)
            - new_id (str | None)
            - error (str | None)
        """
        try:
            id = self._id_map.expand_id(message_id)
            if not id:
                return ApiResult.fail("Error: Unknown message_id.")   
            
            if not target_folder in self.WELL_KNOWN_FOLDERS:
                target_folder = self._id_map.expand_id(target_folder)

            endpoint = f"/me/messages/{id}/{'move' if move else 'copy'}"
            payload = {"destinationId": target_folder}

            response = self._client.post(endpoint, json=payload)
            return self.response2result(response)

        except Exception as e:
            return self.exception2result(e)

    def send_mail(self, to: str, subject: str, body: str) -> ApiResult:
        message = {
            "message": {
                "subject": subject,
                "body": {
                    "contentType": "Text",
                    "content": body
                },
                "toRecipients": [
                    {"emailAddress": {"address": to}}
                ]
            },
            "saveToSentItems": "true"
        }

        try:
            response = self._client.post("/me/sendMail", json=message)            
            return self.response2result(response)
        except Exception as e:
            return self.exception2result(e)
        
    def reply_mail(self, message_id: str, comment: str) -> ApiResult:
        """
        Reply to a single email by its ID with a comment (text body).
        """
        try:
            id = self._id_map.expand_id(message_id)
            if not id:
                return ApiResult.fail("Error: Unknown message_id.")   
            
            url = f"/me/messages/{id}/reply"
            payload = {
                "comment": comment
            }
            response = self._client.post(url, json=payload)
            return self.response2result(response)
        except Exception as e:
            return self.exception2result(e)

    def reply_all_mail(self, message_id: str, comment: str) -> ApiResult:
        """
        Reply to all recipients of a single email by its ID.
        """
        try:
            id = self._id_map.expand_id(message_id)
            if not id:
                return ApiResult.fail("Error: Unknown message_id.")   
            
            url = f"/me/messages/{id}/replyAll"
            payload = {
                "comment": comment
            }
            response = self._client.post(url, json=payload)
            return self.response2result(response)
        except Exception as e:
            return self.exception2result(e)

    def read_mail(self, message_id: str) -> ApiResult:
        try:
            id = self._id_map.expand_id(message_id)
            if not id:
                return ApiResult.fail("Error: Unknown message_id.")

            url = f"/me/messages/{id}"
            response = self._client.get(url)            
            return self.response2result(response)            
        except Exception as e:
            return self.exception2result(e)

    def delete_mail(self, message_id: str) -> ApiResult:
        """
        Move a mail to the Deleted Items folder (Trash).
        This is the safe 'delete' operation, emails remain recoverable.

        If you want permanent deletion, use purge_mail().
        """        
        try:
            id = self._id_map.expand_id(message_id)
            if not id:
                return ApiResult.fail("Error: Unknown message_id.")   
            deleted_folder_id = "deleteditems"            
            response = self._client.post(
                f"/me/messages/{id}/move",
                json={"destinationId": deleted_folder_id}
            )
            return self.response2result(response)

        except Exception as e:
            return self.exception2result(e)            

    def purge_mail(self, message_id: str) -> ApiResult:
        """
        Delete a mail by ID.

        This performs a **soft delete**:
        - The message is moved to the "Deleted Items" folder (Trash).
        - It is not permanently destroyed and can be restored by the user.
        - Final deletion only occurs if the "Deleted Items" folder is emptied.

        Args:
            mail_id: The REST-compatible ID of the message.

        Returns: dict with keys
            - success (bool)
            - status (int | None)
            - action ("delete")
            - mail_id (str)
            - target_folder (None)
            - new_id (None)
            - error (str | None)
        """        
        try:
            id = self._id_map.expand_id(message_id)
            if not id:
                return ApiResult.fail("Error: Unknown message_id.")   
            endpoint = f"/me/messages/{id}"
            response = self._client.delete(endpoint)
            return self.response2result(response)
        except Exception as e:
            return self.exception2result(e)            

    def archive_mail(self, message_id: str) -> ApiResult:
        """
        Move a mail to the Archive folder.

        Args:
            mail_id: The REST-compatible ID of the message.

        Returns: dict with keys
            - success (bool)
            - status (int | None)
            - action ("archive")
            - mail_id (str)
            - target_folder ("Archive")
            - new_id (str | None)
            - error (str | None)
        """
        try:
            id = self._id_map.expand_id(message_id)
            if not id:
                return ApiResult.fail("Error: Unknown message_id.")   
            
            folder_id = "archive"            

            endpoint = f"/me/messages/{id}/move"
            payload = {"destinationId": folder_id}
            response = self._client.post(endpoint, json=payload)
            return self.response2result(response)
        except Exception as e:
            return self.exception2result(e)            
        
    def forward_mail(self, message_id: str, recipient: str, comment: str = "") -> ApiResult:
        """
        Forward a mail to a given recipient.

        Args:
            mail_id: The REST-compatible ID of the message.
            recipient: Email address to forward to.
            comment: Optional message body prefix.

        Returns: dict with keys
            - success (bool)
            - status (int | None)
            - action ("forward")
            - mail_id (str)
            - target_folder (recipient email)
            - new_id (None, forward doesn’t create a new local mail ID)
            - error (str | None)
        """
        try:
            id = self._id_map.expand_id(message_id)
            if not id:
                return ApiResult.fail("Error: Unknown message_id.")   

            endpoint = f"/me/messages/{id}/forward"
            payload = {
                "comment": comment,
                "toRecipients": [
                    {"emailAddress": {"address": recipient}}
                ]
            }
            response = self._client.post(endpoint, json=payload)
            return self.response2result(response)

        except Exception as e:
            return self.exception2result(e)  

    def set_email_read_status(self, message_id: str, is_read: bool) -> ApiResult:
        """
        Mark an email as read or unread.

        :param message_id: The ID of the email to update
        :param is_read: True = mark as read, False = mark as unread
        """
        try:
            id = self._id_map.expand_id(message_id)
            if not id:
                return ApiResult.fail("Error: Unknown message_id.")   
            
            url = f"/me/messages/{id}"
            response = self._client.patch(url, json={"isRead": is_read})
            return self.response2result(response)
        except Exception as e:
            return self.exception2result(e)          
        
    # ----------------------------------------
    # Termin erstellen
    # ----------------------------------------
    def create_event(self, subject: str, start: datetime, end: datetime,
                    attendees: Optional[List[str]] = None, body: str = "") -> ApiResult:
        """
        Erstellt einen neuen Termin im Standardkalender.
        :param client: API-Client (mit .post Methode)
        :param subject: Betreff des Termins
        :param start: Startzeit (datetime, UTC oder mit Zeitzone)
        :param end: Endzeit (datetime)
        :param attendees: Liste von E-Mail-Adressen der Teilnehmer
        :param body: Beschreibungstext
        :return: Event-Daten als Dict
        """
        event = {
            "subject": subject,
            "body": {
                "contentType": "HTML",
                "content": body or ""
            },
            "start": {
                "dateTime": start.isoformat(),
                "timeZone": "UTC"
            },
            "end": {
                "dateTime": end.isoformat(),
                "timeZone": "UTC"
            }
        }

        if attendees:
            event["attendees"] = [
                {"emailAddress": {"address": a, "name": a}, "type": "required"}
                for a in attendees
            ]
        
        try:
            response = self._client.post("/me/events", json=event)

            data = response.json()
            data["id"] = self._id_map.shorten_id(data.get("id"))            
            data.pop("@odata.context", None)
            data.pop("@odata.etag", None)
            data.pop("changeKey", None)
            data.pop("iCalUId", None)
            data.pop("uid", None)
            data.pop("webLink", None)
            data.pop("responseStatus", None)

            return self.response2result(response, data=data)
        except Exception as e:
            return self.exception2result(e)


    # ----------------------------------------
    # Termin löschen
    # ----------------------------------------
    def delete_event(self, event_id: str) -> ApiResult:
        """
        Löscht einen Termin anhand der Event-ID.
        :param client: API-Client
        :param event_id: ID des Events
        :return: True wenn erfolgreich, False sonst
        """
        try:
            id = self._id_map.expand_id(event_id)
            if not id:
                return ApiResult.fail("Error: Unknown event_id.")
            response = self._client.delete(f"/me/events/{id}")
            return self.response2result(response)
        except Exception as e:
            return self.exception2result(e)


    # ----------------------------------------
    # Termine suchen (mit Filtern)
    # ----------------------------------------
    def search_events(self, start: datetime, end: datetime,
                    search_text: Optional[str] = None,
                    attendee: Optional[str] = None) -> ApiResult:
        """
        Sucht Termine im Zeitraum mit optionalem Filter nach Text oder Teilnehmer.
        :param client: API-Client
        :param start: Startzeitraum
        :param end: Endzeitraum
        :param search_text: Volltextsuche im Termin
        :param attendee: Suche nach Teilnehmer (E-Mail)
        :return: Liste der gefundenen Events
        """
        params = {
            "startDateTime": start.isoformat(),
            "endDateTime": end.isoformat()
        }

        try:
            response = self._client.get("/me/calendarview", params=params)
            if not self.response_ok(response):
                return self.response2result(response)

            data = response.json()
            events = data.get("value", [])

            # Optional: Filtern nach Textinhalt
            if search_text:
                events = [e for e in events if search_text.lower() in str(e).lower()]

            # Optional: Filtern nach Teilnehmer
            if attendee:
                events = [
                    e for e in events
                    if any(att.get("emailAddress", {}).get("address", "").lower() == attendee.lower()
                        for att in e.get("attendees", []))
                ]

            for event in events:
                event["id"] = self._id_map.shorten_id(event.get("id", None))

            return self.response2result(response, data=events)
        except Exception as e:
            return self.exception2result(e)
    
    def update_event(self, event_id: str,
                 subject: Optional[str] = None,
                 start: Optional[datetime] = None,
                 end: Optional[datetime] = None,
                 attendees: Optional[List[str]] = None,
                 body: Optional[str] = None) -> ApiResult:
        """
        Updates an existing event by ID.
        :param event_id: ID of the event to update
        :param subject: new subject/title
        :param start: new start datetime
        :param end: new end datetime
        :param attendees: new list of attendee emails
        :param body: new description text
        :return: True if update was successful, False otherwise
        """
        update_data = {}

        if subject is not None:
            update_data["subject"] = subject

        if start is not None:
            update_data["start"] = {"dateTime": start.isoformat(), "timeZone": "UTC"}

        if end is not None:
            update_data["end"] = {"dateTime": end.isoformat(), "timeZone": "UTC"}

        if body is not None:
            update_data["body"] = {"contentType": "HTML", "content": body}

        if attendees:
            update_data["attendees"] = [
                {"emailAddress": {"address": a, "name": a}, "type": "required"}
                for a in attendees
            ]

        try:
            if not update_data:
                raise Exception("nothing to update.")
            
            id = self._id_map.expand_id(event_id)
            if not id:
                return ApiResult.fail("Error: Unknown event_id.")

            response = self._client.patch(f"/me/events/{id}", json=update_data)
            return self.response2result(response)            
        except Exception as e:
            self.exception2result(e)

    # ----------------------------------------------------
    # Kontakte erstellen
    # ----------------------------------------------------
    def create_contact(self,
                       given_name: str,
                       surname: str,
                       email: str,
                       mobile_phone: Optional[str] = None,
                       business_phone: Optional[str] = None,
                       company_name: Optional[str] = None) -> ApiResult:
        """
        Erstellt einen neuen Kontakt im Outlook-Adressbuch.
        """
        contact_data = {
            "givenName": given_name,
            "surname": surname,
            "emailAddresses": [{"address": email}],
        }

        if mobile_phone:
            contact_data["mobilePhone"] = mobile_phone
        if business_phone:
            contact_data["businessPhones"] = [business_phone]
        if company_name:
            contact_data["companyName"] = company_name

        try:
            response = self._client.post("/me/contacts", json=contact_data)
            
            data = response.json()
            data["id"] = self._id_map.shorten_id(data.get("id"))            
            data.pop("@odata.context", None)
            data.pop("@odata.etag", None)
            data.pop("changeKey", None)

            return self.response2result(response, data=data)
        except Exception as e:
            return self.exception2result(e)    


    # ----------------------------------------------------
    # Kontakt aktualisieren
    # ----------------------------------------------------
    def update_contact(self, contact_id: str, 
                       given_name: Optional[str] = None,
                       surname: Optional[str] = None,
                       email: Optional[str] = None,
                       mobile_phone: Optional[str] = None,
                       business_phone: Optional[str] = None,
                       company_name: Optional[str] = None) -> ApiResult:
        """
        Aktualisiert einen Kontakt.
        """
        contact_data = {}

        if given_name:
            contact_data["givenName"] = given_name
        if surname:
            contact_data["surname"] = surname
        if email:
            contact_data["emailAddresses"] = [{"address": email}]
        if mobile_phone:
            contact_data["mobilePhone"] = mobile_phone
        if business_phone:
            contact_data["businessPhones"] = [business_phone]
        if company_name:
            contact_data["companyName"] = company_name

        try:
            if not contact_data:
                raise Exception("nothing to update.")

            id = self._id_map.expand_id(contact_id)
            if not id:
                return ApiResult.fail("Error: Unknown contact_id.")

            response = self._client.patch(f"/me/contacts/{id}", json=contact_data)
            return self.response2result(response)
        except Exception as e:
            return self.exception2result(e)
    
    # ----------------------------------------------------
    # Kontakt löschen
    # ----------------------------------------------------
    def delete_contact(self, contact_id: str) -> ApiResult:
        """
        Löscht einen Kontakt anhand der Contact-ID.
        """
        try:
            id = self._id_map.expand_id(contact_id)            
            response = self._client.delete(f"/me/contacts/{id}")
            return self.response2result(response)
        except Exception as e:
            return self.exception2result(e)


    # ----------------------------------------------------
    # Kontakte suchen
    # ----------------------------------------------------
    def search_contacts(self,
                        query: Optional[str] = None,
                        top: int = 10) -> ApiResult:
        """
        Sucht Kontakte nach Text (Name, Email, Firma).
        :param query: Suchtext
        :param top: Anzahl Treffer
        """
        try:
            url = f"/me/contacts?$top={top}"
            if query:
                url += f"&$search=\"{query}\""
            response = self._client.get(url)
            if not self.response_ok(response):
                return self.response2result(response)

            data = response.json()
            contacts = data.get("value", [])

            cleaned_contacts = []
            for contact in contacts:
                # Default: erste Adresse nehmen, falls gültig
                email = None
                if contact.get("emailAddresses"):
                    addr = contact["emailAddresses"][0].get("address")
                    if addr and "@" in addr:
                        email = addr

                # Falls keine gültige SMTP-Adresse: Kontakt nachladen
                if not email and contact.get("id"):
                    full_resp = self._client.get(f"/me/contacts/{contact['id']}")
                    if self.response_ok(full_resp):
                        full_contact = full_resp.json()
                        if full_contact.get("emailAddresses"):
                            addr = full_contact["emailAddresses"][0].get("address")
                            if addr and "@" in addr:
                                email = addr
                                contact["emailAddresses"] = full_contact["emailAddresses"]

                # Extra Feld setzen
                contact["email"] = email

                # IDs normalisieren
                contact["id"] = self._id_map.shorten_id(contact.get("id", None))
                contact["parentFolderId"] = self._id_map.shorten_id(contact.get("parentFolderId", None))
                contact.pop("@odata.etag", None)
                contact.pop("changeKey", None)

                cleaned_contacts.append(contact)

            return self.response2result(response, data=cleaned_contacts)

        except Exception as e:
            return self.exception2result(e)


    # ----------------------------------------------------
    # Task erstellen
    # ----------------------------------------------------
    def create_task(self,
                title: str,
                body: Optional[str] = None,
                due_date: Optional[str] = None,
                importance: Optional[str] = None,
                status: Optional[str] = None,
                list_id: str = "Tasks") -> ApiResult:
        """
        Erstellt eine neue Aufgabe in der angegebenen To-Do-Liste.
        :param subject: Titel der Aufgabe
        :param body: Beschreibung (optional)
        :param due_date: Fälligkeitsdatum im Format YYYY-MM-DD (optional)
        :param importance: Wichtigkeit ("low", "normal", "high")
        :param status: Status ("notStarted", "inProgress", "completed", "waitingOnOthers", "deferred")
        :param list_id: ID oder Name der Task-Liste (Default: "Tasks")
        """
        task_data = {"title": title}

        if body:
            task_data["body"] = {"content": body, "contentType": "text"}
        if due_date:
            # Wenn nur Datum ohne Uhrzeit
            if len(due_date) == 10:  # "YYYY-MM-DD"
                date_str = f"{due_date}T23:59:59"
            else:  # ISO mit Uhrzeit vorhanden
                date_str = due_date

            task_data["dueDateTime"] = {
                "dateTime": date_str,
                "timeZone": "UTC"
            }
        if importance in ["low", "normal", "high"]:
            task_data["importance"] = importance
        if status in ["notStarted", "inProgress", "completed", "waitingOnOthers", "deferred"]:
            task_data["status"] = status

        try:
            response = self._client.post(f"/me/todo/lists/{list_id}/tasks", json=task_data)

            data = response.json()
            data["id"] = self._id_map.shorten_id(data.get("id"))            
            data.pop("@odata.context", None)
            data.pop("@odata.etag", None)
            data.pop("changeKey", None)

            return self.response2result(response, data=data)
        except Exception as e:
            return self.exception2result(e)


    # ----------------------------------------------------
    # Task aktualisieren
    # ----------------------------------------------------
    def update_task(self,
                task_id: str,
                title: Optional[str] = None,
                body: Optional[str] = None,
                due_date: Optional[str] = None,
                status: Optional[str] = None,
                importance: Optional[str] = None,
                list_id: str = "Tasks") -> ApiResult:
        """
        Aktualisiert eine bestehende Aufgabe.
        :param task_id: ID der Aufgabe
        :param subject: Neuer Titel (optional)
        :param body: Neue Beschreibung (optional)
        :param due_date: Neues Fälligkeitsdatum (YYYY-MM-DD, optional)
        :param status: Neuer Status ("notStarted", "inProgress", "completed", "waitingOnOthers", "deferred")
        :param importance: Neue Wichtigkeit ("low", "normal", "high")
        :param list_id: ID oder Name der Task-Liste (Default: "Tasks")
        """
        task_data: dict = {}

        if title:
            task_data["title"] = title
        if body:
            task_data["body"] = {"content": body, "contentType": "text"}
        if due_date:
            # Wenn nur Datum ohne Uhrzeit
            if len(due_date) == 10:  # "YYYY-MM-DD"
                date_str = f"{due_date}T23:59:59"
            else:  # ISO mit Uhrzeit vorhanden
                date_str = due_date

            task_data["dueDateTime"] = {
                "dateTime": date_str,
                "timeZone": "UTC"
            }
        if status in ["notStarted", "inProgress", "completed", "waitingOnOthers", "deferred"]:
            task_data["status"] = status
        if importance in ["low", "normal", "high"]:
            task_data["importance"] = importance

        try:
            if not task_data:
                raise Exception("nothing to update.")

            id = self._id_map.expand_id(task_id)
            if not id:
                return ApiResult.fail("Error: Unknown task_id.")

            response = self._client.patch(
                f"/me/todo/lists/{list_id}/tasks/{id}",
                json=task_data
            )
            return self.response2result(response)
        except Exception as e:
            return self.exception2result(e)


    # ----------------------------------------------------
    # Task löschen
    # ----------------------------------------------------
    def delete_task(self, task_id: str, list_id: str = "Tasks") -> ApiResult:
        """
        Löscht eine Aufgabe anhand der Task-ID.
        """
        try:
            id = self._id_map.expand_id(task_id)
            if not id:
                return ApiResult.fail("Error: Unknown task_id.")
            
            response = self._client.delete(f"/me/todo/lists/{list_id}/tasks/{id}")
            return self.response2result(response)
        except Exception as e:
            return self.exception2result(e)    
        
    # ----------------------------------------------------
    # Tasks suchen/listen
    # ----------------------------------------------------
    def search_tasks(self,
                     query: Optional[str] = None,
                     top: int = 10,
                     list_id: str = "Tasks") -> ApiResult:
        """
        Sucht Aufgaben in einer Liste.
        :param query: Suchtext (filter auf title)
        :param top: Anzahl Treffer
        :param list_id: ID oder Name der Task-Liste (Default: "Tasks")
        """
        from urllib.parse import quote

        try:
            base_endpoint = f"/me/todo/lists/{list_id}/tasks"

            if query:
                # OData escaping für '
                q_escaped = query.replace("'", "''")
                filter_expr = f"contains(title,'{q_escaped}')"
                encoded_filter = quote(filter_expr, safe='')
                url = f"{base_endpoint}?$top={top}&$filter={encoded_filter}"
            else:
                url = f"{base_endpoint}?$top={top}"

            response = self._client.get(url)
            if not self.response_ok(response):
                return self.response2result(response)

            data = response.json()
            tasks = data.get("value", [])
            for task in tasks:
                task["id"] = self._id_map.shorten_id(task.get("id", None))
                task.pop("@odata.etag", None)

            return self.response2result(response, data=tasks)

        except Exception as e:
            return self.exception2result(e)

        
    ### UNIVERSAL QUERY FUNCTION ###

    def _escape_odata_literal(self, s: str) -> str:
        """Escape für OData Stringliterale (single quotes verdoppeln)."""
        return (s or "").replace("'", "''")

    def _iso_floor(self, date_str: str) -> str:
        """YYYY-MM-DD -> YYYY-MM-DDT00:00:00Z (oder passt durch, wenn schon ISO mit T)."""
        if not date_str:
            return None
        return date_str if "T" in date_str else f"{date_str}T00:00:00Z"

    def _iso_ceil(self, date_str: str) -> str:
        """YYYY-MM-DD -> YYYY-MM-DDT23:59:59Z (oder passt durch, wenn schon ISO mit T)."""
        if not date_str:
            return None
        return date_str if "T" in date_str else f"{date_str}T23:59:59Z"

    def _collect_paged(self, first_url: str, headers: Dict[str, str], limit: Optional[int]) -> ApiResult:
        """Folgt @odata.nextLink und sammelt bis 'limit' (None = alle)."""
        url = first_url
        out: List[Dict[str, Any]] = []

        try:
            while url:
                response = self._client.get(url, headers=headers)  # darf relative URL sein
                if not self.response_ok(response):
                    return self.response2result(response)
                data = response.json()
                items = data.get("value", [])
                out.extend(items)

                if limit is not None and len(out) >= limit:
                    # ggf. auf exakt 'limit' kürzen
                    return self.response2result(response, data=out[:limit])                    

                url = data.get("@odata.nextLink")
            return self.response2result(response, data=out)
        except Exception as e:
            return self.exception2result(e)    

    def query_emails(
        self,
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
        top: Optional[int] = 50,
    ) -> ApiResult:
        """
        Erweiterte Suche für E-Mails.
        """
        # ---- Regex check ----
        if sender_address_regex_filter:
            try:
                re.compile(sender_address_regex_filter, re.IGNORECASE)
            except re.error as e:
                return ApiResult.fail(error=f"Invalid sender regex: {str(e)}", status=0)

        if recipient_address_regex_filter:
            try:
                re.compile(recipient_address_regex_filter, re.IGNORECASE)
            except re.error as e:
                return ApiResult.fail(error=f"Invalid recipient regex: {str(e)}", status=0)

        # ---- Ordner ----
        if folder_id and not folder_id in self.WELL_KNOWN_FOLDERS:
            folder_id = self._id_map.expand_id(folder_id)

        if folder_id in (None, "", "/", "msgfolderroot"):
            base = "/me/messages"
        else:
            base = f"/me/mailFolders/{folder_id}/messages"

        # ---- $filter ----
        filter_parts = []
        if exact_sender_address:
            filter_parts.append(
                f"from/emailAddress/address eq '{self._escape_odata_literal(exact_sender_address)}'"
            )

        sd = self._iso_floor(start_date)
        ed = self._iso_ceil(end_date)
        if sd:
            filter_parts.append(f"receivedDateTime ge {sd}")
        if ed:
            filter_parts.append(f"receivedDateTime le {ed}")

        if has_attachments is not None:
            filter_parts.append(f"hasAttachments eq {'true' if has_attachments else 'false'}")

        if is_read is not None:
            filter_parts.append(f"isRead eq {'true' if is_read else 'false'}")

        # ---- $search ----
        search_terms = []

        if exact_recipient_address:
            # to: / cc: / bcc: alle durchsuchen
            addr = exact_recipient_address.replace('"', r'\"')
            search_terms.append(f"to:{addr} OR cc:{addr} OR bcc:{addr}")

        if subject_substring:
            s = subject_substring.replace('"', r'\"')
            search_terms.append(f"subject:{s}")

        if body_substring:
            b = body_substring.replace('"', r'\"')
            search_terms.append(f"body:{b}")

        kql = None
        if search_terms:
            kql = " AND ".join([f"({t})" for t in search_terms])

        # ---- URL bauen ----
        page_size = min(999, top) if (isinstance(top, int) and top > 0) else 500
        url = f"{base}?$top={int(page_size)}"

        if filter_parts:
            url += "&$filter=" + quote(" and ".join(filter_parts), safe="()' =:<>,@/")

        headers: Dict[str, str] = {}
        if kql:
            url += "&$search=" + quote(f"\"{kql}\"")
            headers["ConsistencyLevel"] = "eventual"

        # ---- Paginierte Anfrage ----
        result = self._collect_paged(url, headers, top if isinstance(top, int) and top > 0 else None)
        if not result.success:
            return result

        messages = result.data

        # ---- Clientseitige Regex-Filter ----
        def _addr_from(m: Dict[str, Any]) -> str:
            return (((m.get("from") or {}).get("emailAddress") or {}).get("address") or "")

        def _addresses_recipients(m: Dict[str, Any]) -> List[str]:
            out: List[str] = []
            for key in ("toRecipients", "ccRecipients", "bccRecipients"):
                for r in m.get(key, []) or []:
                    addr = ((r.get("emailAddress") or {}).get("address") or "")
                    if addr:
                        out.append(addr)
            return out

        if sender_address_regex_filter:
            try:
                pat = re.compile(sender_address_regex_filter, re.IGNORECASE)
                messages = [m for m in messages if pat.search(_addr_from(m))]
            except Exception as e:
                return ApiResult.fail(error=str(e), status=result.status)

        if recipient_address_regex_filter:
            try:
                pat = re.compile(recipient_address_regex_filter, re.IGNORECASE)
                messages = [m for m in messages if any(pat.search(a) for a in _addresses_recipients(m))]
            except Exception as e:
                return ApiResult.fail(error=str(e), status=result.status)

        for msg in messages:
            msg["id"] = self._id_map.shorten_id(msg.get("id", None))
            msg["parentFolderId"] = self._id_map.shorten_id(msg.get("parentFolderId", None))
            msg.pop("conversationId", None)
            msg.pop("conversationIndex", None)            
            msg.pop("internetMessageId", None)
            msg.pop("changeKey", None)
            msg.pop("@odata.etag", None)
            msg.pop("webLink", None)            

        result.data = messages
        return result
    

_auth_client: GraphAuthClient = None

# Singleton
def init_graph_client():
    global _auth_client
    _auth_client = GraphAuthClient()

def get_graph_client() -> GraphAuthClient:
    return _auth_client
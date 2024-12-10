# Copyright (c) 2024, rtCamp and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document

import google.oauth2.credentials
import googleapiclient.errors
from googleapiclient.discovery import build

from frappe.integrations.google_oauth import GoogleOAuth

from frappe import _
import requests

from frappe_gmail_thread.utils.helpers import create_new_email, find_gmail_thread

SCOPES = "https://www.googleapis.com/auth/gmail.readonly"


class GmailThread(Document):
    pass
    # def on_update(self):
    #     if self.has_value_changed("reference_doctype") or self.has_value_changed("reference_name"):
    #         for email in self.emails:
    #             communication = frappe.get_doc("Communication", email.linked_communication)
    #             communication.reference_doctype = self.reference_doctype
    #             communication.reference_name = self.reference_name
    #             communication.status = "Linked"
    #             communication.save(ignore_permissions=True)


def sync(user = None, history_id = None):
    if not user:
        user = frappe.session.user
    gmail_account = frappe.get_doc("Gmail Account", {"linked_user": user})
    if not gmail_account.gmail_enabled:
        frappe.throw(_("Please configure Gmail in Email Account."))
    if not gmail_account.refresh_token:
        frappe.throw(_("Please authorize Gmail by clicking on 'Authorize Gmail' button."))
    gmail = get_gmail_object(gmail_account.name)
    folders = ["INBOX"]  # TODO: Give option to select folders
    labels = gmail.users().labels().list(userId="me").execute()
    label_ids = []
    for folder_name in folders:
        for label in labels["labels"]:
            if label["name"] == folder_name:
                label_ids.append(label["id"])
    if not label_ids:
        return
    for label_id in label_ids:
        if not history_id:
            max_history_id = 0
            try:
                threads = gmail.users().threads().list(userId="me", labelIds=label_id).execute()
            except googleapiclient.errors.HttpError:
                continue
            for thread in threads["threads"][::-1]:
                thread_id = thread["id"]
                gmail_thread = find_gmail_thread(thread_id)
                thread = gmail.users().threads().get(userId="me", id=thread_id).execute()
                if not gmail_thread:
                    gmail_thread = frappe.new_doc("Gmail Thread")
                    gmail_thread.gmail_thread_id = thread_id
                    gmail_thread.gmail_account = gmail_account.name
                for message in thread["messages"]:
                    try:
                        raw_email = gmail.users().messages().get(userId="me", id=message["id"], format="raw").execute()
                    except googleapiclient.errors.HttpError:
                        continue
                    email = create_new_email(raw_email, gmail_account)
                    if not gmail_thread.subject_of_first_mail:
                        gmail_thread.subject_of_first_mail = email.subject
                        gmail_thread.creation = email.date_and_time
                    gmail_thread.append("emails", email)
                    if int(message["historyId"]) > max_history_id:
                        max_history_id = int(message["historyId"])
                gmail_thread.save(ignore_permissions=True)
                frappe.db.set_value("Gmail Thread", gmail_thread.name, "modified", email.date_and_time, update_modified=False)
            gmail_account.reload()
            gmail_account.last_historyid = max_history_id
            gmail_account.save(ignore_permissions=True)
            gmail_thread.notify_update()
        else:
            try:
                history = gmail.users().history().list(userId="me", startHistoryId=history_id, historyTypes="messageAdded", labelId=label_id).execute()
            except googleapiclient.errors.HttpError:
                continue
            new_history_id = int(history["historyId"])
            last_history_id = int(gmail_account.last_historyid)
            if new_history_id > last_history_id:
                history = gmail.users().history().list(userId="me", startHistoryId=last_history_id, historyTypes="messageAdded", labelId=label_id).execute()
                if 'history' not in history:
                    return
                for history in history["history"]:
                    for message in history["messages"]:
                        try:
                            raw_email = gmail.users().messages().get(userId="me", id=message["id"], format="raw").execute()
                        except googleapiclient.errors.HttpError:
                            continue
                        thread_id = message["threadId"]
                        gmail_thread = find_gmail_thread(thread_id)
                        if not gmail_thread:
                            gmail_thread = frappe.new_doc("Gmail Thread")
                            gmail_thread.gmail_thread_id = thread_id
                            gmail_thread.gmail_account = gmail_account.name
                        email = create_new_email(raw_email, gmail_account)
                        if not gmail_thread.subject_of_first_mail:
                            gmail_thread.subject_of_first_mail = email.subject
                            gmail_thread.creation = email.date_and_time
                        gmail_thread.append("emails", email)
                        gmail_thread.save(ignore_permissions=True)
                        frappe.db.set_value("Gmail Thread", gmail_thread.name, "modified", email.date_and_time, update_modified=False)
                    
                gmail_account.reload()
                gmail_account.last_historyid = new_history_id
                gmail_account.save(ignore_permissions=True)
                gmail_thread.notify_update()



def enable_pubsub(gmail_account):
    google_settings = frappe.get_single("Google Settings")
    if not gmail_account.gmail_enabled or not google_settings.custom_gmail_sync_in_realtime:
        return False
    if not gmail_account.refresh_token:
        frappe.throw(_("Please authorize Gmail by clicking on 'Authorize Gmail' button."))
    if not google_settings.custom_gmail_pubsub_topic:
        frappe.throw(_("Please configure PubSub in Google Settings."))
    gmail = get_gmail_object(gmail_account.name)
    topic = google_settings.custom_gmail_pubsub_topic
    folders = ["INBOX"]  # TODO: Give option to select folders, reference: sync function in this file
    labels = gmail.users().labels().list(userId="me").execute()
    label_ids = []
    for folder_name in folders:
        for label in labels["labels"]:
            if label["name"] == folder_name:
                label_ids.append(label["id"])
    if not label_ids:
        label_ids = ["INBOX"]
    if "SENT" not in label_ids:
        label_ids.append("SENT")
    body = {
        "labelIds": label_ids,
        "topicName": topic,
        "labelFilterBehavior": "include",
    }
    gmail.users().watch(userId="me", body=body).execute()
    print("PubSub enabled")
    
def disable_pubsub(gmail_account):
    google_settings = frappe.get_single("Google Settings")
    if not gmail_account.gmail_enabled or google_settings.custom_gmail_sync_in_realtime:
        return False
    if not gmail_account.refresh_token:
        frappe.throw(_("Please authorize Gmail by clicking on 'Authorize Gmail' button."))
    if not google_settings.custom_gmail_pubsub_topic:
        frappe.throw(_("Please configure PubSub in Email Account."))
    gmail = get_gmail_object(gmail_account.name)
    gmail.users().stop(userId="me").execute()

def get_access_token(gmail_account_name):
    google_settings = frappe.get_single("Google Settings")
    gmail_account = frappe.get_doc("Gmail Account", gmail_account_name)

    if not gmail_account.refresh_token:
        button_label = frappe.bold(_("Authorize Gmail"))
        raise frappe.ValidationError(_("Click on {0} in Gmail Account to generate Refresh Token.").format(button_label))

    data = {
        "client_id": google_settings.client_id,
        "client_secret": google_settings.get_password(fieldname="client_secret", raise_exception=False),
        "refresh_token": gmail_account.get_password(fieldname="refresh_token", raise_exception=False),
        "grant_type": "refresh_token",
        "scope": SCOPES,
    }

    try:
        r = requests.post(GoogleOAuth.OAUTH_URL, data=data).json()
    except requests.exceptions.HTTPError:
        button_label = frappe.bold(_("Authorize Gmail"))
        frappe.throw(
            _(
                "Something went wrong during the token generation. Click on {0} in Gmail Account to generate Refresh Token."
            ).format(button_label)
        )

    return r.get("access_token")


def get_gmail_object(gmail_account_name):
    """
    Returns an object of Google Mail along with Google Mail doc.
    """
    google_settings = frappe.get_doc("Google Settings")
    account = frappe.get_doc("Gmail Account", gmail_account_name)

    credentials_dict = {
        "token": get_access_token(gmail_account_name),
        "refresh_token": account.get_password(fieldname="refresh_token", raise_exception=False),
        "token_uri": GoogleOAuth.OAUTH_URL,
        "client_id": google_settings.client_id,
        "client_secret": google_settings.get_password(fieldname="client_secret", raise_exception=False),
        "scopes": [SCOPES],
    }

    credentials = google.oauth2.credentials.Credentials(**credentials_dict)
    gmail = build(
        serviceName="gmail", version="v1", credentials=credentials
    )

    check_gmail_object(account, gmail)

    return gmail


def check_gmail_object(account, gmail):
    try:
        gmail.users().getProfile(userId="me").execute()
    except Exception as e:
        if "invalid_grant" in str(e):
            button_label = frappe.bold(_("Authorize Gmail"))
            frappe.throw(
                _(
                    "Your Gmail authorization has expired. Click on {0} in Email Account to re-authorize."
                ).format(button_label)
            )
        else:
            frappe.throw(_("Something went wrong during the token generation."))
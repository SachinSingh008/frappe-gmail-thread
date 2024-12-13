# Copyright (c) 2024, rtCamp and contributors
# For license information, please see license.txt

import json
import frappe
from frappe.model.document import Document

import google.oauth2.credentials
import googleapiclient.errors
from googleapiclient.discovery import build

from frappe.integrations.google_oauth import GoogleOAuth

from frappe_gmail_thread.api.oauth import get_gmail_object

from frappe import _
import requests

from frappe_gmail_thread.utils.helpers import create_new_email, find_gmail_thread

SCOPES = "https://www.googleapis.com/auth/gmail.readonly"


class GmailThread(Document):
    pass


@frappe.whitelist()
def sync_labels(account_name):
    gmail = get_gmail_object(account_name)
    labels = gmail.users().labels().list(userId="me").execute()
    
    gmail_account = frappe.get_doc("Gmail Account", account_name)
    available_labels = [x.label_id for x in gmail_account.labels]
    
    for label in labels["labels"]:
        if label["name"] == "DRAFT":
            continue
        if label["id"] in available_labels:
            continue
        gmail_account.append("labels", {
            "label_id": label["id"],
            "label_name": label["name"]
        })
    gmail_account.save(ignore_permissions=True)
    frappe.db.commit()


def sync(user = None, history_id = None):
    if user:
        frappe.set_user(user)
    user = frappe.session.user
    gmail_account = frappe.get_doc("Gmail Account", {"linked_user": user})
    if not gmail_account.gmail_enabled:
        frappe.throw(_("Please configure Gmail in Email Account."))
    if not gmail_account.refresh_token:
        frappe.throw(_("Please authorize Gmail by clicking on 'Authorize Gmail' button."))
    gmail = get_gmail_object(gmail_account.name)
    label_ids = [x.label_id for x in gmail_account.labels if x.enabled]
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
                    email = create_new_email(raw_email, gmail_account, gmail_thread)
                    if not gmail_thread.subject_of_first_mail:
                        gmail_thread.subject_of_first_mail = email.subject
                        gmail_thread.creation = email.date_and_time
                    gmail_thread.append("emails", email)
                    if int(message["historyId"]) > max_history_id:
                        max_history_id = int(message["historyId"])
                gmail_thread.save(ignore_permissions=True)
                frappe.db.set_value("Gmail Thread", gmail_thread.name, "modified", email.date_and_time, update_modified=False)
                # set owner to linked user
                frappe.db.set_value("Gmail Thread", gmail_thread.name, "owner", gmail_account.linked_user, modified_by=gmail_account.linked_user, update_modified=False)
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
                        email = create_new_email(raw_email, gmail_account, gmail_thread)
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
                # if gmail thread has a reference doctype and name, then publish real-time activity
                if gmail_thread.reference_doctype and gmail_thread.reference_name:
                    frappe.publish_realtime("gthread_new_email", doctype=gmail_thread.reference_doctype, docname=gmail_thread.reference_name)


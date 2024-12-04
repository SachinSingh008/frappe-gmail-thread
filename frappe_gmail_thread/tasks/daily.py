import frappe
from frappe_gmail_thread.frappe_gmail_thread.doctype.gmail_thread.gmail_thread import enable_pubsub

def enable_pubsub_everyday():
    email_accounts = frappe.get_all("Email Account", filters={"custom_gmail_enabled": 1, "custom_gmail_sync_in_realtime": 1}, fields=["*"])
    for email_account in email_accounts:
        enable_pubsub(email_account)
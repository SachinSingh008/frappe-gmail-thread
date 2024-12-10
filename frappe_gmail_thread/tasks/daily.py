import frappe
from frappe_gmail_thread.frappe_gmail_thread.doctype.gmail_thread.gmail_thread import enable_pubsub
from frappe import _

def enable_pubsub_everyday():
    google_settings = frappe.get_single("Google Settings")
    if not google_settings.enable:
        return
    if not google_settings.custom_gmail_sync_in_realtime or not google_settings.custom_gmail_pubsub_topic:
        return

    gmail_accounts = frappe.get_all("Gmail Account", filters={"gmail_enabled": 1}, fields=["*"])
    for gmail_account in gmail_accounts:
        enable_pubsub(gmail_account)
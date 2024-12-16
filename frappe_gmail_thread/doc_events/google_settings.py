import frappe
from frappe import _

from frappe_gmail_thread.api.oauth import disable_pubsub, enable_pubsub


def on_update(doc, method=None):
    if doc.has_value_changed("custom_gmail_sync_in_realtime"):
        return  # TODO: Fix it for all accounts.
        if doc.custom_gmail_sync_in_realtime:
            # start pubsub
            enable_pubsub(doc)
            frappe.msgprint(_("Enabled Realtime Sync for {0}").format(doc.email_id))
        else:
            # stop pubsub
            disable_pubsub(doc)
            frappe.msgprint(_("Disabled Realtime Sync for {0}").format(doc.email_id))

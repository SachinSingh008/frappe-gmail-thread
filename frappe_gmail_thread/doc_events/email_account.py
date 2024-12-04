import frappe
from frappe import _
from frappe_gmail_thread.frappe_gmail_thread.doctype.gmail_thread.gmail_thread import disable_pubsub, enable_pubsub

# override validate method of Email Account to check if Client ID and Client Secret are set in Google Settings when custom_gmail_enabled is set in Email Account
def validate(doc, method = None):
    if doc.custom_gmail_enabled:
        google_settings = frappe.get_single("Google Settings")
        if not google_settings.enable:
            frappe.throw(_("Enable Google API in Google Settings."))
        if not google_settings.client_id or not google_settings.get_password(fieldname="client_secret", raise_exception=False):
            frappe.throw(_("Please set Client ID and Client Secret in Google Settings to enable Gmail"))
        if not doc.custom_gmail_refresh_token:
            frappe.throw(_("Please authorize Gmail by clicking on 'Authorize Gmail' button."))
            

def on_update(doc, method = None):
    if doc.has_value_changed("custom_gmail_enabled"):
        if doc.custom_gmail_enabled:
            if not doc.custom_gmail_refresh_token:
                frappe.throw(_("Please authorize Gmail by clicking on 'Authorize Gmail' button."))
            else:
                frappe.enqueue(
                    "frappe_gmail_thread.frappe_gmail_thread.doctype.gmail_thread.gmail_thread.sync",
                    email=doc.email_id,
                    queue="long",
                    enqueue_after_commit=True,
                )
    if doc.has_value_changed("custom_gmail_sync_in_realtime"):
        if doc.custom_gmail_sync_in_realtime:
            # start pubsub
            enable_pubsub(doc)
            frappe.msgprint(_("Enabled Realtime Sync for {0}").format(doc.email_id))
        else:
            # stop pubsub
            disable_pubsub(doc)
            frappe.msgprint(_("Disabled Realtime Sync for {0}").format(doc.email_id))
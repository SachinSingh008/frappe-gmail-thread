# Copyright (c) 2024, rtCamp and contributors
# For license information, please see license.txt

# import frappe
from frappe.model.document import Document
import frappe
from frappe import _
from frappe_gmail_thread.frappe_gmail_thread.doctype.gmail_thread.gmail_thread import disable_pubsub, enable_pubsub


class GmailAccount(Document):
    def before_insert(self):
        self.linked_user = frappe.session.user

    def validate(self):
        if self.gmail_enabled:
            google_settings = frappe.get_single("Google Settings")
            if not google_settings.enable:
                frappe.throw(_("Enable Google API in Google Settings."))
            if not google_settings.client_id or not google_settings.get_password(fieldname="client_secret", raise_exception=False):
                frappe.throw(_("Please set Client ID and Client Secret in Google Settings to enable Gmail"))
    
    def on_update(self):
        if self.has_value_changed("gmail_enabled") and self.gmail_enabled:
            google_settings = frappe.get_single("Google Settings")
            if not google_settings.enable:
                frappe.throw(_("Enable Google API in Google Settings."))
            if not google_settings.client_id or not google_settings.get_password(fieldname="client_secret", raise_exception=False):
                frappe.throw(_("Please set Client ID and Client Secret in Google Settings to enable Gmail"))
        if self.has_value_changed("refresh_token") and self.refresh_token and self.linked_user == frappe.session.user:
            # check if old value of refresh token is empty
            if not self.get_doc_before_save().refresh_token:
                google_settings = frappe.get_single("Google Settings")
                if google_settings.custom_gmail_sync_in_realtime and google_settings.custom_gmail_pubsub_topic:
                    if self.gmail_enabled:
                        # start pubsub
                        enable_pubsub(self)
                        frappe.msgprint(_("Enabled Realtime Sync for {0}").format(self.linked_user))
                    else:
                        # stop pubsub
                        disable_pubsub(self)
                        frappe.msgprint(_("Disabled Realtime Sync for {0}").format(self.linked_user))
                frappe.enqueue(
                    "frappe_gmail_thread.frappe_gmail_thread.doctype.gmail_thread.gmail_thread.sync",
                    user=self.linked_user,
                    queue="long",
                )
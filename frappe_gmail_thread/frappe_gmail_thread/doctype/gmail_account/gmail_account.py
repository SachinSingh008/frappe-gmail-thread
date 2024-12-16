# Copyright (c) 2024, rtCamp and contributors
# For license information, please see license.txt

# import frappe
import frappe
from frappe import _
from frappe.model.document import Document

from frappe_gmail_thread.api.oauth import disable_pubsub, enable_pubsub
from frappe_gmail_thread.frappe_gmail_thread.doctype.gmail_thread.gmail_thread import (
    sync_labels,
)


class GmailAccount(Document):
    def before_insert(self):
        self.linked_user = frappe.session.user

    def validate(self):
        if self.gmail_enabled:
            google_settings = frappe.get_single("Google Settings")
            if not google_settings.enable:
                frappe.throw(_("Enable Google API in Google Settings."))
            if not google_settings.client_id or not google_settings.get_password(
                fieldname="client_secret", raise_exception=False
            ):
                frappe.throw(
                    _(
                        "Please set Client ID and Client Secret in Google Settings to enable Gmail"
                    )
                )

    def on_update(self):
        if self.linked_user != frappe.session.user:
            return
        if self.has_value_changed("gmail_enabled") and self.gmail_enabled:
            google_settings = frappe.get_single("Google Settings")
            if not google_settings.enable:
                frappe.throw(_("Enable Google API in Google Settings."))
            if not google_settings.client_id or not google_settings.get_password(
                fieldname="client_secret", raise_exception=False
            ):
                frappe.throw(
                    _(
                        "Please set Client ID and Client Secret in Google Settings to enable Gmail"
                    )
                )
        if self.has_value_changed("refresh_token") and self.refresh_token:
            sync_labels(self.name)
            if not self.get_doc_before_save().refresh_token:
                google_settings = frappe.get_single("Google Settings")
                if (
                    google_settings.custom_gmail_sync_in_realtime
                    and google_settings.custom_gmail_pubsub_topic
                ):
                    if self.gmail_enabled:
                        # start pubsub
                        enable_pubsub(self)
                        frappe.msgprint(
                            _("Enabled Realtime Sync for {0}").format(self.linked_user)
                        )
                    else:
                        # stop pubsub
                        disable_pubsub(self)
                        frappe.msgprint(
                            _("Disabled Realtime Sync for {0}").format(self.linked_user)
                        )
        if self.has_value_changed("labels") and not self.has_value_changed(
            "last_historyid"
        ):
            if (
                self.gmail_enabled
                and self.refresh_token
                and not self.has_value_changed("refresh_token")
            ):
                has_labels = False
                for label in self.labels:
                    if label.enabled:
                        has_labels = True
                        break
                if has_labels:
                    enable_pubsub(self)
                    frappe.enqueue(
                        "frappe_gmail_thread.frappe_gmail_thread.doctype.gmail_thread.gmail_thread.sync",
                        user=self.linked_user,
                        queue="long",
                    )
                else:
                    frappe.msgprint(_("Please select at least one label."))

# Copyright (c) 2024, rtCamp and contributors
# For license information, please see license.txt


import frappe
import frappe.share
import googleapiclient.errors
from frappe import _
from frappe.model.document import Document
from frappe.utils import get_string_between

from frappe_gmail_thread.api.oauth import get_gmail_object
from frappe_gmail_thread.utils.helpers import (
    AlreadyExistsError,
    create_new_email,
    find_gmail_thread,
    process_attachments,
    replace_inline_images,
)

SCOPES = "https://www.googleapis.com/auth/gmail.readonly"


class GmailThread(Document):
    def has_value_changed(self, fieldname):
        # check if fieldname is child table
        if fieldname in ["involved_users"]:
            old_value = self.get_doc_before_save()
            if old_value:
                old_value = old_value.get(fieldname)
            new_value = self.get(fieldname)
            if old_value and new_value:
                if len(old_value) != len(new_value):
                    return True
                old_names = [d.name for d in old_value]
                new_names = [d.name for d in new_value]
                if set(old_names) != set(new_names):
                    return True
                return False
            if not old_value and not new_value:
                return False
            return True
        return super().has_value_changed(fieldname)

    def on_update(self):
        if self.has_value_changed("involved_users"):
            # give permission of all files to all involved users
            attachments = frappe.get_all(
                "File",
                filters={
                    "attached_to_doctype": "Gmail Thread",
                    "attached_to_name": self.name,
                },
                fields=["name"],
            )
            for attachment in attachments:
                for user in self.involved_users:
                    if user.account == self.owner:
                        continue
                    frappe.share.add_docshare(
                        "File",
                        attachment.name,
                        user.account,
                        flags={"ignore_share_permission": True},
                    )
        if self.has_value_changed("reference_doctype") and self.has_value_changed(
            "reference_name"
        ):
            if self.reference_doctype and self.reference_name:
                if self.status == "Open":
                    self.status = "Linked"
                    self.save(ignore_permissions=True)
                # check if there is any other thread with same reference doctype and name
                threads = frappe.get_all(
                    "Gmail Thread",
                    filters={
                        "reference_doctype": self.reference_doctype,
                        "reference_name": self.reference_name,
                    },
                    fields=["name"],
                )
                for thread in threads:
                    if thread.name != self.name:
                        frappe.msgprint(
                            _(
                                "The document is already linked with another Gmail Thread. This may cause confusion in the document timeline."
                            )
                        )
                        break


@frappe.whitelist(methods=["POST"])
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
        gmail_account.append(
            "labels", {"label_id": label["id"], "label_name": label["name"]}
        )
    gmail_account.save(ignore_permissions=True)


def sync(user=None, history_id=None):
    if user:
        frappe.set_user(user)
    user = frappe.session.user
    gmail_account = frappe.get_doc("Gmail Account", {"linked_user": user})
    if not gmail_account.gmail_enabled:
        frappe.throw(_("Please configure Gmail in Email Account."))
    if not gmail_account.refresh_token:
        frappe.throw(
            _("Please authorize Gmail by clicking on 'Authorize Gmail' button.")
        )
    gmail = get_gmail_object(gmail_account.name)
    label_ids = [x.label_id for x in gmail_account.labels if x.enabled]
    if not label_ids:
        return
    last_history_id = int(gmail_account.last_historyid)
    for label_id in label_ids:
        if not last_history_id:
            max_history_id = 0
            try:
                threads = (
                    gmail.users()
                    .threads()
                    .list(userId="me", labelIds=label_id)
                    .execute()
                )
            except googleapiclient.errors.HttpError:
                continue
            if "threads" not in threads:
                continue
            for thread in threads["threads"][::-1]:
                thread_id = thread["id"]
                thread = (
                    gmail.users().threads().get(userId="me", id=thread_id).execute()
                )
                gmail_thread = find_gmail_thread(thread_id)
                involved_users = set()
                for message in thread["messages"]:
                    try:
                        raw_email = (
                            gmail.users()
                            .messages()
                            .get(userId="me", id=message["id"], format="raw")
                            .execute()
                        )
                    except googleapiclient.errors.HttpError:
                        continue
                    try:
                        email, email_object = create_new_email(raw_email, gmail_account)
                    except AlreadyExistsError:
                        continue
                    if not gmail_thread:
                        email_message_id = email_object.message_id
                        email_references = email_object.mail.get("References")
                        if email_references:
                            email_references = [
                                get_string_between("<", x, ">")
                                for x in email_references.split()
                            ]
                        else:
                            email_references = []
                        gmail_thread = find_gmail_thread(
                            thread_id, [email_message_id] + email_references
                        )
                    if not gmail_thread:
                        gmail_thread = frappe.new_doc("Gmail Thread")
                        gmail_thread.gmail_thread_id = thread_id
                        gmail_thread.gmail_account = gmail_account.name
                    if not gmail_thread.subject_of_first_mail:
                        gmail_thread.subject_of_first_mail = email.subject
                        gmail_thread.creation = email.date_and_time
                    involved_users.add(email_object.from_email)
                    for recipient in email_object.to:
                        involved_users.add(recipient)
                    for recipient in email_object.cc:
                        involved_users.add(recipient)
                    for recipient in email_object.bcc:
                        involved_users.add(recipient)
                    update_involved_users(gmail_thread, involved_users)
                    process_attachments(email, gmail_thread, email_object)
                    replace_inline_images(email, email_object)
                    gmail_thread.append("emails", email)
                    if int(message["historyId"]) > max_history_id:
                        max_history_id = int(message["historyId"])
                gmail_thread.save(ignore_permissions=True)
                frappe.db.set_value(
                    "Gmail Thread",
                    gmail_thread.name,
                    "modified",
                    email.date_and_time,
                    update_modified=False,
                )
                # set owner to linked user
                frappe.db.set_value(
                    "Gmail Thread",
                    gmail_thread.name,
                    "owner",
                    gmail_account.linked_user,
                    modified_by=gmail_account.linked_user,
                    update_modified=False,
                )
            gmail_account.reload()
            gmail_account.last_historyid = max_history_id
            gmail_account.save(ignore_permissions=True)
            gmail_thread.notify_update()
        else:
            try:
                history = (
                    gmail.users()
                    .history()
                    .list(
                        userId="me",
                        startHistoryId=history_id,
                        historyTypes=["messageAdded", "labelAdded"],
                        labelId=label_id,
                    )
                    .execute()
                )
            except googleapiclient.errors.HttpError:
                continue
            new_history_id = int(history["historyId"])
            if new_history_id > last_history_id:
                history = (
                    gmail.users()
                    .history()
                    .list(
                        userId="me",
                        startHistoryId=last_history_id,
                        historyTypes=["messageAdded", "labelAdded"],
                        labelId=label_id,
                    )
                    .execute()
                )
                if "history" not in history:
                    return
                for history in history["history"]:
                    for message in history["messages"]:
                        try:
                            raw_email = (
                                gmail.users()
                                .messages()
                                .get(userId="me", id=message["id"], format="raw")
                                .execute()
                            )
                        except googleapiclient.errors.HttpError:
                            continue
                        thread_id = message["threadId"]
                        gmail_thread = find_gmail_thread(thread_id)
                        involved_users = set()
                        try:
                            email, email_object = create_new_email(
                                raw_email, gmail_account
                            )
                        except AlreadyExistsError:
                            continue
                        if not gmail_thread:
                            email_message_id = email_object.message_id
                            email_references = email_object.mail.get("References")
                            if email_references:
                                email_references = [
                                    get_string_between("<", x, ">")
                                    for x in email_references.split()
                                ]
                            else:
                                email_references = []
                            gmail_thread = find_gmail_thread(
                                thread_id, [email_message_id] + email_references
                            )
                        if not gmail_thread:
                            gmail_thread = frappe.new_doc("Gmail Thread")
                            gmail_thread.gmail_thread_id = thread_id
                            gmail_thread.gmail_account = gmail_account.name
                        if not gmail_thread.subject_of_first_mail:
                            gmail_thread.subject_of_first_mail = email.subject
                            gmail_thread.creation = email.date_and_time
                        involved_users.add(email_object.from_email)
                        process_attachments(email, gmail_thread, email_object)
                        replace_inline_images(email, email_object)
                        for recipient in email_object.to:
                            involved_users.add(recipient)
                        for recipient in email_object.cc:
                            involved_users.add(recipient)
                        for recipient in email_object.bcc:
                            involved_users.add(recipient)
                        update_involved_users(gmail_thread, involved_users)
                        gmail_thread.append("emails", email)
                        gmail_thread.save(ignore_permissions=True)
                        frappe.db.set_value(
                            "Gmail Thread",
                            gmail_thread.name,
                            "modified",
                            email.date_and_time,
                            update_modified=False,
                        )

                gmail_account.reload()
                gmail_account.last_historyid = new_history_id
                gmail_account.save(ignore_permissions=True)
                gmail_thread.notify_update()
                # if gmail thread has a reference doctype and name, then publish real-time activity
                if gmail_thread.reference_doctype and gmail_thread.reference_name:
                    frappe.publish_realtime(
                        "gthread_new_email",
                        doctype=gmail_thread.reference_doctype,
                        docname=gmail_thread.reference_name,
                    )


def update_involved_users(doc, involved_users):
    involved_users = list(involved_users)
    involved_users_linked = [x.account for x in doc.involved_users]
    all_users = frappe.get_all(
        "User",
        filters={"email": ["in", involved_users], "user_type": ["!=", "Website User"]},
        fields=["name"],
    )
    for user in all_users:
        if user.name not in involved_users_linked:
            involved_user = frappe.get_doc(doctype="Involved User", account=user.name)
            doc.append("involved_users", involved_user)


def get_permission_query_conditions(user):
    if not user:
        user = frappe.session.user
    if user == "Administrator":
        return ""
    return """
        `tabGmail Thread`.name in (
            select parent from `tabInvolved User`
            where account = {user}
        ) or `tabGmail Thread`.owner = {user}
    """.format(user=frappe.db.escape(user))


def has_permission(doc, ptype, user):
    if user == "Administrator":
        return True
    if ptype in ("read", "write", "delete", "create"):
        return frappe.db.exists(
            "Involved User",
            {"parent": doc.name, "account": user},
        )
    return False

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
from googleapiclient.http import BatchHttpRequest
from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any
import time

logger = frappe.logger("gmail_sync")

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

    def before_save(self):
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
            elif self.status == "Linked":
                self.status = "Open"


@frappe.whitelist(methods=["POST"])
def sync_labels(account_name, should_save=True):
    if isinstance(account_name, str):
        gmail_account = frappe.get_doc("Gmail Account", account_name)
    else:
        gmail_account = account_name

    gmail = get_gmail_object(gmail_account)
    labels = gmail.users().labels().list(userId="me").execute()

    available_labels = [x.label_id for x in gmail_account.labels]

    for label in labels["labels"]:
        if label["name"] in ["DRAFT", "CHAT"]:
            continue
        if label["id"] in available_labels:
            continue
        gmail_account.append(
            "labels", {"label_id": label["id"], "label_name": label["name"]}
        )
    if should_save:
        gmail_account.save(ignore_permissions=True)


def _get_google_settings():
    try:
        return frappe.get_single("Google Settings")
    except Exception:
        return None


def _get_retry_after_key(gmail_account_name: str) -> str:
    return f"gmail_retry_after_until:{gmail_account_name}"


def _get_wait_seconds_if_rate_limited(gmail_account_name: str) -> int:
    cache = frappe.cache()
    retry_until = cache.get_value(_get_retry_after_key(gmail_account_name))
    if not retry_until:
        return 0
    try:
        retry_until_dt = datetime.fromisoformat(retry_until)
    except Exception:
        return 0
    now = datetime.now(timezone.utc)
    if retry_until_dt > now:
        return int((retry_until_dt - now).total_seconds())
    return 0


def _set_rate_limit_until(gmail_account_name: str, seconds: int) -> None:
    until = datetime.now(timezone.utc) + timedelta(seconds=max(1, int(seconds)))
    frappe.cache().set_value(_get_retry_after_key(gmail_account_name), until.isoformat())


def _chunk_list(items: List[Any], chunk_size: int) -> List[List[Any]]:
    if chunk_size <= 0:
        return [items]
    return [items[i : i + chunk_size] for i in range(0, len(items), chunk_size)]


def _batch_fetch_threads(gmail, thread_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    threads_data: Dict[str, Dict[str, Any]] = {}
    errors: Dict[str, Exception] = {}

    def thread_callback(request_id, response, exception):
        if exception is not None:
            errors[request_id] = exception
            return
        threads_data[request_id] = response

    batch = BatchHttpRequest(callback=thread_callback)
    for tid in thread_ids:
        req = gmail.users().threads().get(userId="me", id=tid)
        batch.add(req, request_id=tid)
    try:
        batch.execute()
    except googleapiclient.errors.HttpError as e:
        # Handle top-level batch failures (e.g. 429)
        raise e
    # Best-effort: ignore per-item notFound errors
    return threads_data


def _batch_fetch_raw_messages(gmail, message_ids: List[str]) -> Dict[str, Dict[str, Any]]:
    messages_data: Dict[str, Dict[str, Any]] = {}
    errors: Dict[str, Exception] = {}

    def msg_callback(request_id, response, exception):
        if exception is not None:
            errors[request_id] = exception
            return
        messages_data[request_id] = response

    batch = BatchHttpRequest(callback=msg_callback)
    for mid in message_ids:
        req = gmail.users().messages().get(userId="me", id=mid, format="raw")
        batch.add(req, request_id=mid)
    batch.execute()
    return messages_data


def _process_threads_batch(gmail_account, gmail, thread_ids: List[str]):
    # Check if we should delay due to rate limit
    wait_s = _get_wait_seconds_if_rate_limited(gmail_account.name)
    if wait_s > 0:
        # Skip processing now; cron will pick it up later
        return

    try:
        threads_map = _batch_fetch_threads(gmail, thread_ids)
    except googleapiclient.errors.HttpError as e:
        status = getattr(getattr(e, "resp", None), "status", None)
        if status == 429:
            retry_after = getattr(e, "resp", {}).get("retry-after") if hasattr(e, "resp") else None
            retry_after_seconds = int(retry_after) if retry_after and str(retry_after).isdigit() else 60
            _set_rate_limit_until(gmail_account.name, retry_after_seconds)
            return
        raise

    # Collect all message ids from all threads in this batch
    message_ids: List[str] = []
    thread_id_to_message_ids: Dict[str, List[str]] = {}
    for tid, thread_data in threads_map.items():
        mids = [m.get("id") for m in thread_data.get("messages", []) if m.get("id")]
        if mids:
            thread_id_to_message_ids[tid] = mids
            message_ids.extend(mids)

    # Fetch all messages in batch (may be large; split into sub-batches of 50)
    for mids_chunk in _chunk_list(message_ids, 50):
        try:
            messages_map = _batch_fetch_raw_messages(gmail, mids_chunk)
        except googleapiclient.errors.HttpError as e:
            status = getattr(getattr(e, "resp", None), "status", None)
            if status == 429:
                retry_after = getattr(e, "resp", {}).get("retry-after") if hasattr(e, "resp") else None
                retry_after_seconds = int(retry_after) if retry_after and str(retry_after).isdigit() else 60
                _set_rate_limit_until(gmail_account.name, retry_after_seconds)
                return
            raise

        # Process messages, building/augmenting threads
        processed_threads: Dict[str, Dict[str, Any]] = {}
        for tid, mids in thread_id_to_message_ids.items():
            for mid in mids:
                raw_email = messages_map.get(mid)
                if not raw_email:
                    continue
                if "DRAFT" in raw_email.get("labelIds", []):
                    continue
                gmail_thread = find_gmail_thread(tid)
                involved_users = set()
                is_new_thread = False
                try:
                    email, email_object = create_new_email(raw_email, gmail_account)
                except AlreadyExistsError:
                    continue
                if not gmail_thread:
                    email_message_id = email_object.message_id
                    email_references = email_object.mail.get("References")
                    if email_references:
                        email_references = [
                            get_string_between("<", x, ">") for x in email_references.split()
                        ]
                    else:
                        email_references = []
                    gmail_thread = find_gmail_thread(tid, [email_message_id] + email_references)
                if gmail_thread:
                    gmail_thread.reload()
                else:
                    gmail_thread = frappe.new_doc("Gmail Thread")
                    gmail_thread.gmail_thread_id = tid
                    gmail_thread.gmail_account = gmail_account.name
                    is_new_thread = True
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
                involved_users.add(gmail_account.linked_user)
                update_involved_users(gmail_thread, involved_users)
                process_attachments(email, gmail_thread, email_object)
                replace_inline_images(email, email_object)
                gmail_thread.append("emails", email)
                gmail_thread.save(ignore_permissions=True)
                frappe.db.commit()  # nosemgrep
                frappe.db.set_value(
                    "Gmail Thread",
                    gmail_thread.name,
                    "modified",
                    email.date_and_time,
                    update_modified=False,
                )
                if is_new_thread:  # update creation date
                    frappe.db.set_value(
                        "Gmail Thread",
                        gmail_thread.name,
                        "creation",
                        email.date_and_time,
                        update_modified=False,
                    )
                frappe.db.set_value(
                    "Gmail Thread",
                    gmail_thread.name,
                    "owner",
                    gmail_account.linked_user,
                    modified_by=gmail_account.linked_user,
                    update_modified=False,
                )


@frappe.whitelist()  # nosemgrep
def process_thread_batch(user: str, label_id: str, thread_ids: List[str]):
    if user:
        frappe.set_user(user)
    gmail_account = frappe.get_doc("Gmail Account", {"linked_user": user})
    gmail = get_gmail_object(gmail_account)
    _process_threads_batch(gmail_account, gmail, thread_ids)


def sync(user=None):
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
    gmail = get_gmail_object(gmail_account)
    label_ids = [x.label_id for x in gmail_account.labels if x.enabled]
    if not label_ids:
        return

    # Always store the maximum history id seen, to avoid skipping emails
    last_history_id = int(gmail_account.last_historyid or 0)
    max_history_id = last_history_id

    google_settings = _get_google_settings()
    max_threads_per_label = 0
    batch_size = 0
    batch_jobs = False
    if google_settings:
        try:
            max_threads_per_label = int(getattr(google_settings, "custom_gmail_max_threads_per_label", 0) or 0)
        except Exception:
            max_threads_per_label = 0
        try:
            batch_size = int(getattr(google_settings, "custom_gmail_batch_size", 0) or 0)
        except Exception:
            batch_size = 0
        batch_jobs = bool(getattr(google_settings, "custom_gmail_batch_jobs", 0))

    for label_id in label_ids:
        try:
            if not last_history_id:
                # Initial sync: fetch all threads for the label
                threads = (
                    gmail.users()
                    .threads()
                    .list(userId="me", labelIds=label_id)
                    .execute()
                )
                if "threads" not in threads:
                    continue
                # Apply limit if configured
                thread_list = threads["threads"][::-1]
                if max_threads_per_label > 0:
                    thread_list = thread_list[:max_threads_per_label]

                # If batching is enabled, process in chunks, possibly enqueuing as separate jobs
                if batch_size and batch_size > 0:
                    thread_id_chunks = _chunk_list([t["id"] for t in thread_list], batch_size)
                    for chunk in thread_id_chunks:
                        if batch_jobs:
                            job_name = f"gmail_thread_batch_{user}_{label_id}_{chunk[0]}"
                            frappe.enqueue(
                                "frappe_gmail_thread.frappe_gmail_thread.doctype.gmail_thread.gmail_thread.process_thread_batch",
                                user=user,
                                label_id=label_id,
                                thread_ids=chunk,
                                queue="long",
                                job_name=job_name,
                                job_id=job_name,
                            )
                        else:
                            _process_threads_batch(gmail_account, gmail, chunk)
                    # Continue to next label after enqueuing/processing batches
                    gmail_account.reload()
                    gmail_account.last_historyid = max_history_id
                    gmail_account.save(ignore_permissions=True)
                    frappe.db.commit()  # nosemgrep
                    continue

                for thread in thread_list:
                    thread_id = thread["id"]
                    thread_data = (
                        gmail.users().threads().get(userId="me", id=thread_id).execute()
                    )
                    gmail_thread = find_gmail_thread(thread_id)
                    involved_users = set()
                    email = None
                    for message in thread_data["messages"]:
                        # Track max history id
                        msg_history_id = int(message.get("historyId", 0))
                        if msg_history_id > max_history_id:
                            max_history_id = msg_history_id
                        try:
                            raw_email = (
                                gmail.users()
                                .messages()
                                .get(userId="me", id=message["id"], format="raw")
                                .execute()
                            )
                        except googleapiclient.errors.HttpError as e:
                            if hasattr(e, "error_details"):
                                for error in e.error_details:
                                    if error.get("reason") == "notFound":
                                        break
                            else:
                                raise e
                            continue
                        if "DRAFT" in raw_email.get("labelIds", []):
                            continue
                        is_new_thread = False
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
                        if gmail_thread:
                            gmail_thread.reload()
                        else:
                            gmail_thread = frappe.new_doc("Gmail Thread")
                            gmail_thread.gmail_thread_id = thread_id
                            gmail_thread.gmail_account = gmail_account.name
                            is_new_thread = True
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
                        involved_users.add(gmail_account.linked_user)
                        update_involved_users(gmail_thread, involved_users)
                        process_attachments(email, gmail_thread, email_object)
                        replace_inline_images(email, email_object)
                        gmail_thread.append("emails", email)
                        gmail_thread.save(ignore_permissions=True)
                        frappe.db.commit()  # nosemgrep
                        frappe.db.set_value(
                            "Gmail Thread",
                            gmail_thread.name,
                            "modified",
                            email.date_and_time,
                            update_modified=False,
                        )
                        if is_new_thread:  # update creation date
                            frappe.db.set_value(
                                "Gmail Thread",
                                gmail_thread.name,
                                "creation",
                                email.date_and_time,
                                update_modified=False,
                            )
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
                frappe.db.commit()  # nosemgrep
            else:
                # Incremental sync using history API
                try:
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
                except googleapiclient.errors.HttpError as e:
                    # If notFound, update historyid to the value returned by API (if any)
                    # You won't find history id in error, so just reset to 0 and let next sync do initial sync
                    if hasattr(e, "error_details"):
                        for error in e.error_details:
                            if error.get("reason") == "notFound":
                                gmail_account.last_historyid = 0
                                gmail_account.save(ignore_permissions=True)
                                frappe.db.commit()
                                return
                    raise e

                new_history_id = int(history.get("historyId", last_history_id))
                if new_history_id > max_history_id:
                    max_history_id = new_history_id
                updated_docs = set()
                if "history" in history:
                    # Collect message ids and thread mapping
                    message_ids: List[str] = []
                    message_to_thread: Dict[str, str] = {}
                    for hist in history["history"]:
                        for message in hist.get("messages", []):
                            mid = message.get("id")
                            tid = message.get("threadId")
                            if not mid or not tid:
                                continue
                            message_ids.append(mid)
                            message_to_thread[mid] = tid

                    if not message_ids:
                        gmail_account.reload()
                        gmail_account.last_historyid = max_history_id
                        gmail_account.save(ignore_permissions=True)
                        frappe.db.commit()  # nosemgrep
                        continue

                    start_time = time.time()
                    total_processed = 0
                    total_skipped_draft = 0
                    total_duplicates = 0

                    # Use batch_size if configured; fall back to 50
                    incremental_batch_size = batch_size if batch_size and batch_size > 0 else 50

                    for mids_chunk in _chunk_list(message_ids, incremental_batch_size):
                        # Rate-limit gate
                        wait_s = _get_wait_seconds_if_rate_limited(gmail_account.name)
                        if wait_s > 0:
                            logger.info(
                                f"gmail_sync: rate-limited; deferring chunk (account={gmail_account.name}, wait_s={wait_s})"
                            )
                            break
                        try:
                            messages_map = _batch_fetch_raw_messages(gmail, mids_chunk)
                        except googleapiclient.errors.HttpError as e:
                            status = getattr(getattr(e, "resp", None), "status", None)
                            if status == 429:
                                retry_after = getattr(e, "resp", {}).get("retry-after") if hasattr(e, "resp") else None
                                retry_after_seconds = int(retry_after) if retry_after and str(retry_after).isdigit() else 60
                                _set_rate_limit_until(gmail_account.name, retry_after_seconds)
                                logger.info(
                                    f"gmail_sync: 429 received; setting retry-after {retry_after_seconds}s (account={gmail_account.name})"
                                )
                                break
                            raise

                        for mid, raw_email in messages_map.items():
                            if not raw_email:
                                continue
                            if "DRAFT" in raw_email.get("labelIds", []):
                                total_skipped_draft += 1
                                continue
                            thread_id = message_to_thread.get(mid)
                            if not thread_id:
                                continue
                            gmail_thread = find_gmail_thread(thread_id)
                            involved_users = set()
                            is_new_thread = False
                            try:
                                email, email_object = create_new_email(raw_email, gmail_account)
                            except AlreadyExistsError:
                                total_duplicates += 1
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
                                is_new_thread = True
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
                            involved_users.add(gmail_account.linked_user)
                            update_involved_users(gmail_thread, involved_users)
                            process_attachments(email, gmail_thread, email_object)
                            replace_inline_images(email, email_object)
                            gmail_thread.append("emails", email)
                            gmail_thread.save(ignore_permissions=True)
                            frappe.db.set_value(
                                "Gmail Thread",
                                gmail_thread.name,
                                "modified",
                                email.date_and_time,
                                update_modified=False,
                            )
                            if is_new_thread:  # update creation date
                                frappe.db.set_value(
                                    "Gmail Thread",
                                    gmail_thread.name,
                                    "creation",
                                    email.date_and_time,
                                    update_modified=False,
                                )
                            if (
                                gmail_thread.reference_doctype
                                and gmail_thread.reference_name
                            ):
                                updated_docs.add(
                                    (
                                        gmail_thread.reference_doctype,
                                        gmail_thread.reference_name,
                                    )
                                )
                            total_processed += 1

                    elapsed = round((time.time() - start_time), 2)
                    logger.info(
                        f"gmail_sync: incremental label={label_id} processed={total_processed} drafts_skipped={total_skipped_draft} duplicates={total_duplicates} elapsed_s={elapsed}"
                    )
                gmail_account.reload()
                gmail_account.last_historyid = max_history_id
                gmail_account.save(ignore_permissions=True)
                frappe.db.commit()  # nosemgrep
                if updated_docs:
                    for doctype, docname in updated_docs:
                        frappe.publish_realtime(
                            "gthread_new_email",
                            doctype=doctype,
                            docname=docname,
                        )
        except Exception:
            frappe.log_error(frappe.get_traceback(), "Gmail Thread Sync Error")
            continue


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
        return (
            frappe.db.exists(
                "Involved User",
                {"parent": doc.name, "account": user},
            )
            is not None
        )
    return False

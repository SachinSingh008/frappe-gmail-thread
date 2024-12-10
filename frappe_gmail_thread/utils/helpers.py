import json
import frappe
from frappe.utils import get_string_between, get_system_timezone, sanitize_html
from datetime import datetime
import base64

from frappe.email.receive import InboundMail, SentEmailInInboxError
import re
from bs4 import BeautifulSoup


class GmailInboundMail(InboundMail):
    def __init__(self, content, email_account, uid=None, seen_status=None, append_to=None):
        super().__init__(content, email_account, uid, seen_status, append_to)
        # remove quoted replies from email text content
        self.text_content = self.remove_quoted_replies(self.text_content, "text")
        self.html_content = self.remove_quoted_replies(self.html_content, "html")
        self.set_content_and_type()
        
    def remove_quoted_replies(self, content, type):
        if type == "text":
            regex = r"(\n|^)(On(.|\n)*?wrote:)((.|\n)*)"
            return re.sub(regex, "", content)
        if type == "html":
            soup = BeautifulSoup(content, "html.parser")
            # only works for gmail
            for div in soup.find_all("div", class_="gmail_quote"):
                div.decompose()
            return str(soup)
        
    def _build_communication_doc(self, sent_or_received = "Received"):
        data = self.as_dict()
        data["sent_or_received"] = sent_or_received
        
        data["doctype"] = "Communication"

        if self.parent_communication():
            data["in_reply_to"] = self.parent_communication().name

        append_to = self.append_to if self.email_account.use_imap else self.email_account.append_to

        if self.reference_document():
            data["reference_doctype"] = self.reference_document().doctype
            data["reference_name"] = self.reference_document().name
        elif append_to and append_to != "Communication":
            reference_name = self._create_reference_document(append_to)
            if reference_name:
                data["reference_doctype"] = append_to
                data["reference_name"] = reference_name

        if self.is_notification():
            # Disable notifications for notification.
            data["unread_notification_sent"] = 1

        if self.seen_status:
            data["_seen"] = json.dumps(self.get_users_linked_to_account(self.email_account))

        communication = frappe.get_doc(data)
        communication.flags.in_receive = True if data["sent_or_received"] == "Received" else False
        communication.insert(ignore_permissions=True)

        # Communication might have been modified by some hooks, reload before saving
        communication.reload()

        # save attachments
        communication._attachments = self.save_attachments_in_doc(communication)
        communication.content = sanitize_html(self.replace_inline_images(communication._attachments))
        communication.save()
        return communication


def find_gmail_thread(thread_id):
    try:
        gmail_thread = frappe.get_doc("Gmail Thread", {"gmail_thread_id": thread_id})
    except frappe.DoesNotExistError:
        gmail_thread = None
    return gmail_thread
    

def create_new_email(email, gmail_account, append_to=None, gmail_thread = None):
    email_content = base64.urlsafe_b64decode(email['raw'].encode('ASCII')).decode('utf-8')
    inbound_mail = GmailInboundMail(
                            content=email_content,
                            email_account=gmail_account,
                            append_to=append_to
                        )
    user = frappe.get_doc("User", gmail_account.linked_user)
    # check if email is sent or received
    is_sent = False
    if inbound_mail.from_email == user.email:
        is_sent = True

    try:
        email_ct = frappe.get_doc("Single Email CT", {"email_message_id": inbound_mail.message_id})
        if email_ct:
            return email_ct
    except frappe.DoesNotExistError:
        pass

    # if is_sent:
    #     inbound_mail._build_communication_doc(sent_or_received="Sent")
    # else:
    #     inbound_mail.process()
    
    # communication = frappe.get_doc("Communication", {"message_id": inbound_mail.message_id})
    # if gmail_thread and gmail_thread.reference_doctype and gmail_thread.reference_docname:
    #     communication.reference_doctype = gmail_thread.reference_doctype
    #     communication.reference_name = gmail_thread.reference_docname
    #     communication.status = "Linked"
    #     communication.save(ignore_permissions=True)
    #     frappe.db.commit()
    
    new_email = frappe.new_doc("Single Email CT")
    new_email.gmail_message_id = email["id"]
    new_email.subject = inbound_mail.subject
    new_email.sender = inbound_mail.from_email
    new_email.recipients = ""  # TODO: Correct this
    new_email.cc = "" # TODO: Correct this
    new_email.bcc = "" # TODO: Correct this
    new_email.content = inbound_mail.content
    new_email.plain_content = inbound_mail.text_content.strip()
    new_email.date_and_time = inbound_mail.date
    new_email.sender_full_name = inbound_mail.from_real_name
    new_email.read_receipt = False
    new_email.read_by_recipient = False
    new_email.read_by_recipient_on = None
    new_email.gmail_account = gmail_account.name
    new_email.email_status = "Open"
    new_email.email_message_id = inbound_mail.message_id
    new_email.linked_communication = None
    new_email.sent_or_received = "Sent" if is_sent else "Received"
    # set email creation date to the date of the email
    new_email.creation = new_email.date_and_time
    return new_email
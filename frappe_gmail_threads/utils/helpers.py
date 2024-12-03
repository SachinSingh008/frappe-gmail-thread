import json
import frappe
from frappe.utils import get_string_between, get_system_timezone, sanitize_html
from datetime import datetime
import base64

from frappe.email.receive import InboundMail, SentEmailInInboxError


class GmailInboundMail(InboundMail):
    def process(self):
        return super().process()


def find_gmail_thread(thread_id):
    try:
        gmail_thread = frappe.get_doc("Gmail Thread", {"gmail_thread_id": thread_id})
    except frappe.DoesNotExistError:
        gmail_thread = None
    return gmail_thread
    

def create_new_email(email, email_account, append_to=None, gmail_thread = None):
    email_content = base64.urlsafe_b64decode(email['raw'].encode('ASCII')).decode('utf-8')
    snippet = email["snippet"]
    inbound_mail = GmailInboundMail(
                            content=email_content,
                            email_account=email_account,
                            append_to=append_to
                        )

    # check if email is sent or received
    is_sent = False
    if inbound_mail.from_email == email_account.email_id:
        is_sent = True

    try:
        email_ct = frappe.get_doc("Single Email CT", {"email_message_id": inbound_mail.message_id})
        if email_ct:
            return email_ct
    except frappe.DoesNotExistError:
        pass

    inbound_mail.process()
    
    communication = frappe.get_doc("Communication", {"message_id": inbound_mail.message_id})
    if gmail_thread and gmail_thread.reference_doctype and gmail_thread.reference_docname:
        communication.reference_doctype = gmail_thread.reference_doctype
        communication.reference_name = gmail_thread.reference_docname
        communication.save(ignore_permissions=True)
        frappe.db.commit()
    
    new_email = frappe.new_doc("Single Email CT")
    new_email.gmail_message_id = email["id"]
    new_email.subject = communication.subject
    new_email.sender = communication.sender
    new_email.recipients = communication.recipients
    new_email.cc = communication.cc
    new_email.bcc = communication.bcc
    new_email.content = communication.content
    new_email.plain_content = snippet
    new_email.date_and_time = communication.communication_date
    new_email.sender_full_name = communication.sender_full_name
    new_email.read_receipt = communication.read_receipt
    new_email.read_by_recipient = communication.read_by_recipient
    new_email.read_by_recipient_on = communication.read_by_recipient_on
    new_email.email_account = communication.email_account
    new_email.email_status = communication.email_status
    new_email.email_message_id = communication.message_id
    new_email.linked_communication = communication.name
    new_email.sent_or_received = "Sent" if is_sent else "Received"
    # set email creation date to the date of the email
    new_email.creation = new_email.date_and_time
    return new_email
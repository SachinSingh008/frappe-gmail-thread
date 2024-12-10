import json
import frappe
from frappe.email.receive import Email 
import base64

from frappe.email.receive import InboundMail
import re
from bs4 import BeautifulSoup


class GmailInboundMail(Email):
    def __init__(self, content):
        super().__init__(content)
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


def find_gmail_thread(thread_id):
    try:
        gmail_thread = frappe.get_doc("Gmail Thread", {"gmail_thread_id": thread_id})
    except frappe.DoesNotExistError:
        gmail_thread = None
    return gmail_thread
    

def create_new_email(email, gmail_account, append_to=None, gmail_thread = None):
    email_content = base64.urlsafe_b64decode(email['raw'].encode('ASCII')).decode('utf-8')
    email_object = GmailInboundMail(
                            content=email_content
                        )
    user = frappe.get_doc("User", gmail_account.linked_user)
    # check if email is sent or received
    is_sent = False
    if email_object.from_email == user.email:
        is_sent = True

    try:
        email_ct = frappe.get_doc("Single Email CT", {"email_message_id": email_object.message_id})
        if email_ct:
            return email_ct
    except frappe.DoesNotExistError:
        pass
    
    new_email = frappe.new_doc("Single Email CT")
    new_email.gmail_message_id = email["id"]
    new_email.subject = email_object.subject
    new_email.sender = email_object.from_email
    new_email.recipients = ""  # TODO: Correct this
    new_email.cc = "" # TODO: Correct this
    new_email.bcc = "" # TODO: Correct this
    new_email.content = email_object.content
    new_email.plain_content = email_object.text_content.strip()
    new_email.date_and_time = email_object.date
    new_email.sender_full_name = email_object.from_real_name
    new_email.read_receipt = False
    new_email.read_by_recipient = False
    new_email.read_by_recipient_on = None
    new_email.gmail_account = gmail_account.name
    new_email.email_status = "Open"
    new_email.email_message_id = email_object.message_id
    new_email.linked_communication = None
    new_email.sent_or_received = "Sent" if is_sent else "Received"
    # set email creation date to the date of the email
    new_email.creation = new_email.date_and_time
    return new_email
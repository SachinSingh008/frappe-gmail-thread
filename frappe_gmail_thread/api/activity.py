import frappe

@frappe.whitelist()
def get_linked_gmail_threads(reference_doctype, reference_docname):
    gmail_threads = frappe.get_all("Gmail Thread", filters={"reference_doctype": reference_doctype, "reference_name": reference_docname})
    data = []
    for thread in gmail_threads:
        thread = frappe.get_doc("Gmail Thread", thread.name)
        user_full_name = frappe.get_value("User", thread.owner, "full_name")
        for email in thread.emails:
            data.append({
                "name": thread.name,
                "communication_type": "Gmail Thread",
                "communication_medium": "Email",
                "comment_type": "",
                "communication_date": email.creation,
                "content": email.content,
                "sender": email.sender,
                "sender_full_name": email.sender_full_name,
                "cc": email.cc,
                "bcc": email.bcc,
                "creation": email.creation,
                "subject": email.subject,
                "delivery_status": "",
                "_liked_by": thread._liked_by,
                "reference_doctype": thread.reference_doctype,
                "reference_name": thread.reference_name,
                "read_by_recipient": email.read_by_recipient,
                "rating": 0,  # TODO: add rating
                "recipients": email.recipients,
                "attachments": [], # TODO: add attachments
                "_url": thread.get_url(),
                "_doc_status": thread.docstatus,
                "_doc_status_indicator": "red",
                "owner": thread.owner,
                "user_full_name": user_full_name
            })
    return data
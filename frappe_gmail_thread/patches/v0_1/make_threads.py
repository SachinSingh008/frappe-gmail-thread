# import frappe
# from frappe_gmail_thread.utils.helpers import create_new_email, find_gmail_thread

# def sync_emails():
#     pass

# def execute():
#     communications = frappe.get_all("Communication", filters={"communication_medium": "Email", "in_reply_to": ""}, fields=["*"], order_by="communication_date")
    
#     for communication in communications:
#         new_gmail_thread = frappe.new_doc("Gmail Thread")
#         new_email = create_new_email(communication)
#         new_gmail_thread.emails = [new_email]
#         new_gmail_thread.email_account = communication.email_account
#         new_gmail_thread.subject_of_first_mail = communication.subject
#         new_gmail_thread.save(ignore_permissions=True)
#         frappe.db.commit()
        
#     communication_with_in_reply_to = frappe.get_all("Communication", filters={"communication_medium": "Email", "in_reply_to": ["!=", ""]}, fields=["*"], order_by="communication_date")
    
#     for communication in communication_with_in_reply_to:
#         gmail_thread = find_gmail_thread(frappe.get_doc("Communication", communication.name))
#         if gmail_thread:
#             gmail_thread = frappe.get_doc("Gmail Thread", gmail_thread)
#             gmail_thread.append("emails", create_new_email(communication))
#             gmail_thread.save(ignore_permissions=True)
#             frappe.db.commit()
#         else:
#             frappe.log_error(f"No Gmail Thread found for {communication.name}")
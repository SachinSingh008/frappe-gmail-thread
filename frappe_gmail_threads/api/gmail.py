import frappe
from frappe import _

from urllib.parse import quote

@frappe.whitelist()
def is_gmail_configured():
    user = frappe.session.user
    user_email = frappe.get_value("User", user, "email")
    email_account = frappe.get_doc("Email Account", {"email_id": user_email})
    if not frappe.has_permission("Email Account", email_account.name):
        frappe.throw(_("You don't have permission to access this document"), frappe.PermissionError)
    if not email_account.custom_gmail_enabled:
        return {
            "configured": False,
            "message": f"Please configure Gmail in <a href='/app/email-account/{quote(email_account.name)}'>Email Account</a>."
        }
    if email_account.custom_gmail_refresh_token and email_account.email_id == user_email:
        return {
            "configured": True,
            "message": "Gmail is configured."
        }
    return {
        "configured": False,
        "message": "Gmail is not configured."
    }
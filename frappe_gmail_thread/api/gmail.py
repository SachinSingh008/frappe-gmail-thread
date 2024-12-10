import frappe
from frappe import _

from urllib.parse import quote

@frappe.whitelist()
def is_gmail_configured():
    user = frappe.session.user
    gmail_account = frappe.get_doc("Gmail Account", {"linked_user": user})
    if not frappe.has_permission("Gmail Account", gmail_account.name):
        frappe.throw(_("You don't have permission to access this document"), frappe.PermissionError)
    if not gmail_account.gmail_enabled:
        return {
            "configured": False,
            "message": f"Please configure Gmail in <a href='/app/email-account/{quote(gmail_account.name)}'>Email Account</a>."
        }
    if gmail_account.refresh_token and gmail_account.linked_user == user:
        return {
            "configured": True,
            "message": "Gmail is configured."
        }
    return {
        "configured": False,
        "message": "Gmail is not configured."
    }
from urllib.parse import quote

import frappe
from frappe import _


@frappe.whitelist()
def is_gmail_configured():
    user = frappe.session.user
    try:
        gmail_account = frappe.get_doc("Gmail Account", {"linked_user": user})
    except frappe.DoesNotExistError:
        return {
            "configured": False,
            "message": f"Gmail Account not found for {user}. Please configure Gmail in <a href='/app/gmail-account'>Gmail Account</a>.",
        }
    if not frappe.has_permission(
        doctype="Gmail Account", doc=gmail_account.name, ptype="read"
    ):
        frappe.throw(
            _("You don't have permission to access this document"),
            frappe.PermissionError,
        )
    if not gmail_account.gmail_enabled:
        return {
            "configured": False,
            "message": f"Please configure Gmail in <a href='/app/email-account/{quote(gmail_account.name)}'>Email Account</a>.",
        }
    if gmail_account.refresh_token and gmail_account.linked_user == user:
        return {"configured": True, "message": "Gmail is configured."}
    return {"configured": False, "message": "Gmail is not configured."}

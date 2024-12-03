import frappe

import google.oauth2.credentials
from urllib.parse import quote
from frappe.integrations.google_oauth import GoogleOAuth
import requests
from frappe import _

SCOPES = "https://www.googleapis.com/auth/gmail.readonly"

def get_authentication_url(client_id=None, redirect_uri=None):
    return {
        "url": "https://accounts.google.com/o/oauth2/v2/auth?access_type=offline&response_type=code&prompt=consent&client_id={}&include_granted_scopes=true&scope={}&redirect_uri={}".format(
            client_id, SCOPES, redirect_uri
        )
    }

@frappe.whitelist()
def get_auth_url(doc):
    current_user = frappe.session.user
    current_user = frappe.get_doc("User", current_user)
    doc = frappe.get_doc("Email Account", doc)
    # check permission
    if not frappe.has_permission("Email Account", doc.name):
        frappe.throw(_("You don't have permission to access this document"), frappe.PermissionError)
    # check if user email is same as email account email
    if current_user.email != doc.email_id:
        frappe.throw(_("You can only authorize access for your own email account"), frappe.PermissionError)
    google_settings = frappe.get_single("Google Settings")
    client_id = google_settings.client_id
    redirect_uri = frappe.utils.get_url("/api/method/frappe_gmail_threads.api.oauth.callback")
    return get_authentication_url(client_id, redirect_uri)


@frappe.whitelist()
def authorize_access(email, reauthorize=None):
    """
    If no Authorization code get it from Google and then request for Refresh Token.
    """
    google_settings = frappe.get_doc("Google Settings")
    email_account = frappe.get_doc("Email Account", {"email_id": email})
    email_account.check_permission("write")

    redirect_uri = frappe.utils.get_url("/api/method/frappe_gmail_threads.api.oauth.callback")

    if not email_account.custom_gmail_authorization_code or reauthorize:
        return get_authentication_url(client_id=google_settings.client_id, redirect_uri=redirect_uri)
    else:
        try:
            data = {
                "code": email_account.get_password(fieldname="custom_gmail_authorization_code", raise_exception=False),
                "client_id": google_settings.client_id,
                "client_secret": google_settings.get_password(
                    fieldname="client_secret", raise_exception=False
                ),
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            }
            r = requests.post(GoogleOAuth.OAUTH_URL, data=data).json()

            if "refresh_token" in r:
                frappe.db.set_value(
                    "Email Account", email_account.name, "custom_gmail_refresh_token", r.get("refresh_token")
                )
                frappe.db.commit()

            frappe.local.response["type"] = "redirect"
            frappe.local.response["location"] = f"/app/email-account/{quote(email_account.name)}"

            frappe.msgprint(_("Gmail has been configured."))
        except Exception as e:
            frappe.throw(e)


@frappe.whitelist()
def callback(code):
    """
    Authorization code is sent to callback as per the API configuration
    """
    user = frappe.session.user
    user_email = frappe.get_value("User", user, "email")
    # get email account using filter
    email_account = frappe.get_doc("Email Account", {"email_id": user_email})
    
    frappe.db.set_value("Email Account", email_account.name, "custom_gmail_authorization_code", code)
    frappe.db.commit()

    authorize_access(user_email)


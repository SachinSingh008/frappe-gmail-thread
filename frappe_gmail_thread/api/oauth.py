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
    try:
        doc = frappe.get_doc("Gmail Account", doc)
    except frappe.DoesNotExistError:
        frappe.throw(_("Gmail Account not found. If not saved, please save the document first."), frappe.DoesNotExistError)
    # check permission
    if not frappe.has_permission("Gmail Account", doc.name):
        frappe.throw(_("You don't have permission to access this document"), frappe.PermissionError)
    # check if user email is same as email account email
    if current_user.name != doc.linked_user:
        frappe.throw(_("You can only authorize access for your own email account"), frappe.PermissionError)
    google_settings = frappe.get_single("Google Settings")
    client_id = google_settings.client_id
    redirect_uri = frappe.utils.get_url("/api/method/frappe_gmail_thread.api.oauth.callback")
    return get_authentication_url(client_id, redirect_uri)


def authorize_access(user, reauthorize=None):
    """
    If no Authorization code get it from Google and then request for Refresh Token.
    """
    google_settings = frappe.get_doc("Google Settings")
    gmail_account = frappe.get_doc("Gmail Account", {"linked_user": user})
    gmail_account.check_permission("write")

    redirect_uri = frappe.utils.get_url("/api/method/frappe_gmail_thread.api.oauth.callback")

    if not gmail_account.authorization_code or reauthorize:
        return get_authentication_url(client_id=google_settings.client_id, redirect_uri=redirect_uri)
    else:
        try:
            data = {
                "code": gmail_account.get_password(fieldname="authorization_code", raise_exception=False),
                "client_id": google_settings.client_id,
                "client_secret": google_settings.get_password(
                    fieldname="client_secret", raise_exception=False
                ),
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            }
            r = requests.post(GoogleOAuth.OAUTH_URL, data=data).json()

            if "refresh_token" in r:
                gmail_account.reload()
                gmail_account.refresh_token = r["refresh_token"]
                gmail_account.save(ignore_permissions=True)
                frappe.db.commit() # nosemgrep: Committing manually because it's a part of a GET request

            frappe.local.response["type"] = "redirect"
            frappe.local.response["location"] = f"/app/gmail-account/{quote(gmail_account.name)}"

            frappe.msgprint(_("Gmail has been configured."))
        except Exception as e:
            frappe.throw(e)


@frappe.whitelist()
def callback(code):
    """
    Authorization code is sent to callback as per the API configuration
    """
    user = frappe.session.user
    # get gmail account using filter
    gmail_account = frappe.get_doc("Gmail Account", {"linked_user": user})
    
    frappe.db.set_value("Gmail Account", gmail_account.name, "authorization_code", code)
    frappe.db.commit()

    authorize_access(user)


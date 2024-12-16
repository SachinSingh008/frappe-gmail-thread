import base64 as b64
import json

import frappe


@frappe.whitelist(allow_guest=True)
def callback():
    data = frappe.request.get_data(as_text=True)
    data = frappe.parse_json(data)
    message = data.get("message", {}).get("data")
    if message:
        message = b64.b64decode(message).decode("utf-8")
        try:
            message = json.loads(message)
        except json.JSONDecodeError:
            frappe.log_error(f"Error while decoding message: {message}")
            return "OK"
        email_address = message.get("emailAddress")
        user = frappe.get_doc(
            "User", {"email": email_address, "user_type": "System User"}
        )
        if not user:
            return "OK"
        history_id = message.get("historyId")
        if email_address and history_id:
            frappe.enqueue(
                "frappe_gmail_thread.frappe_gmail_thread.doctype.gmail_thread.gmail_thread.sync",
                user=user.name,
                history_id=history_id,
            )
        print("PubSub message received: ", message)
    return "OK"

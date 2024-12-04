import frappe
import base64 as b64
import json

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
        history_id = message.get("historyId")
        if email_address and history_id:
            frappe.enqueue("frappe_gmail_thread.frappe_gmail_thread.doctype.gmail_thread.gmail_thread.sync", email=email_address, history_id=history_id)
        print("PubSub message received: ", message)
    return "OK"
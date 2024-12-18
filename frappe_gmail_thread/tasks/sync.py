import frappe


def sync_emails():
    gmail_accounts = frappe.get_all(
        "Gmail Account",
        filters={"gmail_enabled": 1},
        fields=["name"],
    )
    for gmail_account in gmail_accounts:
        gaccount = frappe.get_doc("Gmail Account", gmail_account.name)
        if gaccount.refresh_token:
            user = gaccount.linked_user
            history_id = gaccount.last_historyid
            frappe.enqueue(
                "frappe_gmail_thread.frappe_gmail_thread.doctype.gmail_thread.gmail_thread.sync",
                user=user,
                history_id=history_id,
                queue="long",
            )

import frappe


def execute():
    reset_all_history_id()


def reset_all_history_id():
    gmail_accounts = frappe.get_all(
        "Gmail Account",
        filters={"gmail_enabled": 1},
        fields=["name"],
    )
    for gmail_account in gmail_accounts:
        gaccount = frappe.get_doc("Gmail Account", gmail_account.name)
        gaccount.last_historyid = None
        gaccount.save()
        frappe.db.commit()

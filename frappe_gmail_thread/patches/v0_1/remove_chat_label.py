import frappe


def execute():
    remove_label_name()


def remove_label_name():
    gmail_accounts = frappe.get_all(
        "Gmail Account",
        filters={"gmail_enabled": 1},
        fields=["name"],
    )
    for gmail_account in gmail_accounts:
        gaccount = frappe.get_doc("Gmail Account", gmail_account.name)
        for label in gaccount.get("labels", []):
            if label.get("label_name") == "CHAT":
                # remove chat label from list
                gaccount.remove(label)
                break
        gaccount.save(ignore_permissions=True)

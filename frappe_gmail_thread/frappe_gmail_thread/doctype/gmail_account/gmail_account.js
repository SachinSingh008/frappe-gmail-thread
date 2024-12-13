frappe.ui.form.on("Gmail Account", {
    authorize_gmail: function (frm) {
        frappe.call({
            method: "frappe_gmail_thread.api.oauth.get_auth_url",
            args: {
                doc: frm.doc.name,
            },
            callback: function (r) {
                try {
                    var url = r.message.url;
                    window.location.href = url;
                } catch (error) {
                    frappe.msgprint("Something went wrong. Please try again later, or report issue in GitHub issues.");
                }
            },
        });
    },
    fetch_labels: function (frm) {
        // disable button
        frm.set_df_property("fetch_labels", "read_only", 1);
        frappe.call({
            method: "frappe_gmail_thread.frappe_gmail_thread.doctype.gmail_thread.gmail_thread.sync_labels",
            args: {
                account_name: frm.doc.name,
            },
            callback: function (r) {
                frappe.msgprint("Labels fetched successfully.");
                frm.reload_doc();
            },
            error: function (r) {
                frappe.msgprint("Something went wrong. Please try again later, or report issue in GitHub issues.");
                frm.reload_doc();
            },
        });
    }
});
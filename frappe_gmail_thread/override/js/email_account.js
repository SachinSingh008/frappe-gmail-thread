frappe.ui.form.on("Email Account", {
    custom_authorize_gmail: function (frm) {
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
});
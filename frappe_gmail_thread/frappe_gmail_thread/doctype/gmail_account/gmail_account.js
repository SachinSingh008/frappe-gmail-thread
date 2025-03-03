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
          frappe.msgprint(__("Something went wrong. Please try again later, or report issue in GitHub issues."));
        }
      },
    });
  },
  fetch_labels: function (frm) {
    // disable button
    frm.set_df_property("fetch_labels", "read_only", 1);
    frappe.call({
      method: "frappe_gmail_thread.frappe_gmail_thread.doctype.gmail_thread.gmail_thread.sync_labels",
      type: "POST",
      args: {
        account_name: frm.doc.name,
      },
      callback: function (r) {
        frappe.msgprint(__("Labels fetched successfully."));
        frm.reload_doc();
      },
      error: function (r) {
        frappe.msgprint(__("Something went wrong. Please try again later, or report issue in GitHub issues."));
        frm.reload_doc();
      },
    });
  },
  refresh: function (frm) {
    // if email_id is empty, set it as current user's email
    if (!frm.doc.email_id) {
      user_email = frappe.session.user_email;
      frm.set_value("email_id", user_email);
    }
    if (frm.doc.refresh_token) {
      frm.add_custom_button(__("Fetch Labels"), function () {
        frm.events.fetch_labels(frm);
      });
      frm.add_custom_button(__("Resync Emails"), function () {
        frappe.confirm(__("Are you sure you want to resync all emails?"), function () {
          frappe.call({
            method: "frappe_gmail_thread.frappe_gmail_thread.doctype.gmail_account.gmail_account.sync_labels_api",
            type: "POST",
            args: {
              args: {
                doc_name: frm.doc.name,
                reset_historyid: true,
              },
            },
            callback: function (r) {},
            error: function (r) {
              frappe.msgprint(__("Something went wrong. Please try again later, or report issue in GitHub issues."));
              frm.reload_doc();
            },
          });
        });
      });
    }
    frm.fields_dict.labels.$wrapper.find(".grid-row-check").hide();
  },
  onload(frm) {
    frm.get_field("labels").grid.cannot_add_rows = true;
  },
});

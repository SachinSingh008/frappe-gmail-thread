frappe.ui.form.on("Gmail Thread", {
  refresh: function (frm) {
    const relink_title = frm.doc.reference_doctype && frm.doc.reference_name ? __("Relink") : __("Link");
    const relink_label = `${relink_title} Gmail Thread`;
    frm.add_custom_button(__(relink_title), function () {
      // open dialog to relink
      frappe.prompt(
        [
          {
            fieldname: "doctype",
            label: __("Document Type"),
            fieldtype: "Link",
            options: "DocType",
            reqd: 1,
          },
          {
            fieldname: "docname",
            label: __("Document Name"),
            fieldtype: "Dynamic Link",
            options: "doctype",
            reqd: 1,
          },
        ],
        function (values) {
          frappe.call({
            method: "frappe_gmail_thread.api.activity.relink_gmail_thread",
            args: {
              name: frm.doc.name,
              doctype: values.doctype,
              docname: values.docname,
            },
            callback: function (r) {
              if (r.message) {
                frm.reload_doc();
              }
            },
          });
        },
        __(relink_label),
        __(relink_title)
      );
    });
  },
});

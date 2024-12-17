frappe.listview_settings["Gmail Thread"] = {
  hide_name_column: true,
  onload: function (listview) {
    frappe.call({
      method: "frappe_gmail_thread.api.gmail.is_gmail_configured",
      callback: function (r) {
        if (r.message) {
          if (!r.message.configured) {
            frappe.msgprint(r.message.message);
          }
        }
      },
    });
  },
};

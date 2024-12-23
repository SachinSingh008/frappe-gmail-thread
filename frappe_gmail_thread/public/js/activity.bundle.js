import FormTimeline from "frappe/public/js/frappe/form/footer/form_timeline.js";

class GmailFormTimeline extends FormTimeline {
  constructor(opts) {
    super(opts);
  }

  make() {
    super.make();
  }

  prepare_timeline_contents() {
    super.prepare_timeline_contents();
    const timeline_contents = this.get_gthread_timeline_contents();
    this.timeline_items.push(...timeline_contents);
  }

  get_gthread_timeline_contents() {
    const doctype = this.frm.doctype;
    const docname = this.frm.docname;
    const timeline_contents = [];
    // get results from whitelisted method frappe_gmail_thread.api.activity.get_linked_gmail_threads
    const response = frappe.call({
      method: "frappe_gmail_thread.api.activity.get_linked_gmail_threads",
      args: {
        reference_doctype: doctype,
        reference_docname: docname,
      },
      async: false,
    });
    if (response.responseJSON.message) {
      const gmail_threads = response.responseJSON.message;
      const all_emails = [];
      for (let gmail_thread of gmail_threads) {
        all_emails.push(gmail_thread.sender);
      }
      const unique_emails = [...new Set(all_emails)];
      const user_info_for_viewers = frappe.call({
        method: "frappe.desk.form.load.get_user_info_for_viewers",
        args: {
          users: JSON.stringify(unique_emails),
        },
        async: false,
      });
      if (user_info_for_viewers.responseJSON.message) {
        const user_info = user_info_for_viewers.responseJSON.message;
        frappe.update_user_info(user_info);
      }
      for (let gmail_thread of gmail_threads) {
        const email = gmail_thread.sender;
        const communication_content = get_gthread_timeline_content(gmail_thread);
        const t_data = {
          icon: "mail",
          icon_size: "sm",
          creation: gmail_thread.creation,
          is_card: true,
          content: communication_content,
          doctype: "Gmail Thread",
          id: `gmail-thread-${gmail_thread.name}`,
          name: gmail_thread.name,
          delivery_status: gmail_thread.delivery_status,
        };
        timeline_contents.push(t_data);
      }
    }
    return timeline_contents;
  }
}

frappe.ui.form.Footer = class extends frappe.ui.form.Footer {
  make_timeline() {
    this.frm.timeline = new GmailFormTimeline({
      parent: this.wrapper.find(".timeline"),
      frm: this.frm,
    });
  }
};

function get_gthread_timeline_content(doc) {
  doc._url = frappe.utils.get_form_link("Gmail Thread", doc.name);
  if (doc.attachments && typeof doc.attachments === "string") {
    doc.attachments = JSON.parse(doc.attachments);
  }
  doc.owner = doc.sender;
  doc.user_full_name = doc.sender_full_name;
  doc.content = frappe.dom.remove_script_and_style(doc.content);
  let communication_content = $(frappe.render_template("timeline_message_box", { doc }));
  return communication_content;
}

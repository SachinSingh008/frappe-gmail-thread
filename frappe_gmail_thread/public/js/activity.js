const setup_gmail_threads_activity = function(frm) {
    // get linked email thread
    const doctype = frm.doctype;
    const docname = frm.docname;
    // get results from whitelisted method frappe_gmail_thread.api.activity.get_linked_gmail_threads
    frappe.call({
        method: "frappe_gmail_thread.api.activity.get_linked_gmail_threads",
        args: {
            reference_doctype: doctype,
            reference_docname: docname
        },
        callback: function(response) {
            if (response.message) {
                const gmail_threads = response.message;
                // add gmail threads to the form
                add_gmail_threads_to_form(frm, gmail_threads);
            }
        }
    });
}

// call before_load function when form is loaded but activity is not yet loaded
$(document).on("form-refresh", function(event, frm) {
    frappe.ui.form.on(frm.doctype, {
        refresh: setup_gmail_threads_activity
    });
});

function add_gmail_threads_to_form(frm, gmail_threads) {
    if (!gmail_threads || gmail_threads.length === 0) {
        return;
    }
    // add gmail threads to the form
    const timeline = frm.timeline
    timeline.refresh();
    const communication_contents = [];
    const all_emails = [];
    for (let gmail_thread of gmail_threads) {
        all_emails.push(gmail_thread.sender);
    }
    const unique_emails = [...new Set(all_emails)];
    // fetch user info from http://localhost/api/method/frappe.desk.form.load.get_user_info_for_viewers?users=[%22shivam.saini@rtcamp.com%22]
    frappe.call({
        method: "frappe.desk.form.load.get_user_info_for_viewers",
        args: {
            users: JSON.stringify(unique_emails)
        },
        callback: function(response) {
            const user_info = response.message;
            frappe.update_user_info(user_info);
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
                }
                communication_contents.push(t_data);
            }
            timeline.add_timeline_items_based_on_creation(communication_contents);
        }
    });
}

function get_gthread_timeline_content(doc, allow_reply = true) {
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

// frappe realtime on gthread_new_email, check if reference_doctype and reference_name matches with current form
frappe.realtime.on("gthread_new_email", function(data) {
    setup_gmail_threads_activity(cur_frm);
});
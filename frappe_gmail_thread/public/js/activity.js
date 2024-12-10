const setup_gmail_threads_activity = function(frm) {
    alert("hello.")
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
$(document).on("load", function (event, frm) {
    frappe.ui.form.on(frm.doctype, {
        before_load: setup_gmail_threads_activity
    });
});

function add_gmail_threads_to_form(frm, gmail_threads) {
    // add gmail threads to the form
    const timeline_communications = frm.timeline.doc_info.communications
    for (let gmail_thread of gmail_threads) {
        // push gmail thread to timeline communications
        timeline_communications.push(gmail_thread);
    }
}
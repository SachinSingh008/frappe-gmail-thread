// frappe.ui.form.on("Gmail Thread", {
//     refresh: function(frm) {
//         emails = frm.doc.emails;
//         if (emails) {
//             emails = emails;
//             for (let email of emails) {
//                 attachments = email.attachments_data;
//                 if (attachments) {
//                     attachments = JSON.parse(attachments);
//                     html = "<table class='table table-bordered'>";
//                     html += "<thead><tr><th>File Name</th><th>Open</th></tr></thead>";
//                     html += "<tbody>";
//                     for (let attachment of attachments) {
//                         html += `<tr><td>${attachment.name}</td><td><a href="${attachment.file_url}" target="_blank">Open</a></td></tr>`;
//                     }
//                     html += "</tbody>";
//                     html += "</table>";
//                     email.attachments_data_html = html;
//                 }
//             }
//         }
//     }
// });

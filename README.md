# Frappe Gmail Thread

A Frappe app that integrates with Gmail's Thread ID to seamlessly sync and track email conversations within your Frappe/ERPNext instance. This provides a unified view of your communications, allowing you to link email threads directly to ERPNext documents like Leads, Sales Orders, and Tasks.

### [View the GitHub Wiki for Full Documentation](https://github.com/rtCamp/frappe-gmail-thread/wiki "null")

## Key Features

- **Seamless Email Syncing:** Automatically syncs sent and received emails into your Frappe instance.

- **Threaded Conversations:** Organizes emails into cohesive threads based on Gmail's native Thread ID.

- **Document Linking:** Link email threads to any ERPNext doctype to view communication history in the document's activity feed.

- **Multi-User Visibility:** Emails with CC/BCC recipients automatically grant all involved users access to the thread.

- **Attachment Management:** Attachments are linked to the thread and visible within the associated document.

- **Manual User Access:** Manually add users to a thread to grant them access to the conversation.

- **Selective Syncing:** Use Gmail labels to control which emails are synced to Frappe, giving you granular control over what data is stored.

## Technical Details

The app uses email message IDs and reference headers to group emails into a single `Gmail Thread` doctype, unifying threads across different user mailboxes within Frappe.

## Contributing

We welcome contributions! If you encounter any bugs or have suggestions, please open an issue or submit a pull request on our GitHub repository.

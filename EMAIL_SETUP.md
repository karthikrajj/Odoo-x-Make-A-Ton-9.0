# Gmail real email setup

1. Enable Google 2-Step Verification and create an app password using https://support.google.com/accounts/answer/185833 . Account policies may restrict availability.
2. Double-click Setup-Gmail.cmd. Enter your sending address and app password in that local window. It tests encrypted authentication without sending a message and stores the configuration in the ignored .env file.
3. Restart RenewSure. Admin sees Email delivery in the sidebar, including delivery states. Register a real address and use Forgot password to verify inbox receipt. The worker processes the queue every 30 seconds.

Google's SMTP endpoint is smtp.gmail.com, port 587 with STARTTLS. Sources: https://support.google.com/mail/answer/7104828 and https://developers.google.com/workspace/gmail/imap/imap-smtp .

The public demo mailbox is removed. Old local-demo messages and addresses ending in .demo, .test, .invalid or .example are suppressed. This prevents the seeded dataset from generating thousands of real emails when Gmail is connected.

Waiting for email setup means configuration is missing. Queued means awaiting the worker. Sent means the SMTP server accepted the message; inbox placement is controlled by the recipient provider. Delivery needs review means a send attempt had an uncertain outcome and will not automatically be retried, avoiding accidental duplicates. A server interrupted in Sending also needs review.

Do not commit .env or share its contents. Google password entry and account setup must be completed by the account owner. The current local installation has a user-confirmed Gmail connection test. A new installation must configure its own sender and verify inbox receipt.

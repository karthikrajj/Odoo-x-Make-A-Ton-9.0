CREATE INDEX IF NOT EXISTS ix_invoice_email ON invoices(email);

CREATE INDEX IF NOT EXISTS ix_allocation_invoice ON allocations(invoice_id);

CREATE INDEX IF NOT EXISTS ix_subscription_due ON subscriptions(state,due);

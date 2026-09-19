# Financial Agent - Corporate Policies & Guidelines

## 1. Invoicing & Late Fees
- **Standard Late Fee:** A standard late fee of $25.00 applies to all invoices that are past due by more than 15 days.
- **Enterprise Late Fee:** For Enterprise tier clients, the late fee is calculated as 5% of the total invoice amount.
- **Grace Period:** All accounts have a 15-day grace period from the invoice due date before any penalties are applied.

## 2. Refund Policies
- **Refund Limits:** Customer service representatives can automatically process refunds up to $500. Any refund exceeding $500 requires managerial approval and must be routed through the Dispute Resolution portal.
- **Time Window:** Refunds can only be processed within 45 days of the original transaction date.

## 3. Dispute Resolution SLAs
- **Standard SLA:** All standard disputes must be acknowledged within 24 hours and resolved within 5 business days.
- **High-Priority SLA:** Disputes involving transaction amounts over $10,000 are classified as High-Priority and must be resolved within 48 hours.

## 4. API & System Constraints
- **Supported Currencies:** The SAP and Salesforce integrations currently only support USD and EUR currencies. Any attempt to sync JPY or GBP will result in a validation error.
- **Batch Processing:** AWS Payment syncs are batched and executed every 4 hours. Real-time sync is not currently supported for AWS.

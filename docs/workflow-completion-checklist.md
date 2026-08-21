# QA checklist

- Worker Akte: contracts, grouped documents, payroll, shifts.
- Client Akte: contracts, grouped documents, orders, locations, shifts.
- Role isolation: client cannot open another client's Akte.
- Client order attachment: multipart PATCH, allowed extension validation, 20 MB limit.
- Drawn signature: pointer canvas emits PNG data URI into contract signing flow.
- Client ANÜ: PDF link available before/after signing and final PDF is regenerated/stamped by existing backend flow.
- Responsive/mobile: Akte and upload dialogs collapse to a single column / bottom sheet.
- WIW reset/import: not included.
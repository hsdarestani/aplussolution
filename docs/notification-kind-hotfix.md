# Notification kind length hotfix

Production PostgreSQL correctly enforces the declared VARCHAR length. UUID-scoped notification event identifiers used by attendance and other workflows can exceed the previous 50-character limit. The model and database column are widened to 120 characters so event identifiers are stored without truncation while retaining the existing notification schema and semantics.

# Scheduling flow v2

The primary scheduling model is demand-first and employee self-service.

1. A+ creates or imports a customer staffing request.
2. The request produces an editable staffing demand with client, location, position, date/time and required headcount.
3. A+ publishes the demand as an OpenShift.
4. Each required place is represented by a persistent capacity slot.
5. Employees see published availability in their own portal and choose an open shift themselves.
6. A claim is confirmed immediately when capacity remains and objective overlap/availability checks pass.
7. The demand remains open until all required places are filled.
8. An employee can release their own place back to the pool; swap flows remain a separate workflow.
9. Direct administrative assignment is not part of the primary UI and is reserved for a later emergency override flow.

This phase deliberately avoids automatic employee selection or ranking. The system manages capacity and validates scheduling constraints; the employee chooses the shift.

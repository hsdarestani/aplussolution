# Weekly Stundenzettel

Web admin dashboard: Stundenzettel → Kalenderwoche → Housekeeping · PDF / Front Office · PDF. Hidden in Capacitor builds. Server enforces existing admin/manager permissions; employee/client/anonymous access is denied.

GET `/api/reports/stundenzettel.pdf?week=2026-W45&group=housekeeping` (or `front_office`). Strict ISO week validation; weeks run Monday–Sunday in Europe/Berlin. Default selection is the last completed Berlin week. No email is sent.

The background is the actual emailed A+ form (Gmail Front Office editable attachment, 5 October 2026), with all original form widgets and example personal/hotel data removed, and the department/hotel fields cleared. Both department variants share this print layout and logo. The original 15-row landscape A4 form remains editable with unique fields per page.

Uses completed, approved native TimeEntry rows and imported WIW historical TimeEntry rows, consistently with existing attendance reports. No scheduled hours or open shifts are substituted. Native pending entries are excluded; empty department/week returns a visible 404 message. Entries without a shift are classified as Service by the existing attendance classifier, so cannot be attributed to HK/FO and are excluded. No live WIW API calls.

Entries belong to their Berlin start date, including overnight/week-boundary shifts (as in the emailed FO example). Duration uses actual UTC elapsed minutes minus effective breaks. Legal first/last names are used, not display aliases. Each client/location has separate pages, even when names match; 14 entries plus the numeric page sum in the hours column, exactly as the emailed form. The upper-right area is empty and the sum has no caption. Per the owner’s explicit format instruction, each populated work row displays “bestätigt” under the original “Bestätigung Hotel (Unterschrift)” heading. This export wording does not update approval/signature records in the database.

Validation: backend tests cover permissions, invalid ISO weeks, missing data, real hours/pause deduction, overnight week boundary, WIW history, editable fields/appearances, hotel isolation, multipage rendering and DST. Frontend tests cover native hiding, ISO week-year/Berlin boundaries, selected week/group download and failures. Build and PDF render inspection required before release.

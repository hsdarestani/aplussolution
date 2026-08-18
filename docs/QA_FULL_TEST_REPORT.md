# A+ Solution — Full Capability QA Report

این سند مسیر تست دستی کل اپ را به همان ترتیبی می‌دهد که QA خودکار و بررسی کد انجام شده است. عنوان دکمه‌ها/صفحه‌ها همان متن داخل اپ است تا تست دوباره راحت باشد.

## وضعیت‌ها

- `AUTO` = سناریو تست خودکار دارد.
- `MANUAL` = باید روی محیط واقعی/دستگاه واقعی هم تست شود.
- `EXTERNAL` = به credential یا سرویس بیرونی واقعی نیاز دارد و از داخل repository به تنهایی قابل تأیید کامل نیست.
- `KNOWN GAP` = باگ یا ناسازگاری شناخته‌شده که باید قبل از تأیید نهایی اصلاح شود.

---

## 0. Smoke / UI shell

### مسیر دستی
1. اپ را در موبایل باز کن.
2. در هیچ صفحه‌ای نباید horizontal scroll داشته باشی.
3. نوار بالای موبایل باید Logo + Role + Page title + Avatar داشته باشد.
4. پایین صفحه تب‌های Start / Plan / Zeit / Chat / Mehr باید قابل کلیک باشند.
5. `Mehr` را باز کن؛ تمام بخش‌های مخصوص Role باید نمایش داده شوند.
6. صفحه را refresh کن و با Back/Forward مرورگر جابه‌جا شو.

### انتظار
- منوی desktop در موبایل مخفی باشد.
- Tabbar موبایل در desktop مخفی باشد.
- Deep link صفحه بعد از refresh حفظ شود.
- Role guard اجازه ورود به view غیرمجاز ندهد.

**Status:** `AUTO + MANUAL`

---

## 1. Login / Authentication

### مسیر دستی
1. Logout کن.
2. با Admin لاگین کن.
3. Logout و با Worker لاگین کن.
4. Logout و با Client لاگین کن.
5. یک بار password اشتباه بزن.
6. از `Profil > Passwort ändern` پسورد اشتباه فعلی وارد کن.
7. پسورد جدید کمتر از 10 کاراکتر بزن.
8. پسورد معتبر تنظیم کن و دوباره Login کن.
9. `Kontolöschung anfragen` را بزن.

### انتظار
- password اشتباه خطای واضح بدهد.
- بعد از تغییر password، login مجدد لازم باشد.
- deletion request ثبت شود ولی داده قانونی بلافاصله پاک نشود.

**Status:** `AUTO`

### Social Login
- Google Login
- Apple Login

**Status:** `EXTERNAL` — نیازمند OAuth credential واقعی و callback production.

---

## 2. Mitarbeiter Activation / Invitation

### مسیر دستی
1. Admin > `Personal & Kunden`.
2. در `Zugänge & Aktivierung` وضعیت workerها را ببین.
3. برای یک Worker فاقد دسترسی `Einladen` را بزن.
4. اگر SMTP فعال نیست، لینک activation باید ساخته/کپی شود.
5. لینک `/aktivieren?...` را در private tab باز کن.
6. password و confirm متفاوت بزن؛ باید رد شود.
7. password معتبر بزن؛ activation کامل شود.
8. همان activation token را دوباره استفاده کن؛ باید رد شود.
9. `Offene Einladungen erstellen` را تست کن.

### انتظار
- endpointهای `portal-status` و `bulk-invite` با Worker detail route تداخل نداشته باشند.
- synthetic WIW email قابل دعوت نباشد.
- token منقضی/مصرف‌شده مجدد قابل استفاده نباشد.

**Status:** `AUTO` — regression باگ POST قبلی نیز پوشش داده شده است.

---

## 3. Personal & Kunden — Mitarbeiter

### مسیر دستی
1. `Personal & Kunden > Mitarbeiter`.
2. Worker جدید بساز:
   - Vorname / Nachname
   - E-Mail
   - Personalnummer
   - Beschäftigungsart
   - Monatsstunden
   - Tariflohn
   - Zulage
3. temporary password را ذخیره کن.
4. با همان Worker وارد شو.
5. در Admin جستجو با Name/Email/Personalnummer را تست کن.
6. Sort با Name و Nummer را تست کن.
7. Worker را `Deaktivieren` کن.
8. Worker غیرفعال نباید بتواند عادی وارد عملیات شود.
9. CSV Import با یک فایل صحیح و یک row خراب تست شود.

### انتظار
- E-Mail تکراری رد شود.
- Personalnummer تکراری رد شود.
- Worker نتواند Worker دیگر را edit کند.

**Status:** `AUTO` برای onboarding/login/permission؛ `MANUAL` برای UI و CSV فایل واقعی.

---

## 4. Personal & Kunden — Kunden

### مسیر دستی
1. `Personal & Kunden > Kunde`.
2. Company + customer number + contact email بساز.
3. temporary password را ذخیره کن.
4. با Client وارد شو.
5. Admin search/sort را تست کن.
6. Client را deactivate کن.
7. CSV Import مشتری را تست کن.

### انتظار
- customer number تکراری رد شود.
- contact email تکراری رد شود.
- Client فقط داده‌های شرکت خودش را ببیند.

**Status:** `AUTO + MANUAL`

---

## 5. Einsatzorte / Geofence

### مسیر دستی
1. Admin > `Personal & Kunden > Einsatzorte > Standort`.
2. Location با client، address، latitude، longitude و geofence radius بساز.
3. Location را در Shift استفاده کن.
4. Worker در زمان shift از داخل radius Clock-in کند.
5. مختصات خارج radius تست شود.
6. بدون location permission/missing lat-lng تست شود.
7. Location استفاده‌شده را delete کن؛ اگر protected است باید حذف خطرناک انجام نشود.

### انتظار
- داخل geofence قبول.
- خارج geofence خطا با distance/radius.
- location دارای Shift به‌صورت ناسالم delete نشود.

**Status:** `AUTO` برای Clock-in geofence path + `MANUAL` روی GPS واقعی.

---

## 6. Positionen

### مسیر دستی
1. Admin > `Personal & Kunden > Positionen > Position`.
2. Position مانند Servicekraft بساز.
3. Color و required skills را بررسی کن.
4. در Shift از Position استفاده کن.
5. Worker نباید بتواند Position جدید بسازد.

**Status:** `AUTO` permission + `MANUAL` CRUD UI.

---

## 7. Kundenauftrag / Aufträge

### مسیر Client
1. Client > `Aufträge`.
2. `Neuer Personalauftrag`.
3. Title, description, location, start/end, staff count را پر کن.
4. Save کن.
5. Client دیگری بساز و بررسی کن Auftrag اول را نمی‌بیند.

### مسیر Admin
1. Admin > `Aufträge`.
2. Auftrag مشتری را ببین.
3. Status و planning flow را بررسی کن.

### انتظار
- Worker نتواند Auftrag بسازد.
- Client خودکار به company خودش scope شود.

**Status:** `AUTO`

---

## 8. Dienstplanung / Staffing Demand / OpenShift

### مسیر دستی
1. Admin > `Dienstplanung`.
2. Shift/Demand جدید بساز با `required_count=3`.
3. Publish کن.
4. باید 3 slot باز داشته باشد.
5. Worker A > `Mein Dienstplan` / available shifts > Claim.
6. Worker B هم Claim کند.
7. Admin باید filled=2 / open=1 ببیند.
8. Worker A > Mine > `Freigeben` و Confirm dialog را تست کن.
9. Release بعد از تأیید باید slot را دوباره open کند.
10. Worker دیگر Claim کند.
11. Shift کامل شد؛ Claim اضافی باید رد شود.
12. Worker دارای overlap/unavailable را Claim/Assign کن؛ باید جلوگیری/هشدار شود.

### انتظار
- Staffing جدید بر مبنای `ShiftSlot` کار کند، نه legacy single worker.
- Available/Mine endpoints درست scope شوند.

**Status:** `AUTO + MANUAL`

---

## 9. Copy Week / Bulk Publish

### مسیر دستی
1. Admin > `Steuerzentrale`.
2. چند Draft Shift در یک هفته بساز.
3. `Woche kopieren` با source/target week اجرا کن.
4. اگر target برای Worker conflict دارد، کپی باید warning بدهد و به OpenShift تبدیل شود.
5. `Entwürfe veröffentlichen / Bulk Publish` اجرا کن.
6. Schedule را refresh کن.

**Status:** `MANUAL` + backend implementation checked.

---

## 10. Worker Dienstplan navigation

### مسیر دستی
1. Worker login.
2. Start > next shift.
3. `Plan`.
4. Available و Mine را جابه‌جا کن.
5. Refresh صفحه روی `?view=schedule`.
6. به `Zeit` برو، Back بزن، Forward بزن.
7. یک Admin-only deep link مثل `?view=people` بده.

### انتظار
- schedule حفظ شود.
- history درست باشد.
- worker به dashboard مجاز برگردد و people باز نشود.

**Status:** `AUTO` Playwright.

---

## 11. Zeiterfassung / Attendance

### مسیر دستی
1. Worker دارای shift نزدیک به زمان فعلی login کند.
2. `Zeit > Einstempeln`.
3. active timer نمایش داده شود.
4. دوباره Clock-in؛ باید رد شود.
5. Clock-out.
6. history باید entry را نمایش دهد.
7. Worker بدون shift Clock-in کند؛ باید رد شود.
8. خارج geofence تست شود.
9. entry بدون approval بساز و Admin exception inbox را ببین.
10. Timer بیش از حد طولانی بساز و Admin > `Timer beenden` با Reason اجرا کند.
11. Worker نباید timer را با admin endpoint ببندد.

**Status:** `AUTO + MANUAL GPS`

---

## 12. Zeitkorrektur

### مسیر دستی
1. Worker یک completed time entry باز کند.
2. `Korrektur` درخواست کند و clock-in/out + reason بدهد.
3. Admin > Attendance Exceptions.
4. Approve کن؛ زمان entry باید اصلاح و approved شود.
5. سناریوی دوم Reject را تست کن.
6. notification Worker را بررسی کن.

**Status:** `AUTO` برای request + approve + notification؛ `MANUAL` برای reject UI.

---

## 13. Urlaub / Abwesenheiten

### مسیر دستی
1. Worker درخواست Time Off بسازد.
2. Admin pending request را ببیند.
3. Approve.
4. درخواست دوم بساز و Reject کن.
5. Worker status را ببیند.

**Status:** `AUTO` approve path + `MANUAL` reject UI.

---

## 14. Verfügbarkeit

### مسیر دستی
1. Worker > `Verfügbarkeit & Tausch`.
2. Available=false برای یک بازه ثبت کن.
3. Admin برای همان بازه worker را برنامه‌ریزی کند/quality check بزند.
4. warning باید ظاهر شود.
5. Availability را delete کن.

**Status:** `AUTO` create/delete؛ `MANUAL` schedule-quality interaction.

---

## 15. Schichttausch

### مسیر دستی مطلوب
1. Worker A یک Shift claimed داشته باشد.
2. `Verfügbarkeit & Tausch > Tauschanfrage`.
3. Worker B را target انتخاب کند.
4. Worker B/Manager approve کند.
5. Worker assignment باید به B منتقل شود.
6. B اگر shift overlapping دارد approval باید رد شود.
7. Requester باید بتواند Cancel کند.

**Status:** `KNOWN GAP — HIGH`

**علت:** Staffing اصلی به `ShiftSlot` مهاجرت کرده، ولی عملیات swap هنوز ownership را از `Shift.worker` می‌سنجد. یک Shift که از مسیر جدید Claim شده است `Shift.worker` ندارد؛ بنابراین swap می‌تواند اشتباه رد شود. برای این مورد تست xfail اختصاصی اضافه شده است.

---

## 16. Steuerzentrale / Schedule Quality

### مسیر دستی
عمداً این مشکلات را بساز:
1. Shift ناقص (required > filled).
2. Shift overlap.
3. Worker unavailable assignment.
4. Monthly hours risk.
5. unapproved time entry.
6. long running timer.
7. Contract نزدیک expiry.
8. Worker master data ناقص.
9. integration failed.

### انتظار
Exception Center و Steuerzentrale باید موارد مربوط را نشان دهند.

**Status:** `KNOWN GAP — HIGH` برای بعضی محاسبات Operations.

**علت:** بخشی از `Steuerzentrale` هنوز `Shift.worker` legacy را برای conflict/overtime/coverage/upcoming shift می‌خواند، درحالی‌که staffing جدید assignment را در `ShiftSlot` ذخیره می‌کند. Admin Exception Center بخش slot-based را بهتر پوشش می‌دهد، اما Operations باید یکپارچه شود.

---

## 17. Contracts — Create / Readiness / PDF / Send / Sign

### مسیر دستی
1. Admin > `Verträge > Neuer Vertrag`.
2. Template + Worker/Client + start/end + variables را انتخاب کن.
3. required master data ناقص باشد؛ `Readiness` باید blocked باشد.
4. master data را کامل کن.
5. `PDF erstellen`.
6. قبل از Send یک field/title را edit کن؛ PDF قبلی باید invalidate شود و status Draft شود.
7. `Versenden`.
8. بعد از Send edit/delete/regenerate نباید مجاز باشد.
9. Worker/Client قرارداد را Sign کند.
10. Employer هم Sign کند.
11. بعد از تکمیل signature status `signed` شود.
12. امضای duplicate/overwrite رد شود.
13. Sent و unsigned را Cancel کن؛ حذف فیزیکی نشود.

**Status:** `AUTO`

---

## 18. Contract templates / 8 final documents

### مسیر دستی
1. Admin > Document Center.
2. باید 8 template موردنیاز را لیست کند.
3. DOCX source واقعی را Upload کن.
4. checksum/version ثبت شود.
5. Worker نباید source نصب کند.
6. Bundle import را تست کن.

**Status:** `AUTO` برای source lifecycle؛ `EXTERNAL/MANUAL` برای 8 فایل حقوقی نهایی.

تا زمانی که 8 فایل حقوقی تأییدشده واقعی نصب نشده باشند، production readiness این بخش نباید سبز تلقی شود.

---

## 19. Contract reminders

### مسیر دستی
1. Sent contract با signature باز ایجاد کن.
2. زمان reminder 3/7 day را شبیه‌سازی/endpoint manual run اجرا کن.
3. Worker و Admin حسب role باید notification بگیرند.
4. دوباره run کن؛ duplicate reminder نباید ساخته شود.

**Status:** `AUTO`

---

## 20. Dokumente

### مسیر دستی
1. Admin > `Dokumente > Dokument` upload.
2. Worker-specific file بساز.
3. Client-specific file بساز.
4. visibility: admin/worker/client/shared را تست کن.
5. Worker login؛ فقط فایل مجاز خودش.
6. Client login؛ فقط فایل مجاز شرکت خودش.
7. Worker خودش document upload کند؛ باید خودکار به own worker folder متصل شود.
8. delete/update توسط Worker نباید مجاز باشد.

**Status:** `AUTO + MANUAL file download/UI`

---

## 21. Lohnabrechnung / Payroll

### مسیر دستی
1. Admin > Dokumente > `Lohnabrechnung`.
2. Worker + period + gross/net + file را ثبت کن.
3. Worker login؛ فقط payroll خودش را ببیند.
4. Client نباید payroll کارکنان را ببیند.

**Status:** `MANUAL` scoping implementation موجود است؛ نیاز به E2E فایل واقعی دارد.

---

## 22. Nachrichten

### مسیر دستی
1. Admin > `Nachrichten > Unterhaltung`.
2. Worker را participant کن.
3. پیام بفرست.
4. Worker login و conversation را باز کن.
5. Worker پاسخ دهد.
6. Admin پیام را ببیند.
7. user خارج conversation نباید آن thread را ببیند/پیام بفرستد.
8. notification دریافت پیام را بررسی کن.

**Status:** `AUTO` notification backend + `MANUAL` کامل conversation permission/UI.

---

## 23. Notifications

### مسیر دستی
Notificationهای زیر را ایجاد کن:
- Shift assignment/claim
- Shift swap
- Time correction decision
- Contract sent/reminder
- Message

سپس `Steuerzentrale > Alle gelesen` را اجرا کن.

**Status:** `AUTO`

---

## 24. Ratings

### مسیر دستی
1. Client > `Mitarbeiter bewerten > Neue Bewertung`.
2. Worker + optional Shift انتخاب کن.
3. Overall/Pünktlichkeit/Qualität/Teamarbeit ثبت کن.
4. comment بنویس.
5. Save.
6. Worker ranking را بررسی کن.

### انتظار
- rating روی ranking_points اثر بگذارد.
- Client نباید بتواند داده شرکت دیگر را از API دریافت کند.

**Status:** `AUTO` basic rating/ranking update + `MANUAL` UI/assignment eligibility.

---

## 25. Ranking

### مسیر دستی
1. چند Rating متفاوت ایجاد کن.
2. Worker > `Ranking`.
3. Sort نزولی بر اساس points باشد.
4. رتبه اول visual highlight داشته باشد.

**Status:** `MANUAL`

---

## 26. Global Search

### مسیر دستی
Admin search کن:
- Worker name
- Client
- Order title
- Shift/client/location
- Contract

نتیجه را باز کن و navigation مقصد را بررسی کن.

Worker نباید endpoint global admin search را داشته باشد.

**Status:** `AUTO + MANUAL navigation`

---

## 27. CSV Reports

### مسیر دستی
Admin > Steuerzentrale/Reports:
- Timesheets CSV
- Schedule CSV
- Payroll Estimate CSV

### انتظار
- CSV دانلود شود.
- separator و encoding برای Excel آلمان قابل استفاده باشد.
- Worker/Client دسترسی مدیریتی export نداشته باشند.

**Status:** `AUTO` timesheets/payroll estimate + `MANUAL` schedule export/download browser.

---

## 28. Working Time Account

### مسیر دستی
1. TimeEntry تاییدشده برای Worker بساز.
2. `working-time sync` اجرا کن.
3. IST hours را با break مقایسه کن.
4. manual adjustment ثبت کن.
5. دوباره sync؛ manual adjustment نباید overwrite شود.
6. export و worker PDF را تست کن.
7. backup را اجرا کن.

**Status:** `AUTO` native source + persistence؛ `MANUAL` export/PDF/backup files.

---

## 29. Order Automation / Native cutover

### مسیر دستی
1. Admin > Steuerzentrale order automation.
2. متن یک سفارش staffing را paste کن.
3. Parse.
4. نتیجه را review کن.
5. Approve.
6. Local Order + Published Shift + required number of Slots باید ساخته شود.
7. WIW credential خام نباید برای عملیات native ضروری باشد.
8. اگر package قرارداد Sent/Signed دارد، replacement خودکار خطرناک باید blocked شود.

**Status:** `AUTO` backend native cutover.

### UI wording issue
در UI فعلی success message هنوز می‌تواند بگوید `OpenShifts wurden in When I Work erstellt.` درحالی‌که مسیر عملیاتی به A+ native منتقل شده است.

**Status:** `KNOWN GAP — MEDIUM (copy/text)`

---

## 30. WIW legacy migration / integration

### هدف
WIW دیگر source of truth تولید نیست، اما migration/history ابزارهای آن باقی مانده‌اند.

### مسیر دستی فقط در صورت نیاز migration
- status/discover
- final migration report
- import historical users/times
- verify reconciliation

**Status:** `AUTO` برای بخش migration data preservation؛ `EXTERNAL` برای live WIW API.

---

## 31. Production readiness

در `Steuerzentrale` موارد زیر را جداگانه بررسی کن:
- Google Login
- Apple Login
- E-Mail delivery
- Company legal data
- AÜG data
- 8 final contract templates
- Android signing
- iOS signing
- Store API credentials

**Status:** `EXTERNAL` برای credentialها و فایل‌های حقوقی. سبز بودن این موارد باید با secret واقعی production بررسی شود، نه با mock/test.

---

## 32. Store compliance

### مسیر دستی
1. Datenschutz صفحه عمومی.
2. Account deletion صفحه عمومی.
3. بدون Login قابل دسترسی باشند.
4. app registration برای business/client در iOS نباید public signup mechanism ایجاد کند؛ onboarding باید admin/invitation scoped باقی بماند.
5. Store review credentials flow را فقط با credential review تست کن.

**Status:** `AUTO` frontend smoke موجود + `MANUAL/EXTERNAL` App Store review.

---

## 33. Android / iOS device QA

روی حداقل یک Android و یک iPhone:
- install/update
- login persistence
- keyboard + modal
- safe area/notch
- status bar
- GPS permission
- background/foreground timer
- slow network
- offline recovery
- deep link activation
- download/open PDF
- back button Android
- rotation
- no horizontal overflow

**Status:** `MANUAL/EXTERNAL DEVICE`

---

# Known defects found during this audit

## QA-01 — Shift swap is not fully migrated to ShiftSlot
**Severity:** HIGH  
**Area:** Worker > Verfügbarkeit & Tausch  
**Effect:** Worker may successfully claim a modern slot but swap API can say the shift is not theirs.  
**Automated regression:** xfail test added.

## QA-02 — Operations/Steuerzentrale partly reads legacy Shift.worker
**Severity:** HIGH  
**Area:** Operations overview, upcoming shifts, conflicts, coverage, overtime/cost.  
**Effect:** slot-based assignments can be missing or risk counts can be wrong.  
**Automated regression:** xfail test added for Worker upcoming shifts.

## QA-03 — Native order automation still has WIW success copy
**Severity:** MEDIUM  
**Area:** Steuerzentrale > order automation  
**Effect:** UI says OpenShifts were created in When I Work although the backend native cutover creates them in A+.

---

# Recommended manual test sequence (do exactly in this order)

برای تست دستی نهایی، این زنجیره را یک بار بدون قطع کردن دیتا اجرا کن:

1. Admin Login
2. Create Worker A + Worker B
3. Create Client + Client Login credential
4. Create Position
5. Create Location + geofence
6. Client Login > Create Order
7. Admin > Create/Publish staffing demand with 2 slots
8. Worker A Claim
9. Worker B Claim
10. Worker A Clock-in/out
11. Worker A Correction Request
12. Admin Approve Correction
13. Worker A Time-Off Request
14. Admin Approve
15. Worker Availability=false
16. Worker Shift Swap — currently expected to expose QA-01 until fixed
17. Admin Exception Center / Steuerzentrale
18. Admin Create Contract
19. Fill missing master data
20. Generate PDF > Edit > Regenerate > Send
21. Worker Sign + Employer Sign
22. Upload Worker Document + Payroll
23. Admin Message Worker > Worker reply
24. Client Rate Worker
25. Worker Ranking
26. Download all three CSV reports
27. Change Password
28. Account deletion request
29. Logout/Login regression
30. Repeat main path on Android + iPhone

این sequence تقریباً تمام dependencyهای واقعی بین ماژول‌های اپ را همزمان تست می‌کند و برای تست دستی بعد از هر release مناسب است.

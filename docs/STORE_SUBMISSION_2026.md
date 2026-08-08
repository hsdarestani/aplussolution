# A+ Solution — Store Submission & Privacy Map (2026)

This document is the canonical release checklist for `de.aplussolution.workforce`.
It is intentionally conservative: store disclosures must match the actual app, even when a distribution method currently exempts a questionnaire.

## 1. Product classification

- App name: **A+ Solution**
- Package / Bundle ID: `de.aplussolution.workforce`
- Category: **Business**
- Production URL: `https://solution.smarbiz.sbs`
- API: `https://solution.smarbiz.sbs/api`
- Privacy policy: `https://solution.smarbiz.sbs/datenschutz`
- Account/data deletion: `https://solution.smarbiz.sbs/konto-loeschen`
- Support: `https://solution.smarbiz.sbs/support`
- Imprint: `https://solution.smarbiz.sbs/impressum`
- Audience: internal A+ Solution workforce (employees, dispatch/management). Not a consumer service.
- Public self-registration: **No**. Accounts are created by administration or activated through a personal invitation.
- Ads: **No**
- Advertising tracking: **No**
- Background location: **No**
- Foreground precise location: **Yes, only when the employee actively clocks in/out and the assigned worksite requires geofence validation.**

## 2. Recommended distribution

### Google Play

Preferred: **Managed Google Play private app** restricted to the A+ Solution organization.
Private apps are not publicly discoverable. If the organization is not yet configured for Managed Google Play/EMM, the same build can be submitted through a normal Play Console track, but then the full Data Safety and public store-listing requirements apply.

### Apple

Preferred: **Private Custom App** assigned to the A+ Solution organization in Apple Business Manager.
This keeps the app visible only to the specified organization. Apple still performs App Review and must be able to log in using a generic test account with sanitized sample data.

Fallback for employee-owned/unmanaged devices: Apple **Unlisted App** distribution can be requested after the app is submitted to App Review. An unlisted app is hidden from search but anyone with the direct link can download it; the app's own access control therefore remains essential.

> Distribution choice is a one-time bootstrap decision. Do not switch a reviewed Apple app between public and private distribution casually: Apple requires a new app record for public↔private changes.

## 3. Access model — answer consistently everywhere

Store reviewers must be told:

> A+ Solution is an internal workforce-management app for A+ Solution GmbH. There is no public registration. Employee and manager accounts are provisioned by company administration or activated using a personal invitation. Google/Apple sign-in, when enabled, only authenticates an already provisioned A+ Solution account and never creates a new account.

For reviewer access, create a **dedicated sanitized review user**. Never give Apple or Google a real employee account.

Suggested review notes:

```text
A+ Solution is an internal workforce-management app used by employees and management of A+ Solution GmbH. There is no public sign-up.

Reviewer access:
Email: [REVIEW_EMAIL]
Password: [REVIEW_PASSWORD]

The supplied reviewer account contains synthetic sample data only.

Location permission is requested only when the reviewer actively uses clock-in/clock-out. The current foreground location is used to validate the assigned worksite/geofence and is stored with that time entry. The app does not use background location, advertising tracking, or ads.

Privacy: https://solution.smarbiz.sbs/datenschutz
Support: https://solution.smarbiz.sbs/support
Deletion: https://solution.smarbiz.sbs/konto-loeschen
```

## 4. Google Play — App content answers

Use these answers when the app is not exempt as a Managed Google Play private app.

### App access

- Is all functionality available without special access? **No**
- Access restriction: **Organization account required**
- Instructions: use the dedicated reviewer credentials from Review Notes. State explicitly that self-registration does not exist.

### Ads

- Contains ads: **No**

### Target audience / children

- The app is **not designed for children** and is an employment/workforce tool.
- Select only age groups that match the company's real employee population. If all intended users are adults, select **18 and over** only.
- Do not opt into Families/children features.

### Account creation / deletion

- Does the app allow users to create an account in the app? **No**
- Accounts are company-provisioned/invitation-based.
- The app nevertheless supports an in-app deletion request under **Mein Profil → Kontolöschung anfragen**, and exposes the public deletion page above.

### Data Safety — conservative data map

If a Data Safety form is required, disclose at least the categories actually used by the current production feature set:

| Google data category | Collected | Shared | Purpose | Notes |
| --- | --- | --- | --- | --- |
| Personal info: name | Yes | Normally no | App functionality / account management | Employee identity |
| Personal info: email address | Yes | Normally no | Account management / authentication | Also used for optional SSO |
| Personal info: phone number | Yes, when stored | Normally no | Workforce administration | Company master data |
| Personal info: address | Yes, when stored | Normally no | Workforce/contract administration | Employee master data |
| User IDs | Yes | No | Authentication / authorization | Internal account ID |
| Precise location | Yes | No | App functionality | Only foreground clock-in/out; no background location |
| Financial info | Yes, for relevant employees | No | Payroll/workforce administration | Hourly rate, payroll/bank-related master data |
| Messages | Yes | No | App functionality | Internal conversations |
| Files and documents | Yes | No | App functionality | Contracts, payroll PDFs, employee/company documents |
| Photos/images | Possible via uploaded files | No | App functionality | Do not claim camera capture unless a camera feature is added |
| Other user-generated content | Yes | No | App functionality | Signatures, notes, availability/correction requests |

Data is transmitted over HTTPS in production.

**Sharing:** service-provider processing on behalf of A+ Solution is not automatically the same as store-defined data “sharing”. Before answering “No data shared”, verify that hosting, email and optional AI providers are contractually used only as processors/service providers and that no provider uses the data for its own advertising or unrelated purposes. If that changes, update both the store form and privacy policy before release.

### Sensitive data disclosure

Do not request medical diagnoses in absence notes. The UI and policy must make clear that diagnoses are unnecessary. If the product is changed to intentionally collect health/diagnosis information, update Google Data Safety and Apple App Privacy before shipping that change.

## 5. Apple App Store Connect — App Privacy

App Privacy must reflect the union of data that the shipped app intentionally collects. Mark the following as **linked to the user** and **not used for tracking**, when applicable:

| Apple data type | Collect | Linked | Tracking | Primary purpose |
| --- | --- | --- | --- | --- |
| Contact Info — Name | Yes | Yes | No | App Functionality |
| Contact Info — Email Address | Yes | Yes | No | App Functionality / authentication |
| Contact Info — Phone Number | When stored | Yes | No | App Functionality |
| Contact Info — Physical Address | When stored | Yes | No | Workforce administration |
| Financial Info — Other Financial Info | When applicable | Yes | No | Payroll/workforce administration |
| Financial/Payment-related bank details | When applicable | Yes | No | Payroll administration |
| Location — Precise Location | Yes | Yes | No | Clock-in/out geofence validation |
| Identifiers — User ID | Yes | Yes | No | Authentication / authorization |
| User Content — Emails or Text Messages | Yes | Yes | No | Internal messaging |
| User Content — Other User Content | Yes | Yes | No | Documents, notes, signatures, requests |
| Photos or Videos | Only if image upload is enabled/used | Yes | No | App Functionality |
| Other Data | If required for stored signature/security evidence | Yes | No | Security / legal evidence |

Do **not** declare advertising, third-party advertising, cross-app tracking or background location: the current app does not implement them.

If an analytics/crash/advertising SDK is added later, the privacy labels must be reviewed before the next build is submitted.

## 6. Native permission declarations

The native projects are generated during the build. Run after `cap sync`:

```bash
node scripts/prepare-native.mjs android
node scripts/prepare-native.mjs ios
```

The script intentionally configures only:

- Android `ACCESS_COARSE_LOCATION`
- Android `ACCESS_FINE_LOCATION`
- iOS `NSLocationWhenInUseUsageDescription`

It intentionally does **not** add background-location, camera, broad storage, photo-library or advertising-tracking permissions.

If a future feature actually needs one of those permissions, add the feature-specific disclosure, update the privacy policy/store labels, and then add the permission.

## 7. GDPR / employee privacy implementation rules

- Employee data processing must be limited to what is required for the employment/workforce purpose.
- Employee consent should not be treated as the default legal basis merely because the OS asks for a permission; employment-data processing is assessed primarily under the applicable employment/legal bases.
- Precise location is collected only on a deliberate clock-in/out action and never continuously in the background.
- Do not ask users to put a medical diagnosis into absence free-text fields.
- Do not send payroll, employee files, sickness details, IDs, bank/tax/social-security data to the optional AI order parser.
- Every new SDK or external processor must be assessed before release and reflected in both the privacy policy and store declarations.
- Account/data deletion requests must be processed, while records subject to mandatory employment/tax/commercial/legal retention may be retained only for the applicable period and purpose.

## 8. Store metadata

### German short description

```text
Interne Dienstplanung, Zeiterfassung und Dokumente für A+ Solution.
```

### German full description

```text
A+ Solution ist die interne Workforce-App der A+ Solution GmbH für freigeschaltete Mitarbeiter, Disposition und Management.

Die App bündelt Dienstplanung, Arbeitszeiterfassung, Verfügbarkeiten, Verträge, Dokumente, Lohnunterlagen, interne Nachrichten und weitere betriebliche Abläufe in einem geschützten Zugang.

Wichtig: Es gibt keine öffentliche Registrierung. Ein Zugang wird ausschließlich von der A+ Solution GmbH bereitgestellt oder über eine persönliche Einladung aktiviert.

Bei standortgebundenen Einsätzen kann die App beim aktiven Ein- und Ausstempeln den aktuellen Standort zur Prüfung des vorgesehenen Einsatzortes verwenden. Es findet keine Hintergrundortung statt.
```

### Keywords / positioning

Use factual business terms only: `Dienstplanung, Zeiterfassung, Workforce, Mitarbeiter, Schichten, Dokumente, A+ Solution`.
Do not market the app as a public staffing marketplace or consumer service.

## 9. Pre-submit release gate

Before pressing Submit:

- Production privacy/support/deletion URLs return HTTP 200 without login.
- No placeholder legal text remains on those routes.
- Reviewer account is active and contains synthetic data.
- Reviewer can log in without access to real employee records.
- Location prompt text matches the actual foreground-only behavior.
- App works when location is denied except for the specific geofenced clock action that requires it.
- No public sign-up button, route or store copy suggests public account creation.
- Store screenshots contain no real employee, payroll, bank, tax, health or client-confidential data.
- Apple/Google OAuth, if visible, is production-configured and only authenticates pre-existing accounts.
- Store privacy declarations match this document and the production build.
- Signing identifiers remain `de.aplussolution.workforce` on both platforms.

## 10. Change-control rule

Any future change involving analytics SDKs, crash SDKs, push-notification providers, camera/microphone, contacts, background location, health information, advertising, payments, new AI processors or public account creation requires a privacy/store review before release.

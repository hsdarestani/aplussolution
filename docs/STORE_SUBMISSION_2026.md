# A+ Solution — Store Submission & Privacy Map (2026)

Canonical release checklist for `de.aplussolution.workforce`.
Store declarations must describe the shipped production build.

## 1. Product classification

- App name: **A+ Solution**
- Category: **Business**
- Android package: `de.aplussolution.workforce`
- iOS bundle ID: `de.aplussolution.workforce`
- Production: `https://solution.smarbiz.sbs`
- API: `https://solution.smarbiz.sbs/api`
- Privacy: `https://solution.smarbiz.sbs/datenschutz`
- Account/data deletion: `https://solution.smarbiz.sbs/konto-loeschen`
- Support: `https://solution.smarbiz.sbs/support`
- Imprint: `https://solution.smarbiz.sbs/impressum`
- Audience: A+ Solution employees, dispatch and management; not a consumer account service.
- Distribution: **public Google Play production listing + public Apple App Store distribution**.
- Public self-registration: **No**.
- Store build login: **company-provisioned email/password only**.
- Ads: **No**.
- Advertising/cross-app tracking: **No**.
- Background location: **No**.
- Foreground location: **Yes, only when a worker deliberately clocks in/out for a geofenced worksite.**

## 2. Distribution choice

The current release goal is visibility under the A+ Solution developer profiles on both stores.

- **Google Play:** public production distribution. Do not configure the package as a Managed Google Play private app.
- **Apple App Store:** **Public Distribution**. Do not use Private Custom App distribution and do not request Unlisted distribution for this release.
- The public store listing does not create or grant an A+ Solution account. Operational access remains restricted to company-provisioned users.

## 3. Access model and reviewer accounts

There is no user registration. Accounts are created by A+ Solution administration or activated by a personal invitation. The store build exposes only the organization email/password login.

Create dedicated reusable reviewer users with synthetic/sample data only. Never give a store reviewer access to real employee, payroll, bank, tax, health, client-confidential or production-sensitive records. Reviewer credentials must not require OTP/2FA and should work regardless of reviewer location.

Suggested Review Notes:

```text
A+ Solution is the official workforce application of A+ Solution GmbH. The application is publicly distributed on the App Store and Google Play, while operational access is restricted to employees and management whose accounts are provisioned by A+ Solution GmbH. There is no public self-registration.

Reviewer access:
Manager: [REVIEW_MANAGER_EMAIL] / [REVIEW_MANAGER_PASSWORD]
Worker: [REVIEW_WORKER_EMAIL] / [REVIEW_WORKER_PASSWORD]

Both reviewer accounts are reusable, do not require OTP/2FA, work regardless of reviewer location, and contain synthetic data only.

Location permission is requested only when the reviewer actively uses clock-in/clock-out for a worksite that requires location validation. The app does not use background location, advertising tracking, or ads.

Privacy: https://solution.smarbiz.sbs/datenschutz
Support: https://solution.smarbiz.sbs/support
Deletion: https://solution.smarbiz.sbs/konto-loeschen
```

## 4. Google Play — App Content

### App access

- All functionality available without special access: **No**
- Restriction: **Organization/company account required**
- Provide the reusable synthetic reviewer credentials and the instructions above.

### Ads

- Contains ads: **No**

### Target audience

- Employment/workforce/business app; not designed for children.
- If the intended workforce is adults only, choose **18 and over**.
- Do not opt into Families/children features.

### Account creation/deletion

- Users can create an account in the app: **No**
- Accounts are company-provisioned/invitation-based.
- The app still provides `Mein Profil → Kontolöschung anfragen` plus the public deletion page.

### Data Safety — conservative production map

Because Android requests both `ACCESS_COARSE_LOCATION` and `ACCESS_FINE_LOCATION`, declare both Google location data types when completing Data Safety.

| Google data category | Collected | Shared | Purpose / note |
| --- | --- | --- | --- |
| Personal info — Name | Yes | Normally no | Employee identity / app functionality |
| Personal info — Email address | Yes | Normally no | Authentication / account management |
| Personal info — Phone number | When stored | Normally no | Workforce administration |
| Personal info — Address | When stored | Normally no | Workforce/contract administration |
| User IDs | Yes | No | Authentication / authorization |
| Approximate location | Yes | No | Foreground clock-in/out location validation only; possible when Android grants coarse location |
| Precise location | Yes | No | Foreground clock-in/out geofence validation only |
| Financial info | When applicable | No | Payroll/workforce administration; e.g. pay/bank-related master data |
| Health and fitness — Health info | When sickness absence is used | No | Sickness/absence status for workforce administration; no diagnosis is required |
| Messages | Yes | No | Internal messaging |
| Files and documents | Yes | No | Contracts, payroll PDFs and company/employee documents |
| Photos/images | If uploaded as a file | No | App functionality; the app does not request camera permission |
| Other user-generated content | Yes | No | Signatures, notes, availability and correction requests |

Production transport is HTTPS.

Before answering “No data shared”, confirm all external vendors are acting only as processors/service providers for the declared purpose and do not use the data for their own advertising or unrelated purposes. If that changes, update the form and privacy policy before the next release.

Sickness absence can reveal health information. Declare it conservatively as health information. Users should not enter diagnoses or unnecessary medical details in optional free-text fields.

## 5. Apple App Privacy

Declare the data intentionally collected by the shipped build as **linked to the user** and **not used for tracking**, where applicable:

| Apple data type | Collect | Linked | Tracking | Purpose |
| --- | --- | --- | --- | --- |
| Contact Info — Name | Yes | Yes | No | App Functionality |
| Contact Info — Email Address | Yes | Yes | No | Authentication / App Functionality |
| Contact Info — Phone Number | When stored | Yes | No | App Functionality |
| Contact Info — Physical Address | When stored | Yes | No | Workforce administration |
| Financial Info — Other Financial Info | When applicable | Yes | No | Payroll/workforce administration |
| Location — Precise Location | Yes | Yes | No | Foreground clock-in/out location validation |
| Identifiers — User ID | Yes | Yes | No | Authentication / authorization |
| Health & Fitness — Health | When sickness absence is used | Yes | No | Absence/workforce administration; not HealthKit |
| User Content — Emails or Text Messages | Yes | Yes | No | Internal messaging |
| User Content — Other User Content | Yes | Yes | No | Documents, notes, signatures and requests |
| Photos or Videos | If image upload is used | Yes | No | App Functionality |
| Other Data | If stored as signature/security evidence | Yes | Yes | No tracking; security/legal evidence |

Do not declare advertising, third-party advertising, cross-app tracking or background location; the current build does not implement them.

If any analytics/crash SDK, push provider, advertising SDK, camera/microphone feature, contacts access, background location, payment SDK or new AI processor is added later, review the privacy labels before shipping that build.

## 6. Native permissions and platform build requirements

After each `cap sync`, the store build runs:

```bash
node scripts/prepare-native.mjs android
node scripts/prepare-native.mjs ios
```

Approved native permissions/declarations:

- Android `ACCESS_COARSE_LOCATION`
- Android `ACCESS_FINE_LOCATION`
- Android `compileSdkVersion = 36`
- Android `targetSdkVersion = 36`
- iOS `NSLocationWhenInUseUsageDescription`
- iOS `ITSAppUsesNonExemptEncryption = false`

Intentionally not added:

- background location
- camera
- broad storage/photo-library permission
- advertising tracking

A new permission may only be added together with the corresponding product need, privacy text and store declaration.

## 7. GDPR / employee-data rules

- Process employee data only for the required employment/workforce purpose and applicable legal obligations.
- Do not treat OS permission consent as the default legal basis for employment processing; assess employee processing under the applicable employment/GDPR rules.
- Collect location only on the deliberate clock-in/out action; never continuously in the background.
- A sickness request does not require a medical diagnosis. Do not ask workers to enter diagnosis details.
- Never send payroll files, employee files, sickness details, identity documents, bank/tax/social-security data to the optional AI order parser.
- Account/data-deletion requests must be processed; records subject to mandatory employment, tax, commercial, social-security or legal retention may remain only for the applicable purpose and period.
- Assess every new SDK/processor before release and update both Datenschutz and store declarations where necessary.

## 8. Store metadata

### Short description

```text
Interne Dienstplanung, Zeiterfassung und Dokumente für A+ Solution.
```

### Full German description

```text
A+ Solution ist die offizielle Workforce-App der A+ Solution GmbH für freigeschaltete Mitarbeiter, Disposition und Management.

Die App bündelt Dienstplanung, Arbeitszeiterfassung, Verfügbarkeiten, Verträge, Dokumente, Lohnunterlagen, interne Nachrichten und weitere betriebliche Abläufe in einem geschützten Zugang.

Die App ist öffentlich im Store verfügbar. Für die Nutzung der betrieblichen Funktionen ist jedoch ein von der A+ Solution GmbH bereitgestelltes Konto erforderlich. Es gibt keine öffentliche Registrierung.

Bei standortgebundenen Einsätzen kann die App beim aktiven Ein- und Ausstempeln den aktuellen Standort zur Prüfung des vorgesehenen Einsatzortes verwenden. Es findet keine Hintergrundortung statt.
```

Keywords/positioning: `Dienstplanung, Zeiterfassung, Workforce, Mitarbeiter, Schichten, Dokumente, A+ Solution`.
Do not describe the app as a public staffing marketplace or imply that downloading it creates an employee account.

## 9. Publisher build configuration

The exact self-hosted Publisher configuration is documented in `docs/PUBLISHER_BUILD_CONFIG.md`.

For the first-ever Google Play upload, use the Publisher-generated Android upload key. Do not establish the Play package using a different signing/upload key first.

Publisher release metadata must drive Android `versionName`/`versionCode` and iOS `MARKETING_VERSION`/`CURRENT_PROJECT_VERSION`, so every Store upload gets a unique build number.

## 10. Pre-submit gate

Before Submit:

- Privacy, support, deletion and imprint routes are public without login.
- No placeholder legal text remains.
- Reviewer users are active and contain synthetic data only.
- Reviewer accounts work without OTP/2FA and without dependence on a specific reviewer location.
- Reviewer can log in with company credentials; there is no public signup/social-login surface in the store build.
- Location text matches foreground-only behavior.
- App remains usable when location is denied except for a clock action that actually requires location validation.
- Screenshots contain no real employee, payroll, bank, tax, health or client-confidential data.
- Store declarations match this document and the exact production build.
- Android/iOS identifiers remain `de.aplussolution.workforce`.
- Google Play distribution is public production and Apple distribution method is Public.

## 11. Change-control rule

Any future change involving analytics/crash SDKs, push providers, camera/microphone, contacts, background location, health/diagnosis collection, advertising, payments, new AI processors or public account creation requires a privacy/store review before release.

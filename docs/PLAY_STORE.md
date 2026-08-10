# Headnote on the Google Play Store

This is the end-to-end guide to get **Headnote** live on the Play Store as an
Android app. The app is a **Trusted Web Activity (TWA)** — a thin, official
Google wrapper that runs `headnote.in` full-screen with no browser address bar.
Users get a real installable app from Play; every fix you ship to the website
appears instantly in the app with **no re-submission**. This is the correct,
lowest-maintenance path for a web app and is exactly how apps like Twitter Lite
and many others shipped.

---

## Part A — What is already done (in this repo)

All the web-side plumbing a TWA needs is built and verified:

| Item | Where | Status |
|---|---|---|
| Web App Manifest | `static/manifest.webmanifest`, served at `/manifest.webmanifest` | ✅ |
| Service worker (installability) | `static/sw.js`, served at `/sw.js` with `Service-Worker-Allowed: /` | ✅ |
| Offline fallback page | `static/offline.html` | ✅ |
| Digital Asset Links | `static/assetlinks.json`, served at `/.well-known/assetlinks.json` | ✅ (fingerprint pending — Step 4) |
| App icons (192/512, maskable) | `static/icons/` | ✅ |
| Manifest + SW linked in app | `static/index.html`, `static/landing.html` | ✅ |
| Play Store listing icon (512×512) | `static/icons/play-store-icon-512.png` | ✅ |
| Feature graphic (1024×500) | `static/icons/feature-graphic-1024x500.png` | ✅ |
| Bubblewrap TWA config | `playstore/twa-manifest.json` | ✅ |
| Store listing copy | this doc, Part D | ✅ |

**Package name (do not change once published): `in.headnote.app`**

### Ship the web changes first
Merge this branch and deploy to Railway so the endpoints are live on
`https://headnote.in` **before** you build the Android app. Verify:

```
curl -s https://headnote.in/manifest.webmanifest        # JSON manifest
curl -s https://headnote.in/sw.js -I                     # 200, Service-Worker-Allowed: /
curl -s https://headnote.in/.well-known/assetlinks.json  # JSON (fingerprint still placeholder — fine for now)
```

---

## Part B — One-time prerequisites (you must do these)

These need a human with a Google account, a card, and an ID — I can't do them.

1. **Google Play Developer account** — https://play.google.com/console/signup
   - One-time **$25** fee.
   - **Identity verification is now mandatory.** You'll upload a government ID
     and (for an individual account) confirm name/address. Verification can take
     anywhere from a few hours to a few days. **Start this today** — it's the
     long pole.
   - Choose **Organization** account type if Headnote is a registered
     company/LLP. This matters a lot — see the testing rule below.

2. **⚠️ The 12-tester / 14-day rule (the real "why it's not live tonight")**
   Google requires **new *personal* developer accounts** to run a **closed test
   with at least 12 testers, opted in continuously for 14 days**, before you can
   apply for production (public) access. There is no way around it for a personal
   account. **Organization accounts are exempt.**
   - Practical impact: from a fresh personal account, plan **~2–3 weeks** to
     public launch. You can start the 14-day clock the day the build is ready.
   - Line up 12 testers now (advocates, campus reps, friends) with Google
     accounts — you'll add their emails to a closed testing track.

3. **A computer with the build toolchain** (only if you use the CLI path in
   Step 3, Option 2). The easier Option 1 (PWABuilder) needs nothing but a
   browser.

---

## Part C — Build & submit (step by step)

### Step 1 — Confirm the site is installable
On an Android phone, open `https://headnote.in/app` in Chrome → three-dot menu
should offer **"Install app" / "Add to Home screen"** as an *app* (not just a
shortcut). If it does, the manifest + service worker are correct.

### Step 2 — Create the app in Play Console
Play Console → **Create app**:
- App name: **Headnote**
- Default language: **English (India) – en-IN**
- App or game: **App**
- Free or paid: **Free** (billing is handled in-web; see the note in Part E)
- Accept the declarations.

### Step 3 — Generate the signed Android bundle (`.aab`)

Pick ONE path.

**Option 1 — PWABuilder (easiest, no local tools) — recommended**
1. Go to https://www.pwabuilder.com and enter `https://headnote.in/app`.
2. It reads the manifest, scores the PWA, then **Package for stores → Android**.
3. Settings to set (match `playstore/twa-manifest.json`):
   - Package ID: `in.headnote.app`
   - App name: `Headnote`, Launcher name: `Headnote`
   - Host: `headnote.in`, Start URL: `/app`
   - Theme color `#ffffff`, Background `#ffffff`
   - **Signing key: "Let PWABuilder generate a new signing key"** — download and
     **back up the keystore + the passwords it shows you.** Losing this key means
     you can never update the app again.
4. Download the zip. It contains the **`.aab`** (upload to Play) and a
   **`signing-key-info` / `assetlinks.json`** with your **SHA-256 fingerprint**.
   → go to Step 4.

**Option 2 — Bubblewrap CLI (repeatable, scriptable)**
Requires **Node 18+** (you have Node 24 ✅) and a **JDK 17** (⚠️ `java` is not
installed on your Mac right now — `brew install openjdk@17`). Then:
```bash
npm i -g @bubblewrap/cli
cd playstore
bubblewrap init --manifest https://headnote.in/manifest.webmanifest
# When prompted, accept the values already in twa-manifest.json (packageId
# in.headnote.app, host headnote.in, start /app). Let it install the Android SDK.
bubblewrap build
```
`bubblewrap build` produces **`app-release-bundle.aab`** (upload to Play) and
prints the **SHA-256 fingerprint** of your signing key. Back up the generated
`android.keystore` and its passwords. → Step 4.

### Step 4 — Wire up Digital Asset Links (removes the URL bar)
This is what makes it feel like a native app instead of a webpage.

1. In **Play Console → your app → Test and release → Setup → App signing**, copy
   the **SHA-256 certificate fingerprint** of the **App signing key** (Google
   re-signs your app, so use *Google's* fingerprint here, not only your upload
   key). If you enroll in Play App Signing (default), Play shows this after your
   first upload.
2. Paste it into `static/assetlinks.json`, replacing
   `REPLACE_WITH_PLAY_APP_SIGNING_SHA256_FINGERPRINT`. Format is
   `AA:BB:CC:...` (colon-separated hex). You can list **multiple** fingerprints
   (e.g. your local upload key *and* Google's) — add both to the array.
3. Deploy. Verify: `curl https://headnote.in/.well-known/assetlinks.json` shows
   the real fingerprint, and test with Google's validator:
   https://developers.google.com/digital-asset-links/tools/generator
4. If you skip/botch this, the app still works but shows a Chrome address bar at
   the top — a dead giveaway that it's a web wrapper. Get it right.

### Step 5 — Fill the Play Console listing
Use the copy in **Part D**. Upload:
- **App icon**: `static/icons/play-store-icon-512.png` (512×512)
- **Feature graphic**: `static/icons/feature-graphic-1024x500.png` (1024×500)
- **Phone screenshots**: minimum **2**, ideally **4–8**. Capture from the TWA on
  a phone/emulator, or from `headnote.in/app` in Chrome on a phone (portrait,
  1080×1920). Good shots: research result with verified citations, a bail draft
  in the editor, the sections (IPC→BNS) finder, My Cases.

### Step 6 — Complete the mandatory Play forms
Every app must clear these before it can publish (answers in Part D):
- **Privacy policy URL**: `https://headnote.in/privacy`
- **Data safety** form (what you collect / share)
- **Content rating** questionnaire → will come back "Everyone"
- **Target audience & content**: 18+ (professional tool for advocates)
- **Ads**: No ads
- **Government/financial/health** declarations: No
- **App access**: the app requires login → provide **demo credentials** for the
  reviewer (create a throwaway account and paste the email+password in
  "App access" so Google's reviewer can get past your sign-in wall — apps get
  rejected when reviewers can't log in).
- **App category**: Productivity (secondary: Business)
- **Contact details**: your support email + `headnote.in`.

### Step 7 — Closed test (required for new personal accounts)
- Create a **Closed testing** track → upload the `.aab`.
- Add your **12+ testers'** Google emails to the track; send them the opt-in link.
- They must **install and keep** the app for **14 continuous days**.
- Personal account: after 14 days with 12+ active testers, Play unlocks a
  **"Apply for production"** button. Organization account: skip straight to
  production.

### Step 8 — Production release → review → live
- Promote the build to the **Production** track.
- Submit for review. First review typically **1–7 days**.
- On approval, Headnote is **live on the Play Store**. 🎉

---

## Part D — Store listing copy (ready to paste)

**App name (30 char max)**
```
Headnote
```

**Short description (80 char max)**
```
AI co-counsel for advocates: verified case-law research + court-ready drafting.
```

**Full description (4000 char max)**
```
Headnote is an AI co-counsel built for India's advocates. Research verified case
law and draft court-ready pleadings in Hindi and English, from the district
court to the High Court and Supreme Court, across every State and Union
Territory.

WHAT HEADNOTE DOES

• Court-ready drafting of 40+ Indian litigation formats — bail and anticipatory
  bail, discharge, revision, appeal, maintenance (Section 125 CrPC / Section 144
  BNSS), domestic violence, recovery of money (Order XXXVII CPC), civil
  defamation, vakalatnama, complaints and replies — in Hindi and English.

• Case-law research over 3.5 crore+ Indian judgments. Every citation is verified
  against its source. Headnote never fabricates case law.

• IPC to BNS, CrPC to BNSS, and Evidence Act to BSA section finder for the 2024
  criminal codes.

• Document Vault — OCR of scanned and handwritten legal paper into searchable,
  structured text you can read and search side by side with the original page.

• Voice-first drafting — dictate in Hindi or English, hands-free.

• Case memory — record a client conversation and get a structured work-product
  note with facts, issues and next steps, ready to hand off into a draft.

BUILT FOR THE INDIAN BAR
Headnote is made for practising advocates, especially the vernacular
district-court bar that works primarily in Hindi. Solo practitioners and small
chambers get the leverage of a diligent junior — one that drafts, researches and
remembers.

VERIFIED, NOT INVENTED
The core promise: citations are checked against their source, and the product
never invents case law or your client's facts. What you can trust, you can file.

PRICING
Start with a free 3-day demo — no card required. Then 599 rupees a month or 5,999
rupees a year. Unlimited use, no auto-renew.

Headnote is a professional research and drafting tool for advocates. It does not
provide legal advice and is not a substitute for a lawyer's professional
judgement.
```

**App category:** Productivity · **Tags:** legal, productivity, business
**Contact email:** (your support email) · **Website:** https://headnote.in
**Privacy policy:** https://headnote.in/privacy

### Data safety form — suggested answers
Confirm against your actual code before submitting.
- **Does the app collect or share user data?** Yes (collect), No third-party sale.
- **Data collected:** Email address & name (account), app activity (drafts,
  searches you store), possibly documents the user uploads (for OCR/vault).
- **Purpose:** App functionality, account management. Not for ads.
- **Is data encrypted in transit?** Yes (HTTPS).
- **Can users request deletion?** Yes — provide the deletion path / contact.
- **Uploaded legal documents:** disclose that users may upload documents which
  are processed to provide the service.

### Content rating questionnaire
- No violence, sexual content, profanity, gambling, or drugs → result:
  **Everyone / PEGI 3**.

---

## Part E — Play policy notes to not get rejected

- **Login wall:** you MUST give the reviewer working demo credentials in
  *App access*, or it's an instant rejection.
- **Payments:** Headnote takes payment on the website, not via Google Play
  Billing. This is generally allowed **only** because Headnote is not selling
  "digital content consumed in the app" in the Play-Billing sense and payment
  happens on your own web domain. To stay safe: **do not add any in-app
  "Buy/Subscribe" button that charges through your own flow inside the TWA that
  Google could read as bypassing Play Billing.** Keep upgrade prompts pointing to
  the web account page, and keep the app usable in its free/demo state. If Google
  flags it, the cleanest fix is to add Play Billing for the subscription. Watch
  this one.
- **Minimum functionality / "webview" rejections:** a proper TWA with valid
  Digital Asset Links (Step 4) is explicitly allowed and is NOT treated as a
  low-quality webview. Getting assetlinks right is what keeps you on the right
  side of this policy.
- **Target API level:** Play requires a recent target API level. Bubblewrap /
  PWABuilder default to a compliant one; just use a current version of the tool.

---

## Part F — Timeline (realistic)

| From a NEW personal account | From an Organization account |
|---|---|
| Day 0: sign up + ID verification (start now) | Day 0: sign up + ID verification |
| Day 1–3: ID verified | Day 1–3: ID verified |
| Day 1: build .aab, create listing, upload to closed test | Day 1: build .aab, create listing |
| Day 1–15: 12 testers keep it installed 14 days | (exempt) |
| Day 15: apply for production | Day 3: submit to production |
| Day 15–22: review → **LIVE** | Day 3–10: review → **LIVE** |

**Bottleneck = ID verification + (for personal accounts) the 14-day test.** If
Headnote is a registered entity, use an **Organization** account to skip the
14-day rule and cut ~2 weeks off launch.

---

## Part G — Updating the app later
Because it's a TWA, **99% of updates need nothing** — you ship to `headnote.in`
and the app reflects it. You only rebuild and re-upload a new `.aab` when you
change: the package name, app name/icon, the TWA config, or to bump the target
API level for Play compliance. When you do, increment `appVersionCode` in
`playstore/twa-manifest.json` and re-run the build with the **same keystore**.

# Service Audit: 2026-08-05

## Summary

The FastAPI service has clear feature boundaries, automatic SQLite schema updates, a hybrid i18n structure, and verified user flows for login, pronunciation evaluation, video learning, and voice calls.

Before treating it as a public production service, prioritize authorization, session security, untrusted content rendering, and external URL restrictions.

## Immediate Fixes

### Session logout does not revoke tokens

- **Files:** `backend/routes/auth.py:293-313`, `backend/utils.py:75-89`
- Logout removes a token from the in-memory cache, but a valid signed token is re-added on its next use until it expires.
- Use server-stored sessions or a token revocation list.

### STT proxy is vulnerable to SSRF

- **File:** `backend/routes/stt.py:24-43`
- Callers can supply `base_url` and `endpoint`, allowing server-side requests to loopback, internal-network, or metadata endpoints.
- Remove caller-controlled target URLs. Allow only configured STT provider endpoints.

### SpeechPro access controls and audio storage are unsafe

- **Files:** `backend/routes/speechpro.py:277-295`, `backend/routes/speechpro.py:416-426`, `backend/routes/speechpro.py:470-495`, `backend/routes/speechpro.py:675-698`, `backend/core/app.py:377-379`
- The SpeechPro target configuration is not effectively admin-protected, and uploaded voice recordings are written under a public static path.
- Require an admin dependency for configuration. Serve recordings only through an authenticated owner-checked endpoint or short-lived signed URLs.

### Learners can overwrite the OnuiTube catalog

- **File:** `backend/routes/media.py:35-62`
- `POST /api/tube/videos` requires only a logged-in user and directly writes the shared catalog.
- Restrict writes to administrators, validate the request schema, and retain a backup/version history.

### Untrusted values are rendered with `innerHTML`

- **Files:** `static/js/dashboard.js:119-132`, `static/js/speechpro-practice.js:340-382`, `static/js/speechpro-practice.js:435-439`, `static/js/ai-roleplay.js:526-532`, `static/js/onui-beats.js:48-61`, `static/js/onui-beats.js:122-138`
- User input, AI responses, and catalog content can execute script in learners' browsers.
- Use DOM APIs and `textContent` by default. Sanitize any content that must support a limited HTML subset.

## High-Priority Improvements

### Google OAuth is broken

- **Files:** `backend/core/app.py:271-388`, `backend/routes/auth.py:140-153`
- Authlib OAuth state requires `SessionMiddleware`; without it, `/api/login/google` returns 500.
- Add `SessionMiddleware` and integration coverage for the OAuth start/callback flow.

### Authentication tokens are exposed to JavaScript

- **Files:** `backend/routes/auth.py:279-290`, `static/js/auth.js:10-28`
- Login returns a bearer token that frontend code stores in `localStorage`, so an XSS flaw can exfiltrate it.
- Use only Secure, HttpOnly session cookies; remove token responses and `localStorage` persistence.

### Anonymous translation calls consume Gemini capacity

- **File:** `backend/routes/ai_services.py:1039-1046`
- `/api/voice-call/translate` has no authentication, credit, or request-rate protection.
- Require authentication, apply credit/rate limits, and cap input size.

### Audio uploads have no resource limits

- **Files:** `backend/routes/stt.py:58-60`, `backend/routes/speechpro.py:378-404`, `backend/routes/speechpro.py:474-503`
- Large uploads can exhaust memory, disk, ffmpeg capacity, and upstream API quotas.
- Enforce file size, audio duration, content type, processing timeouts, and per-user request limits.

### Credits are charged when provider work fails

- **Files:** `backend/routes/tts.py:182-211`, `backend/routes/tts.py:420-425`, `backend/routes/ai_services.py:1327-1372`
- TTS and image credits are consumed before complete validation and are not refunded on provider failures.
- Validate before debit and refund/compensate on failed generation.

## Quality and Operations

- Add login rate limits or exponential backoff: `backend/routes/auth.py:227-290`.
- Configure PM2 log rotation and size limits: `ecosystem.config.js:14-18`, `ecosystem.config.js:29-33`.
- Mask email addresses and voice transcripts in application logs; define retention limits.
- Update `document.documentElement.lang` and rerender dynamic UI after a locale change: `static/js/i18n.js:270-286`.
- Replace clickable landing-page `div` elements with links and add modal focus management: `templates/index.html:445-483`, `templates/index.html:556-666`.
- Add missing static locale keys: `dash.view_full`, `adm.current_mode`.

## Recommended Order

1. Fix SSRF, SpeechPro authorization/recording exposure, catalog write authorization, and token revocation.
2. Remove unsafe `innerHTML` rendering and migrate authentication to HttpOnly cookies.
3. Restore OAuth; protect AI usage and audio uploads with authentication and rate limits.
4. Add credit compensation, privacy-safe logs, and PM2 log rotation.
5. Add accessibility, i18n, security, and browser integration tests.

## Verification Status

- Existing Python test suite: `12 passed`.
- Missing coverage: OAuth, authorization boundaries, token revocation, SSRF prevention, upload limits, XSS rendering, browser accessibility, and locale-key completeness.

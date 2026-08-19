# Google OAuth production

Production Google Sign-In is configured through GitHub Actions secrets only.

Required repository secrets:

- `GOOGLE_OAUTH_CLIENT_ID`
- `GOOGLE_OAUTH_CLIENT_SECRET`

Production callback:

`https://solution.smarbiz.sbs/api/auth/oauth/google/callback/`

The production integration workflow copies the secrets into the server-side `.env` after a successful production deployment. Secret values must never be committed to this repository.

# Supabase connection verification — 2026-11-18

- Configured local ignored `.env` with the supplied database credentials, Session pooler on port 5432, and TLS (`sslmode=require`). File permissions: 0600. No credentials are included in this report.
- Connected successfully to the remote Supabase PostgreSQL database.
- Initialized the application's six tables using its existing idempotent schema initializer.
- Verified RLS enabled on all six application tables.
- Executed the API in a local FastAPI TestClient against the real remote database: `/ready` returned 200 with `database: postgresql`; `/health` returned 200 with `google_configured: true`.
- These checks do not verify a real Google OAuth round trip, a deployed Render service, or desktop end-to-end behavior. Google configuration presence is not proof of successful authentication.
- The public backend still needs deployment. Database snapshot mode and the 20 MiB upload limit are configured locally.

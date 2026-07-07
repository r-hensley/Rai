# Rai Web Admin Setup

This is a read-only proof-of-concept dashboard served by Rai itself through
`cogs.web_admin`. It is disabled unless the remote runtime opts in with
environment variables.

## Architecture

Use Cloudflare Tunnel as the public door:

```text
Browser -> https://rai-admin.example.com -> Cloudflare Tunnel -> http://127.0.0.1:8765
```

Rai should bind only to `127.0.0.1`. Cloudflare handles the public HTTPS URL.

## Discord Developer Portal

In the Discord application used by Rai, add this redirect URI:

```text
https://rai-admin.example.com/oauth/callback
```

Replace `rai-admin.example.com` with the final Cloudflare hostname.

## Required Environment

Set these on the remote Rai host. Do not commit real values to the repo.

```env
WEB_ADMIN_ENABLED=true
WEB_ADMIN_PUBLIC_BASE_URL=https://rai-admin.example.com
WEB_ADMIN_SESSION_SECRET=replace-with-a-long-random-string
WEB_ADMIN_ALLOWED_USERS=202995638860906496
DISCORD_CLIENT_ID=replace-with-discord-application-client-id
DISCORD_CLIENT_SECRET=replace-with-discord-application-client-secret
```

Optional settings:

```env
WEB_ADMIN_BIND_HOST=127.0.0.1
WEB_ADMIN_PORT=8765
WEB_ADMIN_ALLOWED_GUILDS=243838819743432704,189571157446492161
```

For local HTTP-only testing, you can temporarily set:

```env
WEB_ADMIN_COOKIE_SECURE=false
```

Do not use that setting for the public Cloudflare deployment.

## Cloudflare Tunnel Target

After the domain is active in Cloudflare, create a tunnel/public hostname with:

```text
Public hostname: rai-admin.example.com
Service: http://127.0.0.1:8765
```

The dashboard route `/healthz` is unauthenticated and returns a small JSON health
response. All dashboard content requires Discord OAuth login and an explicit user
ID allowlist.

## Security Notes

- The dashboard is read-only.
- The dashboard does not display raw `.env`, tokens, raw `db.json`, message
  contents, or full modlog bodies.
- OAuth uses a `state` cookie and the session cookie is signed.
- Keep production secrets outside repo-managed files when possible.

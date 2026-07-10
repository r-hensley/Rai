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
Run `cloudflared` on the same host as Rai so that this loopback address refers
to the machine serving the dashboard. Do not open port `8765` in the host
firewall or point public DNS directly at it.

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
WEB_ADMIN_SESSION_SECRET=paste-a-generated-value-here
WEB_ADMIN_ALLOWED_GUILDS=243838819743432704
WEB_ADMIN_GUILD_ADMINS={"243838819743432704":["202995638860906496"]}
DISCORD_CLIENT_ID=replace-with-discord-application-client-id
DISCORD_CLIENT_SECRET=replace-with-discord-application-client-secret
```

Generate the session secret on the remote host and paste its output into the
environment:

```bash
python3.14 -c "import secrets; print(secrets.token_urlsafe(48))"
```

The generated value must be at least 32 bytes. Do not use the placeholder from
this document. `WEB_ADMIN_GUILD_ADMINS` is a JSON object: each guild ID maps to
the Discord user IDs allowed to inspect that guild. For example, separate
Spanish and Japanese administrator lists look like this:

```env
WEB_ADMIN_ALLOWED_GUILDS=243838819743432704,189571157446492161
WEB_ADMIN_GUILD_ADMINS={"243838819743432704":["111111111111111111"],"189571157446492161":["222222222222222222"]}
```

An authenticated user sees only the guilds where their ID appears. The cog
rechecks this authorization on every dashboard request. Restart Rai after
changing these values so the cog reloads its configuration. The old
`WEB_ADMIN_ALLOWED_USERS` setting is no longer used.

Optional settings, shown with their defaults:

```env
WEB_ADMIN_BIND_HOST=127.0.0.1
WEB_ADMIN_PORT=8765
WEB_ADMIN_OWNER_USERS=202995638860906496
```

`WEB_ADMIN_OWNER_USERS` controls access to global process and database health.
If omitted, the cog uses Rai's existing `OWNER_ID`. Other guild administrators
see only activity and configuration for the guilds assigned to them.

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

Use a named tunnel with this stable hostname. A temporary Quick Tunnel receives
a changing hostname and is unsuitable because Discord requires the OAuth
redirect URI to match the configured value.

Keep the tunnel credential or token outside the repository and run the named
tunnel as a persistent service so it returns after a reboot. Cloudflare Access
can optionally add a second identity check in front of the site, but the cog's
Discord OAuth and per-guild authorization remain required.

The dashboard route `/healthz` is unauthenticated. It returns only
`{"ok": true}` with HTTP 200 when both the site and bot are ready, or
`{"ok": false}` with HTTP 503 otherwise. It does not disclose guild counts or
other diagnostics. All dashboard content requires Discord OAuth login and an
explicit per-guild user allowlist.

## Security Notes

- The dashboard is read-only.
- The dashboard does not display raw `.env`, tokens, raw `db.json`, message
  contents, or full modlog bodies.
- Last-hour charts aggregate only timestamps, guild IDs, channel IDs, and author
  counts from the in-memory message queue. They never render message content.
- OAuth uses a `state` cookie and the session cookie is signed.
- The cog disables its HTTP access log because OAuth callback URLs contain a
  short-lived authorization code. Do not enable query-string logging for this
  route in another proxy.
- Session and OAuth cookies are `Secure`, `HttpOnly`, and `SameSite=Lax` in
  public HTTPS deployments.
- Responses disable caching and include restrictive browser security headers.
- Keep production secrets outside repo-managed files when possible.

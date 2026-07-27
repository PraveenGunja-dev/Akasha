# Microsoft Entra Authentication Setup

Phase 1 replaces Akasha's local password placeholder with Microsoft Entra access tokens.

## Development Mode

Development authentication is the current default when no mode is configured:

```text
AKASHA_AUTH_MODE=development
VITE_AUTH_MODE=development
```

The login dialog allows anyone with application access to continue as CEO or PMAG. The browser keeps one opaque development profile identifier per role in `localStorage`, activates it in `sessionStorage` after login, and sends it with the selected role through development-only headers on same-origin Akasha API calls. Logout clears the active session but retains the local profile so private chat ownership survives later logins. Clearing browser site data creates a new identity and makes sessions owned by the previous identifier inaccessible through the UI.

Development profiles are browser-local. Two developers see the same history only if they deliberately use the same profile identifier and the same application database; pulling Git code does not copy chat-session rows. Production Entra identities use the stable directory object ID instead.

Never expose a deployment using development mode to an untrusted network.

## Production Mode

Both sides must explicitly select Entra before production:

```text
AKASHA_AUTH_MODE=entra
VITE_AUTH_MODE=entra
```

Production mode ignores development identity headers and requires a signed Entra bearer token.

## App Registration

Configure an Entra app registration with:

- SPA redirect URI: `http://localhost:5173/akasha/` for development and the deployed `/akasha/` URL for production.
- API scope: `access_as_user` under an application ID URI such as `api://<client-id>`.
- App role `Akasha.CEO` assigned to CEO users or groups.
- App role `Akasha.PMAG` assigned to PMAG users or groups.

App-role assignment is preferred. Group IDs can be configured as a fallback, but tokens using Entra group-overage references are rejected because Akasha does not call Microsoft Graph during authorization.

## Backend Environment

```text
ENTRA_TENANT_ID=<directory-tenant-id>
ENTRA_CLIENT_ID=<api-app-client-id>
ENTRA_AUDIENCE=<token-audience; defaults to ENTRA_CLIENT_ID>
ENTRA_CEO_APP_ROLE=Akasha.CEO
ENTRA_PMAG_APP_ROLE=Akasha.PMAG
ENTRA_CEO_GROUP_ID=<optional-group-object-id>
ENTRA_PMAG_GROUP_ID=<optional-group-object-id>
AKASHA_ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3510
REQUESTS_CA_BUNDLE=<optional-path-to-corporate-ca-bundle>
SSL_CERT_FILE=<optional-path-to-corporate-ca-bundle>
CURL_CA_BUNDLE=<optional-path-to-corporate-ca-bundle>
```

Install the updated backend requirements so `PyJWT[crypto]` is available.

## Frontend Environment

```text
VITE_ENTRA_CLIENT_ID=<spa-app-client-id>
VITE_ENTRA_TENANT_ID=<directory-tenant-id>
VITE_ENTRA_API_SCOPE=api://<api-app-client-id>/access_as_user
VITE_AUTH_MODE=entra
```

MSAL stores its cache in browser `sessionStorage`. Akasha does not store bearer tokens in `localStorage`.

## Database Migration

Run `backend/migrations/phase1_chat_ownership.sql` once before deploying Phase 1. Existing chat sessions have no verified owner and intentionally remain inaccessible. The migration must not assign them to an Entra user automatically.

## Authorization Boundary

- Every registered `/api` business router requires an authenticated CEO or PMAG identity.
- In development mode this identity is intentionally unverified and selected in the browser.
- CEO frontend routes require the `executive` Akasha role.
- PMAG frontend routes require the `pmag` Akasha role.
- Chat sessions and feedback are filtered by Entra tenant and user object ID.
- Local password login and user seeding return HTTP 410 and cannot create a session.

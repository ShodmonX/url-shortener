# Frontend Implementation Prompt

You are a senior frontend engineer. Build a production-quality frontend application for an existing URL Shortener backend.

Do not redesign the backend. Do not invent unsupported backend endpoints. Integrate cleanly with the existing API contract described below.

## Goal

Build a full frontend application for the URL Shortener backend using:

- React
- TypeScript
- Vite
- TailwindCSS
- React Router
- Axios
- Docker support

The UI should be:

- clean and minimal
- responsive
- accessible
- production-oriented
- easy to maintain
- based on reusable components

Do not overengineer the architecture. Keep it simple, modular, and realistic for a portfolio-quality project.

## Backend Overview

This backend is a FastAPI URL shortener with:

- URL creation
- optional custom aliases
- optional expiration
- redirect handling
- click analytics
- JWT authentication
- access + refresh token flow
- anonymous and authenticated URL ownership modes
- owner-only dashboard endpoints

Important backend behavior:

- The same `POST /api/v1/links` endpoint works for both anonymous and authenticated users.
- If the request includes a valid bearer access token, the created short URL belongs to that user.
- If the request does not include auth, the URL is anonymous and has no owner.
- Anonymous URLs redirect normally but do not appear in any user dashboard.
- Authenticated users can view only their own URLs through `/api/v1/users/me/urls`.
- Owner-only stats are available through `/api/v1/urls/{url_id}/stats`.
- There is no backend delete URL endpoint at the moment. Do not fake one.

## API Base Rules

- Base API prefix: `/api/v1`
- Public redirect endpoint is outside the API prefix: `GET /{short_code}`
- Use an environment variable for the API base URL, for example:
  - `VITE_API_BASE_URL=http://localhost:8000/api/v1`
- Do not manually build redirect URLs from short codes if the backend already returns `short_url`.

## Authentication Flow

The backend uses JWT access + refresh tokens returned in JSON responses.

### Auth endpoints

#### `POST /api/v1/auth/register`

Request:

```json
{
  "email": "alice@example.com",
  "password": "StrongPass123!"
}
```

Response:

```json
{
  "access_token": "jwt",
  "refresh_token": "jwt",
  "token_type": "bearer",
  "access_token_expires_at": "2026-03-06T10:15:00Z",
  "refresh_token_expires_at": "2026-04-05T10:00:00Z",
  "user": {
    "id": "uuid",
    "email": "alice@example.com",
    "created_at": "2026-03-06T10:00:00Z"
  }
}
```

#### `POST /api/v1/auth/login`

Request:

```json
{
  "email": "alice@example.com",
  "password": "StrongPass123!"
}
```

Response shape is the same as register.

#### `POST /api/v1/auth/refresh`

Request:

```json
{
  "refresh_token": "jwt"
}
```

Response shape is the same as register/login.

Important:

- Refresh tokens are rotated by the backend.
- When refresh succeeds, replace both the stored access token and refresh token.
- If refresh fails, clear auth state and treat the session as logged out.

#### `POST /api/v1/auth/logout`

Request:

```json
{
  "refresh_token": "jwt"
}
```

Response:

- `204 No Content`

Frontend rule:

- Always clear local auth state after logout.
- If logout API fails because the refresh token is already invalid, still clear local auth state.

#### `GET /api/v1/users/me`

Requires:

- `Authorization: Bearer <access_token>`

Response:

```json
{
  "id": "uuid",
  "email": "alice@example.com",
  "created_at": "2026-03-06T10:00:00Z"
}
```

## URL Endpoints

### `POST /api/v1/links`

Works for both anonymous and authenticated users.

Request:

```json
{
  "url": "https://example.com/docs",
  "custom_alias": "docs-link",
  "expires_at": "2026-12-31T23:59:59Z"
}
```

Notes:

- `custom_alias` is optional.
- `expires_at` is optional.
- If the user is authenticated, send the bearer token.
- If the user is not authenticated, do not send an auth header.

Response:

```json
{
  "short_code": "docs-link",
  "short_url": "http://localhost:8000/docs-link",
  "url": "https://example.com/docs/",
  "custom_alias": true,
  "expires_at": "2026-12-31T23:59:59Z",
  "metadata_status": "pending",
  "created_at": "2026-03-06T10:00:00Z",
  "manage_token": "opaque-string"
}
```

Important frontend behavior:

- Anonymous create:
  - short link is created successfully
  - it will not appear in any dashboard
  - show a clear note in the UI that anonymous links are not attached to an account
- Authenticated create:
  - short link is created successfully
  - it will appear in the user dashboard
- The backend returns `manage_token` even for anonymous links. This is not required for the core dashboard flow. You may optionally keep it in local state for future enhancements, but do not overcomplicate the MVP around it.

### `GET /api/v1/users/me/urls?page=1&page_size=20`

Requires auth.

Response:

```json
{
  "items": [
    {
      "id": "uuid",
      "original_url": "https://example.com/docs/",
      "short_code": "docs-link",
      "created_at": "2026-03-06T10:00:00Z",
      "expires_at": null,
      "total_clicks": 42
    }
  ],
  "pagination": {
    "page": 1,
    "page_size": 20,
    "total": 1,
    "has_next": false
  }
}
```

Important:

- Only URLs owned by the current authenticated user are returned.
- Anonymous URLs must never appear here.
- Use the `id` field from this response for owner stats routes.

### `GET /api/v1/urls/{url_id}/stats?days=30`

Requires auth.

Response:

```json
{
  "id": "uuid",
  "short_code": "docs-link",
  "original_url": "https://example.com/docs/",
  "total_clicks": 42,
  "created_at": "2026-03-06T10:00:00Z",
  "expires_at": null,
  "last_clicked_at": "2026-03-06T12:00:00Z",
  "daily_clicks": [
    {
      "date": "2026-03-05",
      "clicks": 10,
      "unique_visitors": 8
    },
    {
      "date": "2026-03-06",
      "clicks": 32,
      "unique_visitors": 21
    }
  ],
  "top_referrers": [
    {
      "value": "https://news.ycombinator.com",
      "count": 7
    }
  ],
  "top_countries": [
    {
      "value": "US",
      "count": 20
    }
  ],
  "top_devices": []
}
```

Important:

- This endpoint is owner-only.
- If another user tries to access a URL they do not own, the backend returns `404`.
- The frontend should show a generic "URL not found or not accessible" state and should not treat this as a normal server crash.

### Public redirect endpoint

#### `GET /{short_code}`

- Returns a `307` redirect to the original URL
- Not a React app page
- The frontend only needs to display/copy/open returned `short_url`

## Extra Existing Backend Endpoints

The backend also has manage-token endpoints:

- `GET /api/v1/links/{short_code}` with `X-Manage-Token`
- `GET /api/v1/links/{short_code}/preview` with `X-Manage-Token`
- `GET /api/v1/links/{short_code}/qr` with `X-Manage-Token`
- `GET /api/v1/links/{short_code}/analytics?days=30` with `X-Manage-Token`

These are not required for the main frontend pages below. Treat them as optional enhancements only.

## Pages To Build

### 1. Home Page

Requirements:

- public page
- primary URL shortening form
- works for anonymous users
- if the user is logged in, the same form should create owned URLs automatically by sending the access token
- include optional advanced fields:
  - custom alias
  - expiration datetime
- after success show:
  - short URL
  - original URL
  - copy button
  - open button
  - created timestamp
  - clear success/error states
- if anonymous:
  - show a note that the link will not appear in any dashboard
  - show a CTA to log in or register for ownership and stats access
- if authenticated:
  - show a CTA to view dashboard

### 2. Login Page

Requirements:

- email/password form
- submit to `/auth/login`
- inline validation
- loading state
- error handling for:
  - invalid credentials
  - inactive account
  - network issues
- on success:
  - persist session
  - redirect to dashboard or previous protected route

### 3. Register Page

Requirements:

- email/password form
- password confirmation on frontend
- submit to `/auth/register`
- inline validation
- loading state
- on success:
  - persist session
  - redirect to dashboard

### 4. Dashboard Page

Requirements:

- authenticated route
- fetch `/users/me/urls`
- support pagination using URL search params:
  - `?page=1&page_size=20`
- show:
  - short code
  - original URL
  - created at
  - expires at
  - total clicks
  - short URL copy action
  - open short URL action
  - view stats action
- responsive layout:
  - table on desktop
  - stacked cards on mobile
- empty state if no URLs exist
- include a clear note that only owned URLs appear here

Delete behavior:

- The backend currently does not support deleting URLs.
- Do not call a fake delete endpoint.
- Either omit the delete action entirely or render a disabled "Delete" button labeled as unavailable.

### 5. URL Statistics Page

Requirements:

- authenticated route
- route param should be the backend URL UUID from `/users/me/urls`
- fetch `/urls/{url_id}/stats`
- display:
  - original URL
  - short code
  - total clicks
  - created at
  - expires at
  - last clicked at
  - daily clicks summary
  - top referrers
  - top countries
  - top devices
- allow switching stats range with a simple selector, for example:
  - 7 days
  - 30 days
  - 90 days
  - 365 days
- charts if possible:
  - use a lightweight chart implementation
  - if you add a chart library, keep it minimal
  - a simple bar/line chart is enough
- if the API returns 404:
  - show a "not found or not accessible" state

## Frontend Architecture Requirements

Create the frontend in a separate `frontend/` directory so the backend remains untouched except for optional Docker integration.

### Suggested folder structure

```text
frontend/
  src/
    api/
      client.ts
      auth.ts
      links.ts
      users.ts
      urls.ts
    app/
      router.tsx
      providers.tsx
    components/
      ui/
        Button.tsx
        Input.tsx
        Card.tsx
        Spinner.tsx
        Alert.tsx
        EmptyState.tsx
        Pagination.tsx
      layout/
        AppShell.tsx
        Header.tsx
        Container.tsx
      auth/
        AuthForm.tsx
      links/
        ShortenForm.tsx
        ShortLinkResult.tsx
        UrlRow.tsx
        UrlCard.tsx
      stats/
        StatsSummary.tsx
        DailyClicksChart.tsx
        DimensionList.tsx
    features/
      auth/
        AuthContext.tsx
        authStorage.ts
        useAuth.ts
      links/
        hooks.ts
      dashboard/
        hooks.ts
      stats/
        hooks.ts
    pages/
      HomePage.tsx
      LoginPage.tsx
      RegisterPage.tsx
      DashboardPage.tsx
      UrlStatsPage.tsx
      NotFoundPage.tsx
    routes/
      ProtectedRoute.tsx
      PublicOnlyRoute.tsx
    types/
      api.ts
    utils/
      format.ts
      copy.ts
      query.ts
    main.tsx
    index.css
  public/
  .env.example
  Dockerfile
  nginx.conf
  package.json
  tsconfig.json
  vite.config.ts
  tailwind.config.ts
  postcss.config.js
```

You may adjust naming slightly, but keep the overall architecture simple and feature-oriented.

## Auth State Management

Use a lightweight auth architecture:

- React Context for auth state
- custom hook such as `useAuth()`
- Axios client with auth interceptors

Recommended token strategy:

- keep the access token in memory
- keep the refresh token in localStorage
- on app startup:
  - if a refresh token exists, call `/auth/refresh`
  - restore the session silently if possible
- when access token expires:
  - Axios interceptor should attempt one refresh
  - retry the original request once
- if refresh fails:
  - clear auth state
  - redirect to login when the user is on a protected page

Use a refresh-in-flight guard so multiple concurrent 401 responses do not trigger multiple refresh calls simultaneously.

## API Client Layer

Create a dedicated API layer with typed request/response functions:

- `authApi.register`
- `authApi.login`
- `authApi.refresh`
- `authApi.logout`
- `authApi.getMe`
- `linksApi.create`
- `usersApi.getMyUrls`
- `urlsApi.getStats`

Rules:

- centralize Axios config in one place
- add auth headers automatically
- keep route handlers thin
- keep page components focused on UI composition
- do not call Axios directly all over the component tree

## Route Protection

Implement:

- `ProtectedRoute`
  - for dashboard and stats page
  - waits for auth bootstrap to finish before redirecting
- `PublicOnlyRoute`
  - for login/register
  - redirects authenticated users away from auth pages

Suggested routes:

- `/` -> Home
- `/login` -> Login
- `/register` -> Register
- `/dashboard` -> Dashboard
- `/dashboard/urls/:urlId` -> URL Stats
- `*` -> Not Found

## UI and Component Guidance

The design should be modern, clean, and restrained.

Use:

- a simple top navigation
- a centered content container
- clear hierarchy
- generous spacing
- readable typography
- subtle shadows and borders
- strong button and form states

Do not rely on generic placeholder-looking layouts. Make the UI feel intentional without becoming flashy.

Component expectations:

- reusable `Button`, `Input`, `Card`, `Alert`, `Spinner`, `Pagination`
- reusable shorten form used on the Home page
- reusable URL list items adaptable to desktop and mobile layouts
- reusable stat cards for analytics summary

## Error Handling

Handle these cases well:

- `401`
  - unauthenticated or expired token
  - trigger refresh flow when appropriate
- `403`
  - authenticated but forbidden
  - show a clear message
- `404`
  - stats page for another user's URL or unknown URL
  - show a generic not found/no access state
- `409`
  - duplicate email on register
  - custom alias conflict on URL creation
- `422`
  - validation errors
  - surface field-level messages when possible
- `429`
  - rate limited
  - show a friendly retry message
- network/server errors
  - show non-blocking but visible feedback

Use user-friendly error messaging. Avoid dumping raw Axios errors into the UI.

## Loading States

Implement visible loading states for:

- initial auth bootstrap
- login/register submit
- create short URL submit
- dashboard fetch
- pagination transitions
- stats fetch and range changes

Use disabled buttons, skeletons, spinners, or placeholder cards as appropriate.

## Responsive Design

The frontend must work well on:

- mobile
- tablet
- desktop

Specific expectations:

- shorten form should be easy to use on mobile
- dashboard table should gracefully switch to cards on smaller screens
- stats summary cards should stack cleanly
- navigation should remain usable on small screens

## Home Page UX Rules Around Anonymous vs Authenticated Users

This is important:

- A visitor can shorten URLs without logging in.
- If the visitor is not authenticated:
  - create the URL anonymously
  - do not imply that it will appear later in a dashboard
  - explain that dashboard and owner stats require authentication
- If the visitor is authenticated:
  - create the URL as an owned URL
  - make it clear it will appear in the dashboard

Optional but acceptable:

- store a list of recent anonymous results locally in localStorage for convenience only
- if you do this, label them clearly as client-side history, not server-owned data

## Implementation Constraints

- Do not add Redux or other heavyweight state libraries unless absolutely necessary.
- Do not invent backend capabilities that do not exist.
- Do not build delete functionality against a fake endpoint.
- Do not hardcode localhost URLs inside components.
- Use environment variables for configuration.
- Keep the code strongly typed.
- Keep date formatting consistent.
- Keep API types centralized.

## Docker Requirements

Add Docker support for the frontend.

Expectations:

- multi-stage Docker build
- build the Vite app with Node
- serve the production build with Nginx
- include an `.env.example`
- include an `nginx.conf` if needed

If you decide to update the repository root `docker-compose.yml`, do it additively only and do not break the backend services.

## Deliverables

Produce:

- the full frontend application in `frontend/`
- reusable components
- typed API layer
- auth context and refresh flow
- protected routes
- responsive pages for Home, Login, Register, Dashboard, and URL Stats
- Docker support
- concise README instructions for how to run the frontend locally and with Docker

## Final Notes

- Prefer maintainability over cleverness.
- Use the existing backend contract exactly as described.
- Make the Home page work well for anonymous users first, then layer authenticated dashboard behavior on top.
- Keep the UI polished but minimal.
- If something is unsupported by the backend, reflect that honestly in the UI instead of inventing functionality.

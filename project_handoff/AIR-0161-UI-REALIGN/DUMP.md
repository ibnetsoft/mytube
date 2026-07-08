# AIR-0161-UI-REALIGN: Referral Dashboard UI Migration

**Status**: COMPLETED & APPROVED
**Priority**: P0
**Role**: Senior Frontend Engineer

## Objective
Migrate the Referral Dashboard UI out of the Next.js `auth-web` frontend and directly into the FastAPI desktop app's native templating system, strictly adhering to the CTO's requirement that users must not be redirected to external domains for core features.

## Architecture & CTO Decisions Addressed
- **Zero Redirection Rule**: The referral dashboard now lives entirely within the local user app (`/referral`).
- **No auth-web Dependency (UI)**: The React/Next.js dashboard components have been bypassed. The new implementation is 100% native HTML, TailwindCSS, and Vanilla JavaScript hosted within `templates/pages/referral.html`.
- **API Reusability**: The core data logic remains secure. The new frontend securely fetches data using the user's local `Bearer token` directly from the `auth-web` API endpoints (`/dashboard`, `/tree`, `/timeline`).

## Implementation Details

### 1. Navigation Changes
- The `base.html` sidebar and `projects.html` top banner no longer point to `{{ AUTH_SERVER_URL }}/referral`. They now utilize the local `/referral` route, keeping the user securely within the desktop app context.

### 2. FastAPI Route
- Added a dedicated HTML route in `app/routers/pages.py` (`@router.get("/referral")`) which renders the Jinja2 template and passes localization variables.

### 3. UI Structure (Vanilla HTML/JS)
- **KPI Cards**: Converted from React components to raw DOM elements. Data is fetched asynchronously, displaying loading skeleton animations until the `/dashboard` API resolves.
- **Referral Tree**: The previously flat API response is now recursively parsed into a parent-child hierarchical tree on the client side. The DOM manipulation is optimized to build a single HTML string before injection (`container.innerHTML`), avoiding slow multiple repaints.
- **Commission Timeline**: Recreated the timeline with a `Load More` pagination button.
- **Share Section**: Fully implemented the native `navigator.share` API along with `navigator.clipboard.writeText`, including a custom slide-in Toast notification built in pure CSS (`animate-[slideIn_0.3s_ease-out]`).

### 4. Performance Notes
- **Minimal DOM Updates**: Instead of reactive states constantly triggering re-renders, the JS engine only manipulates the DOM exactly once per API payload load.
- **Zero Bundle Size**: Bypassing React and Next.js entirely for this page drastically improves First Input Delay (FID) and memory usage within the desktop web view.

## Deliverables Completed
- `templates/pages/referral.html` (New UI)
- `app/routers/pages.py` (New Backend Route)
- `templates/base.html` & `templates/pages/projects.html` (Updated Navigation)

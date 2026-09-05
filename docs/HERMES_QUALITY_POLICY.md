# Hermes Quality Policy

Hermes generation criteria are stored in Supabase instead of being controlled only by scattered constants.

## Storage

- `quality_policies` contains the active `hermes_generation` policy and its optimistic-lock version.
- `quality_policy_history` records every saved version through a database trigger.
- `topics_queue.quality_policy_snapshot` records the exact policy version used for a completed package.
- Both policy tables have RLS enabled and are accessible only through the server-side `service_role`.

## Worker Flow

1. The Worker settings page reads and updates the policy through the authenticated central Worker API.
2. A Hermes worker fetches the active policy at the start of each claimed job.
3. The worker normalizes the policy, stores a snapshot in the job payload, and applies it to stage and final gates.
4. If the central API is unavailable, Hermes uses the bundled strict policy. It never disables validation.
5. Saves use the current version as an optimistic lock. A stale screen must reload instead of overwriting a newer policy.

The fallback prohibition, prior-stage requirement, and passing QA report requirement are hard guards. They are visible but cannot be disabled from the Worker UI.

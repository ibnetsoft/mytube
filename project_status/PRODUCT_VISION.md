# PRODUCT VISION

## Service Definition
AIR Studio is a production platform for creating AI-assisted video content with a BFF-oriented architecture.
Its current product goal is to support online members who create longform videos through a guided workflow that connects topic assignment, planning, script generation, media generation, editing, rendering, and delivery.

## Core Target Users
- Online workers producing longform videos inside the AIR Studio workflow
- Internal operators managing policy, assignment, payout, and shared infrastructure

## Product Priority
1. `Longform Mode`
   This is the primary delivery target and the main product we are actively completing.
2. `Longform Music`
   Internal-use mode for later development. Preserve structure, but do not actively build it now.
3. `General Shorts`
   Intended later as a shorts/reels/tiktok-connected marketing platform. Preserve structure, but defer active feature work.
4. `Shorts Commerce`
   Internal-use mode for later development. Preserve structure, but do not actively build it now.

## Development Principles
- If a task directly helps `Longform Mode`, it should be prioritized.
- If a task does not directly help `Longform Mode`, it should usually move to backlog or roadmap unless it protects shared structure.
- Shared modules such as BFF layers, authentication, database access, and APIs should be implemented so all modes can reuse them.
- UI work should be completed for `Longform Mode` first.
- Other modes do not need to be fully working right now, but their structure must not be broken.
- Changes should preserve clean ownership between runtime code, admin code, and shared contracts.
- ChatGPT/Codex should treat this file plus `NEXT_TASK.md` as the decision baseline for whether a proposal becomes active work now.

## What We Are Not Doing Right Now
- We are not actively finishing all four modes in parallel.
- We are not allowing deferred modes to block longform delivery unless the issue affects shared architecture.
- We are not expanding UI polish evenly across all modes before the longform worker flow is complete.
- We are not keeping product-facing features that do not match the real operating model just because code for them already exists.
- We are not letting wallet-address-centered payout UX survive by default if operator payout flow is actually heading toward Binance ID or another controlled identifier.

## Why BFF Matters Here
The BFF structure helps AIR Studio keep worker-facing runtime flows, admin-facing policy flows, and backend integration contracts organized without collapsing everything into one layer.
This is especially important because the product already contains multiple modes with different maturity levels.
Keeping BFF boundaries intact lets us finish `Longform Mode` first while preserving the base needed to resume the other modes later.

## Document Roles
- `PRODUCT_VISION.md`
  Stable product constitution. Changes rarely.
- `ROADMAP.md`
  Medium-term plan and sequencing.
- `LATEST.md`
  Recent confirmed changes and current state snapshot.
- `NEXT_TASK.md`
  Immediate handoff and next implementation target.

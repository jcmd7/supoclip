# Task lifecycle (backend contract)

This documents the current SupoClip task workflow for users, developers and AI agents. The runtime helper is `src/task_lifecycle.py`. **The state topology below is descriptive, not yet an enforced database transition guard.**

| State | Meaning | Usual next state |
| --- | --- | --- |
| `queued` | Task has been created or explicitly re-queued. | `processing`, `error`, `cancelled` |
| `processing` | Worker is generating clips. | `completed`, `error`, `cancelled` |
| `completed` | Generation finished. | None |
| `error` | A task failed. | `queued` via explicit resume |
| `cancelled` | User requested cancellation. | `queued` via explicit resume |

## Event contract

`GET /tasks/{task_id}/progress` emits an initial `status` event and may then emit `progress` or `clip_ready` events. It emits a `close` event and ends the SSE stream for **all** terminal statuses: `completed`, `error` and `cancelled`. `POST /tasks/{task_id}/cancel` records cancellation and now makes a best-effort `cancelled` progress publication to existing subscribers. The persisted task row remains authoritative; clients should fetch it after `close`.

### UX

Do not display an active spinner after receiving a terminal status. Distinguish user cancellation from processing failure; only offer Resume for `cancelled`/`error` tasks, per the existing API.

### DX

Keep state names and terminal semantics synchronized with `src/task_lifecycle.py`. When adding a state, update API, worker, frontend, tests, and this contract. Treat re-queueing as a **new attempt**, not a recovery of an old worker.

### AX

Agents should read `status` from the task API rather than inferring completion from progress percentage or Redis. Only request `cancel` for queued/processing tasks; only request `resume` for error/cancelled (or queued, which the current API also accepts). Observe `close` and re-fetch final persisted state before acting on generated clips.

## Known concurrency limitation

The database's `update_task_status` currently writes statuses without an attempt/version fence; a late worker can overwrite `cancelled`, or an old attempt can conflict with a resumed task. The SSE and lifecycle-helper patch **does not fix that**. The follow-up should add generation/attempt IDs, compare-and-set transitions, worker fencing, and retry/cancel/resume concurrency tests before touching execution semantics. No database migration is included here.

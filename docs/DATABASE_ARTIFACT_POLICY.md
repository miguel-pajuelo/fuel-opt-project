# Database artifact policy (audit finding H7)

## Finding

`data/db/gas_stations.sqlite` is tracked in git:

- size ≈ **20 MB**;
- mutated by the local catalog refresh (runs every ~4h on the maintainer's PC),
  so committing it produces large binary diffs;
- **≈ 60 MB** of cumulative DB blob versions already exist in history (paid by
  every clone forever);
- the regeneration source `data/cache/minetur_snapshot.json` (≈ 16 MB) is also
  tracked.

Severity is **low from a security standpoint** — the data is public MINETUR
catalog data, no secrets. The impact is **maintainability / release hygiene**:
repository bloat and accidental large binary diffs.

## Why it is currently tracked (intentional, for now)

First boot depends on the DB being present:

- `app/api/main.py` startup raises if `settings.db_path` does not exist;
- the launcher only triggers a refresh *after* the server is healthy, so a
  missing DB causes a chicken-and-egg failure at first boot.

Tracking the prebuilt DB therefore gives the local demo **zero-config startup**.
No test depends on the tracked DB (tests build their own temporary databases).

## Options considered

1. **Keep tracked, document as intentional** — simplest; zero-config demo keeps
   working. Accepts the bloat.
2. **Keep tracked + guardrail against growth/mutation** — as (1) plus a
   reporting check (`tests/db_artifact_check.py`) that warns on size/mutation
   and fails only on an absurd ceiling. *(Adopted now.)*
3. **Git LFS** — moves the binary out of normal history but adds clone/
   contributor friction for an artifact that is fully regenerable. Not preferred.
4. **Stop tracking; generate on first run** — drop the DB from git and bootstrap
   it offline from the tracked `minetur_snapshot.json`
   (`python scripts/refresh_catalog.py --source snapshot`, no network). Cleanest
   long-term, but requires a startup/launcher change so first boot self-heals
   instead of erroring. **Needs approval (code change).**
5. **Small fixture DB in git + full DB generated separately** — keep a tiny
   fixture for demo/tests, regenerate the production-sized DB out of band.
   Also a code/bootstrap change.

## Decision

- **Short term (now): Option 1 + 2.** Keep `gas_stations.sqlite` tracked
  (load-bearing for first boot; low security risk) and add a non-invasive
  guardrail. Do **not** commit refreshed copies casually — the working-tree DB
  mutates on refresh and should be committed only on a deliberate dataset bump.
- **Long term (pending approval): Option 4 (preferred) or 5.** Untrack the
  production DB and bootstrap on first run from the tracked snapshot. This
  removes ongoing bloat but is a behavioral change and is **out of scope** for
  the analysis-only H7 pass.

History is intentionally **not** rewritten here (no `git filter-repo` / BFG /
LFS migration). Any history rewrite is a separate, coordinated decision because
it changes every commit hash and forces re-clones.

## Guardrail

`tests/db_artifact_check.py` (also run by `scripts/release_check.cmd`):

- reports tracked status, size, and whether the DB is modified in the worktree;
- prints a warning above ~25 MB or if the DB is modified (avoid committing it);
- fails only above a conservative **64 MB** ceiling, so normal refreshes never
  trip it but an accidental oversized commit does.

`.gitignore` is intentionally left unchanged: the active DB is tracked on
purpose, while its sidecars/backups (`*-wal`, `*-shm`, `*.next.sqlite`,
`*.previous-*.sqlite`, backups) are already ignored.

## H7 status

**Accepted-risk (short term) + pending implementation (long term).** The
guardrail and this policy close the "accidental bloat / silent growth" gap now;
fully removing the artifact from tracking is deferred until the first-run
bootstrap change is approved.

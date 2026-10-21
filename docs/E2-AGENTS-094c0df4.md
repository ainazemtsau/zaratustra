# Zaratustra development

Commands (Node 22.19.0, npm 11.6.2, Pi 1.3.0):

- `npm ci` — install pinned development dependencies.
- `npm run check` — format, ESLint, TypeScript, dependency graph, build, disk tests.
- `npm run format` — format maintained sources/docs.
- `npx tsx --test --test-name-pattern="disk" tests/core.test.ts` — focused tests.
- `npx prettier --check src/core/index.ts`; `npx eslint src/core/index.ts`.
- `npm run deliver` — check plus required RESULT fields.

Read `docs/specification-v1.1.html` completely and `docs/DEVELOPMENT.md` for the
approved block and decisions. The full R1 contract remains the target. The current
owner-authorized block is E2: exact approvals, managed native file effects/recovery,
finite merges/catalog changes, textual export/drift and provider boundary.
D is independently scope-qualified PASS and separately owner-accepted on
1b742a6e774eaa14826c036977ae2a42ff1ca46a. E1 is independently scope-qualified PASS and technically accepted by the coordinator
under explicit owner delegation on 0b45c0853d7ee0c2f3c294b9bc4dd9803117462a.
This is not personal usefulness/T31. E2 result acceptance remains separate. Full E/R1/T31 remain open.

## Run contract (PROBA)

1. Authority is the owner assignment plus this repo contract and full specification.
2. Native build/hygiene and nonvisual persistence checks are required. OPORA frozen-pair,
   mutation, stage receipt, notification and orchestration machinery do not apply here.
3. Real product/authority changes and unavailable required tools stop for owner input.
4. This assignment uses one executor; no chats or subagents. The owner launches fresh review.
5. Correct routine preserving engineering defects in this assignment; retain all failed attempts.
6. Return root `RESULT.md`: outcome, evidence, assumptions, cuts, cost, manual-acceptance, next.
7. `next: solmax`; do not write Direction OS or issue successor tasks. No R1/owner acceptance claim.

## Principles

- Pi/model own understanding, planning, language and context selection. No keyword planner.
- Core is Pi-independent; module imports use public `index.ts`. SQLite is behind StoragePort.
- Original bytes/quotes stay original; English working representations are labelled derived.
- State, versions, Changes and receipts commit atomically; prose never proves persistence.
- Personal data, credentials and private transcripts never enter Git. Only synthetic evidence.
- One trusted personal writer, no OS-isolation or arbitrary-command deduplication claim.

All product writes stay in this checkout and explicitly isolated synthetic/output paths.
Keep imports bounded; no database transaction spans model, human or external-tool waits.
Test actual installed public refs outside checkout; never copy credentials into test config.
Live E2 budget: one new non-reset ledger, 30 attempts / 240 dispatches / USD 20 Pi estimate;
openai-codex/gpt-6.1-sol, medium, native Pi authentication. Retain all errors/retries.
Real merges and finite catalog reorganization require exact E2 bound approvals.
E3 backup/quarantine restore/archive/delete/retention/GC and R2 Sleep/Codex remain open.
Public route is only `codex/zaratustra-v1`; no force push, main/foreign ref/tag mutation.

END_OF_FILE: AGENTS.md

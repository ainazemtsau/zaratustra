# P2 dependency advisory applicability

The unchanged lockfile and current `npm audit --json` report nine high vulnerable
package nodes, with one unique advisory:
[GHSA-vfj7-8cjw-p6xm / CVE-2026-93687](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm).
The authenticated GitHub advisory read reports braces <=3.0.3 recursive AST walkers
can exhaust the stack on deeply nested brace patterns, even under the character
limit, terminating Node with RangeError. It was published 2026-09-18, updated
2026-10-02, and has no first_patched_version in that advisory response.

Exact locked route:
`typescript-eslint@8.46.2 -> @typescript-eslint/typescript-estree@8.46.2 -> fast-glob@3.3.3 -> micromatch@4.0.8 -> braces@3.0.3`.
The nine nodes are typescript-eslint, @typescript-eslint/eslint-plugin,
@typescript-eslint/parser, @typescript-eslint/type-utils,
@typescript-eslint/typescript-estree, @typescript-eslint/utils, fast-glob,
micromatch and braces. The first six have version 8.46.2. Audit propagation does
not mean nine independent CVEs.

| Surface                                   | Observed applicability and limit                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| ----------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Installed Zaratustra product dependencies | Native Pi install audited two packages, zero vulnerabilities. `npm audit --omit=dev --json` reports zero. The product runtime dependency is zod@4.1.12, and own Core/storage/import paths do not import braces/fast-glob/micromatch. No route from retained book/message content into these glob parsers was found in the implemented block. This is a graph/code observation, not a general safety proof.                                                                                                                                              |
| Development lint tools                    | The vulnerable dependency really is installed and reachable as a library. In locked typescript-estree, resolveProjectList passes parserOptions.project glob patterns to fast-glob, but returns early for an empty project list. Current eslint.config.js uses recommended rules without parserOptions.project/projectService. This particular project-glob route is not selected by the current config. Hostile/future config, supplied patterns or other tooling could expose the parser; devDependency classification alone does not remove the risk. |
| Pi host and wider tooling                 | Pi/TypeBox are provided by the host at runtime. This patch does not audit the entire host, every brace call site or arbitrary shell tools/configuration. Their security remains unknown from these checks. No alternate provider or material format was added.                                                                                                                                                                                                                                                                                          |

Residual issue: the locked development dependency still has the high advisory.
A separate bounded dependency change should select a compatible non-vulnerable
resolution and check the resulting lint/type/tool graph. npm suggests a newer
umbrella typescript-eslint version, but this was not installed or assumed to fix
all routes. No mass update or security PASS is part of the two P2 corrections.

Exact reports, advisory response and dependency path are retained in
`p2-evidence/`; audit exits are 1 (full) and 0 (omit=dev). No exploit was attempted.

END_OF_FILE: docs/P2-DEPENDENCIES.md

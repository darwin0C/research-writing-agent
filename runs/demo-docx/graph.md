# Task graph · demo-docx

Journal: International Journal of Heat and Mass Transfer (style: ijhmt) · bib: — · level: medium · max attempts per unit: 3

## Done when
- Every prose unit is `passed` or `reverted` (original kept after 3 failed gates).
- Final section gate passes (no `[error]`).
- claims.md exists and every reopen it caused is resolved.
- report.md is generated.

## Nodes

| Node | Type | Input | Output | Check |
|---|---|---|---|---|
| C1 split | code | original.tex | units/*, audit.txt | — |
| A1 audit | LLM ×1 (auditor) | masked.txt + audit.txt of 3 units | issues.md per unit | each issue quotes its sentence |
| A2 rewrite uNN | LLM ×N parallel (rewriter) | masked.txt, issues.md, feedback.md | masked_revised.txt, changes.md | G uNN |
| G uNN | code (hook) | masked_revised.txt | revised.tex, run.json | unmask + compare: 0 errors |
| C assemble + G* | code | units | revised.tex | full-section compare: 0 errors |
| A3 claims | LLM ×1 (claim-checker) | revised.tex + original.tex | claims.md, reopen requests | claim never stronger than evidence |
| C5 report | code | run.json, changes.md, claims.md | report.md | — |

## Edges

```
C1 → A1 → A2[uNN] → G[uNN] ─fail(≤3)→ A2[uNN]
                         └pass→ C assemble → G* → A3 ─reopen→ A2[uNN]
                                                   └ok→ C5
```

Prose units: u02 u03 u05  
Frozen units (passed through unchanged): u01 u04

## Code nodes (never delegated to a model)
split, mask/unmask, audit scan, gate (compare), retry/revert bookkeeping, assemble, report merge.

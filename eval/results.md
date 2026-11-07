# Checker benchmark

Corpus: 10 paragraph pairs · overall: **PASS**

## Faithful revisions (false-positive check)

| Paragraph | Errors | Warnings |
|---|---|---|
| p01-chf-mass-flux | 0 | 0 |
| p02-md-waiting-time | 0 | 0 |
| p03-htc-nanostructure | 0 | 0 |
| p04-pressure-drop | 0 | 0 |
| p05-contact-angle-onb | 0 | 0 |
| p06-itr | 0 | 0 |
| p07-friction-factor | 0 | 0 |
| p08-departure | 0 | 0 |
| p09-biphilic | 0 | 0 |
| p10-model-validation | 0 | 0 |

False rejections: 0 · warnings to review: 0

## Planted errors

| Type | Kind | Cases | Blocked | Flagged | Target |
|---|---|---|---|---|---|
| number_change | hard | 10 | 100% | 100% | blocked ≥ 95% ✓ |
| unit_change | hard | 8 | 100% | 100% | blocked ≥ 95% ✓ |
| cite_drop | hard | 6 | 100% | 100% | blocked ≥ 95% ✓ |
| cite_fake | hard | 6 | 100% | 100% | blocked ≥ 95% ✓ |
| eq_edit | hard | 2 | 100% | 100% | blocked ≥ 95% ✓ |
| from_to_swap | hard | 4 | 100% | 100% | blocked ≥ 95% ✓ |
| bound_drop | hard | 4 | 100% | 100% | blocked ≥ 95% ✓ |
| claim_up | soft | 4 | 100% | 100% | flagged ≥ 80% ✓ |
| direction_flip | soft | 8 | 50% | 100% | flagged ≥ 80% ✓ |
| approx_drop | soft | 4 | 0% | 100% | flagged ≥ 80% ✓ |
| scope_drop | soft | 5 | 0% | 100% | flagged ≥ 80% ✓ |
| hedge_drop | soft | 4 | 0% | 100% | flagged ≥ 80% ✓ |
| intensifier_add | soft | 8 | 0% | 100% | flagged ≥ 80% ✓ |
| term_drift | soft | 8 | 0% | 100% | flagged ≥ 80% ✓ |
| rebind_swap | gap | 1 | 0% | 0% | — |

## Misses

- rebind_swap in p02-md-waiting-time

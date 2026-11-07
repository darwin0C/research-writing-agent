# Claims · demo-style

| Unit | Sentence (≤12 words) | Evidence | Strength orig → new | Verdict |
|---|---|---|---|---|
| u02 | "Wall wettability affects both the nucleation onset and … bubble growth" | \cite{kim2015,chen2019}; bubble growth not studied here, rests on citation only | "plays a pivotal role in determining" (assert) → "affects" (assert, plainer) | ok |
| u03 | "At 300 K, onset time decreased from 350 ps … to 125 ps" | Fig. onset; same quantities as original (onset time, 110° → 35°, wall T 300 K) | data statement, unchanged; 300 K scope kept | ok |
| u03 | "This indicates that a smaller contact angle accelerates nucleation." | 350 → 125 ps at 300 K, single runs, no uncertainty | demonstrate ("clearly", "significantly") → indicate | ok |
| u03 | "The 70° surface gave an intermediate onset time of 210 ps." | Fig. onset; 210 ps still the 70° onset time | data statement, unchanged | ok |
| u03 | "consistent with the onset time varying monotonically … over the range" | three contact angles (35°, 70°, 110°) | prove → consistent with (≈ suggest); scope "over the range we studied" added | ok |
| u05 | "We can interpret the increase in … onset time with contact angle" | u03 data: onset time rises 125 → 210 → 350 ps with angle — direction named correctly | can (unchanged) | ok |
| u05 | "the trend may be attributed to a lower energy barrier … hydrophilic" | Eq. onset; no barrier computed. Standard heterogeneous CNT predicts a lower barrier on more hydrophobic walls — sign of the mechanism questionable | assert ("decreases … due to") → may | author |
| u05 | "This lower barrier would come from the enhanced solid–liquid interaction" | \cite{carey2018} | assert ("due to") → would | ok |
| u05 | "This result suggests that interfacial wettability affects the onset of phase change." | three angles at 300 K (u03) | implicit assert ("sheds light on the interplay … phase change") → suggest; scope narrowed to onset | ok |
| u05 | "Under the conditions studied here, wettability could be considered in … design" | none in section — only onset time measured, no cooling/heat-transfer performance | "paves the way for rational design of high-performance …" → could; scope added | author |

Notes:
- No number changed quantity: 350 ps (110°), 125 ps (35°), 210 ps (70°), 300 K (wall temperature) all describe the same quantity as in original.tex.
- Cross-paragraph: the closing u05 sentences stay within what u03 shows (onset time, three angles, 300 K); the design sentence still lacks direct evidence, but that gap is inherited from the original and is now hedged and scoped.
- The style pass (style_changes.md) kept every hedge and scope condition ("indicates", "over the range we studied", "may", "would", "under the conditions studied here"); no strengthening introduced by splitting sentences.

## Reopen
none

claims: 8 ok, 0 reopen, 2 author

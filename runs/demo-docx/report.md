# 修改报告 · demo-docx

目标期刊：International Journal of Heat and Mass Transfer · 改写程度：medium

## 1. 修改后文本

```latex
Results and discussion

Wall wettability influences both the onset of nucleation of a liquid on a solid surface and the subsequent bubble growth ⟦CITE1⟧.

⟦REF1⟧ presents the vapor fraction near the wall for contact angles ⟦FMT1⟧ of 35°, 70° and 110°. The hydrophilic surface accelerated nucleation: at a wall temperature of 300 K and a heat flux of 2 MW/m⟦FMT2⟧, the onset time decreased from 350 ps to 125 ps. This result suggests that the onset time varies monotonically with the contact angle.

⟦EQ1⟧

The shorter onset time on the hydrophilic surface is consistent with classical nucleation theory, in which an enhanced solid–liquid interaction is expected to lower the energy barrier ⟦CITE1⟧. This result relates wettability to the onset of nucleation under the simulated conditions⟦BM1⟧ and may be relevant to the design of cooling surfaces.⟦BM2⟧
```

## 2. 各段修改

### u02 · passed · 校验 1 次

| # | Before | After | Reason (issue #) |
|---|---|---|---|
| 1 | "In recent years, the nucleation behavior of liquids on solid surfaces has garnered significant attention." | Deleted; its subject ("liquid on a solid surface") is folded into the next sentence | Template opener with an uncited "attention" claim (1) |
| 2 | "It is worth noting that the wettability of the wall …" | "Wall wettability …" | Filler phrase removed (2) |
| 3 | "plays a pivotal role in determining both the nucleation onset and the subsequent bubble growth ⟦CITE1⟧" | "influences both the onset of nucleation … and the subsequent bubble growth ⟦CITE1⟧" | Inflated wording replaced with a plain verb (3) |

- **Claims:** "plays a pivotal role in determining" → "influences": strength lowered slightly; scope (nucleation onset and bubble growth, on solid surfaces) kept. The "significant attention" claim was removed, not restated.
- **Warnings:** none.
- **For the author:** Issue 3 asks for the concrete cited effect (e.g. how contact angle shifts onset time and bubble growth). That direction is not stated in the original, so it was not added; please state it from [1,2] if you want it. Also consider opening with the specific question this Results section answers.

u02: PASSED after 1 attempt(s)

### u03 · passed · 校验 1 次

# Changes · u03

| # | Before | After | Reason (issue #) |
|---|---|---|---|
| 1 | "Our results clearly demonstrate that the hydrophilic surface significantly accelerates nucleation" | "The hydrophilic surface accelerated nucleation" | Removed rhetorical "clearly demonstrate" and statistical-sounding "significantly"; the change is now carried by the numbers (1) |
| 2 | One sentence chaining claim, data and inference via ":" and "which" | Claim + data in one sentence (conditions first), inference in a separate sentence | Split overlong sentence; conditions lead per IJHMT style (5) |
| 3 | "the onset time decreases from 350 ps to 125 ps" | "the onset time decreased from 350 ps to 125 ps" | Past tense for observations (4) |
| 4 | "which proves that the onset time varies monotonically" | "This result suggests that the onset time varies monotonically" | Downgraded "proves" → "suggests" (3) |

- **Claims:** "clearly demonstrate … significantly accelerates" → plain observation "accelerated" (weaker, no statistical connotation). "proves … monotonically" → "suggests" (weaker): two endpoint values cannot establish monotonicity across three angles.
- **Warnings:** none (gate passed with no warnings).
- **For the author:**
  - Issue 2 not fully resolved: the paragraph does not say which contact angle gives 350 ps and which gives 125 ps, nor which angle "the hydrophilic surface" refers to (35° or 70°). Please state, e.g., "from 350 ps at θ = 110° to 125 ps at θ = 35°" — not inferred to avoid adding facts.
  - Give the onset time at 70°; without it the monotonic-trend statement remains weakly supported.
  - State the fluid–wall pair if not given in an earlier paragraph.
  - Issue 1 suggested a percentage reduction; not added (would be a new computed value). If wanted: (350 − 125)/350 ≈ 64%, please verify.

u03: PASSED after 1 attempt(s)

### u05 · passed · 校验 2 次 · 重开 1 次

# Changes · u05

| # | Before | After | Reason (issue #) |
|---|---|---|---|
| 1 | "The trend can be interpreted using classical nucleation theory" | "The shorter onset time on the hydrophilic surface is consistent with classical nucleation theory" | Names the trend from the preceding paragraph, limited to what u03 reports (hydrophilic surface → shorter onset); hedged link to CNT (2, 1; feedback 1) |
| 2 | "where the energy barrier decreases due to the enhanced solid–liquid interaction ⟦CITE1⟧" | "in which an enhanced solid–liquid interaction is expected to lower the energy barrier ⟦CITE1⟧" | Unmeasured mechanism hedged as a CNT expectation; ⟦CITE1⟧ stays with the CNT statement (1) |
| 3 | "This innovative finding sheds light on the intricate interplay between wettability and phase change" | "This result relates wettability to the onset of nucleation under the simulated conditions" | Self-evaluation and template phrases removed; no new all-angle relation; scoped to the simulated conditions (3, 4; feedback 1) |
| 4 | "and paves the way for better cooling surfaces." | "and may be relevant to the design of cooling surfaces." | Template phrase removed; original scope (cooling surfaces) kept, hedged with "may"; no link to onset of nucleate boiling, no new design goal; ⟦BM1⟧ and ⟦BM2⟧ kept in place (5; feedback 2) |

- **Claims:** Sentence 1 weakened — mechanism changed from stated fact ("decreases due to") to "is consistent with … is expected to", because the energy barrier was not measured; trend limited to the hydrophilic surface as reported in u03. Sentence 2 weakened — "paves the way for better cooling surfaces" became "may be relevant to the design of cooling surfaces", scoped to the simulated conditions.
- **Warnings:** none.
- **For the author:** "Under the simulated conditions" refers to the wall temperature of 300 K and heat flux of 2 MW/m² in the preceding paragraph; restate them if this paragraph may be read in isolation.

u05: PASSED after 2 attempt(s)

## 3. 论断检查

# Claims · demo-docx

| Unit | Sentence (≤12 words) | Evidence | Strength orig → new | Verdict |
|---|---|---|---|---|
| u02 | "Wall wettability influences both the onset of nucleation … bubble growth" | ⟦CITE1⟧ = [1,2]; not shown in this section (bubble growth is never reported) | "plays a pivotal role in determining" (strong assertion) → "influences" (plain assertion, weaker); scope kept | ok |
| u03 | "The hydrophilic surface accelerated nucleation" | Fig. 1; onset 350 ps → 125 ps at 300 K, 2 MW/m² | "clearly demonstrate … significantly accelerates" → "show"-level observation (weaker); conditions kept; 350/125 ps still onset times, same conditions | author — as in the original, the text never says which θ gives 350 ps and which 125 ps, and "the hydrophilic surface" is ambiguous (both 35° and 70° are hydrophilic) |
| u03 | "This result suggests that the onset time varies monotonically …" | Only two onset times for three contact angles; no 70° value | "proves" → "suggests" (weaker) | author — two endpoint values cannot support monotonicity over three angles; author should give the 70° onset time |
| u05 | "The decrease in onset time … is consistent with classical nucleation theory" | ⟦CITE1⟧ = [3]; energy barrier not computed | "can be interpreted using CNT, where the barrier decreases due to …" → "is consistent with CNT … is expected to lower" (comparable relation to theory, mechanism hedged; not stronger) | author — already in the original: in textbook CNT for heterogeneous vapour-bubble nucleation the barrier factor f(θ) falls as θ increases (hydrophobic walls favour nucleation), so "lower barrier on the more wetting wall" is not the standard CNT expectation; the author must confirm that [3] supports this direction |
| u05 | "Under the simulated conditions, a smaller contact angle corresponded to an earlier onset" | Same two onset times as u03; no 70° value | Original made no such statement ("sheds light on the interplay") → unhedged general relation across contact angles | reopen — new claim, and stronger than u03, which only "suggests" the monotonic trend; the revision states it as an observed relation over all angles |
| u05 | "… may be relevant to the design of hydrophilic surfaces … nucleate boiling" | None in section: simulations report nucleation onset time (ps) at a fixed 2 MW/m², not onset of nucleate boiling (a wall-superheat/heat-flux threshold) | "paves the way for better cooling surfaces" (unhedged, vague) → "may be relevant … earlier onset of nucleate boiling" (hedged, but a new, specific application) | reopen — new application not in the original: equates the simulated nucleation onset time with onset of nucleate boiling (a different quantity) and adds the design goal "earlier ONB" |

## Reopen
- u05: Do not state a general contact-angle relation the data cannot carry — replace "a smaller contact angle corresponded to an earlier onset of nucleation" with a statement limited to what was reported (e.g. "the more hydrophilic surface showed an earlier onset of nucleation"), or hedge it to match u03 ("suggests").
- u05: Remove the new application "for an earlier onset of nucleate boiling" — the simulations measure nucleation onset time, not ONB; keep only a hedged form of the original scope, e.g. "which may be relevant to the design of cooling surfaces".

claims: 1 ok, 2 reopen, 3 author

## 4. 校验与指标

- 整节终审：PASS
- AI 套话密度：49.3 → 0.0（每千词）；强论断词：4 → 0
- 字数：142 → 125
- 保留原文的段落：无
- Word 输出：revised_tracked.docx（修订模式，可在 Word 中逐条接受/拒绝）、revised_clean.docx（干净版）；改动段落 3 个
- 逐次校验记录见 checks.md

> 投稿时请按期刊政策说明 AI 辅助编辑的使用情况。

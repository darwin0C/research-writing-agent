# 修改报告 · demo-style

目标期刊：International Journal of Heat and Mass Transfer · 改写程度：medium

## 1. 修改后文本

```latex
\section{Results and discussion}\label{sec:results}

Wall wettability affects both the nucleation onset and the later bubble growth \cite{kim2015,chen2019}. We now examine its effect on nucleation with molecular dynamics simulations.

Figure~\ref{fig:onset} shows how the vapor fraction near the wall evolves in time. We compare contact angles of 35$^\circ$, 70$^\circ$ and 110$^\circ$. At a wall temperature of 300 K, the onset time of nucleation decreased from 350 ps on the 110$^\circ$ surface to 125 ps on the 35$^\circ$ surface. This indicates that a smaller contact angle accelerates nucleation. The 70$^\circ$ surface gave an intermediate onset time of 210 ps. These results are consistent with the onset time varying monotonically with the contact angle over the range we studied.

\begin{equation}
  t_{\mathrm{on}} = t_0 \exp\left(\frac{\Delta G^*}{k_B T_w}\right)
  \label{eq:onset}
\end{equation}

We can interpret the increase in nucleation onset time with contact angle using classical nucleation theory, as expressed in Eq.~\eqref{eq:onset}. Within this framework, the trend may be attributed to a lower energy barrier $\Delta G^*$ on more hydrophilic surfaces. This lower barrier would come from the enhanced solid--liquid interaction \cite{carey2018}. This result suggests that interfacial wettability affects the onset of phase change. Under the conditions studied here, wettability could be considered in the design of cooling surfaces for electronic devices.
```

## 2. 各段修改

### u02 · styled · 校验 1 次

# Changes · u02

| # | Before | After | Reason (issue #) |
|---|---|---|---|
| 1 | "In recent years, the nucleation behavior of liquids on solid surfaces has garnered significant attention." | (deleted) | Generic opener with an uncited "attention" claim (1, 2) |
| 2 | "It is worth noting that the wettability of the wall plays a pivotal role in determining both…" | "Wall wettability affects both…" | Filler and inflated verb removed; dependence stated directly (3) |
| 3 | "In this section, we delve into the effects of wettability on the nucleation process based on our molecular dynamics simulations." | "This section examines the effect of wettability on the nucleation process using our molecular dynamics simulations." | Template verb replaced with a plain one (4) |

- **Claims:** "plays a pivotal role in determining" became "affects", which is weaker; it still rests on ⟦CITE1⟧. The deleted opener made an uncited claim about research attention, and no other content was removed.
- **Warnings:** None. The gate passed with no warnings.
- **For the author:** Issues 2 and 4 ask for details that I could not take from the paragraph, so I added none of them:
  - the fluid and the nucleation type (for example, heterogeneous vapor-bubble nucleation of <fluid> on a heated wall);
  - the contact angles examined;
  - the wall temperature;
  - the quantity compared (for example, onset time).

  Adding them would make the scope sentence specific. If you want a context sentence before the wettability statement, it needs its own citation.

u02: PASSED after 1 attempt(s)

风格校准：已采用（风格距离 original 1.45 → rewrite 1.07 → styled 0.86）

Style distance: 1.07 → 0.86
| # | Before (rewrite) | After (styled) | Habit |
|---|---|---|---|
| 1 | "This section examines the effect of wettability on the nucleation process using our molecular dynamics simulations." | "We now examine its effect on nucleation with molecular dynamics simulations." | Active "we now" opener instead of "This section …"; shorter sentence (16 → 11 words); "nucleation process" → "nucleation" (fewer nominalisations); one first-person marker, matching the author's we-rate |
| 2 | "the subsequent bubble growth" | "the later bubble growth" | Plainer word, closer to the author's short-word rhythm |

Note: the remaining nominalisation gap comes from the technical terms "nucleation" and "simulations", which cannot be replaced.

u02: STYLED, distance 1.07 → 0.86

### u03 · styled · 校验 1 次

| # | Before | After | Reason (issue #) |
|---|---|---|---|
| 1 | "presents the temporal evolution" | "shows the temporal evolution" | Plain verb for what a figure shows (style) |
| 2 | "Our results clearly demonstrate that the hydrophilic surface significantly accelerates nucleation: the onset time decreases from 350 ps … at a wall temperature of 300 K." | "At a wall temperature of 300 K, the onset time of nucleation decreased from 350 ps … to 125 ps …, which indicates that a smaller contact angle accelerates nucleation." | Data first, then the inference; removed "clearly"/"significantly" (no statistics given); past tense for observed results (1) |
| 3 | "the hydrophilic surface" | "a smaller contact angle" | Avoids ambiguity, since both 35° and 70° are hydrophilic; surfaces named by contact angle (2) |
| 4 | "Interestingly, the 70° surface exhibits an intermediate onset time of 210 ps, which proves that …" | "The 70° surface exhibited an intermediate onset time of 210 ps. These results are consistent with a monotonic variation …" | Deleted filler opener (4); split into two sentences; "proves" weakened (5) |

**Claims:**
- S2: "clearly demonstrate … significantly accelerates" → "indicates … accelerates". Weakened because no replicate runs or uncertainties are reported; "significantly" removed instead of being replaced with a computed percentage (recomputing values is not allowed).
- S4: "proves that the onset time varies monotonically" → "are consistent with a monotonic variation … over the range studied". Three contact angles cannot prove monotonicity; scope limited to the angles tested.

**Warnings:** none (gate attempt 1 failed because "three" was read as an added number; the wording was changed to "These results").

**For the author:**
- State the fluid, the wall heat flux/superheat and system size, or point to Methods (issue 3).
- Define the onset time (vapor-fraction threshold) and the width of the "near the wall" region (issue 3).
- If replicate runs exist, give their number and the uncertainty on the onset times; you may then report the relative reduction in onset time (issue 1).
- Optionally give the range explicitly (35°–110°) in the last sentence; it was not added here to avoid introducing new numbers.

u03: PASSED after 2 attempt(s)

风格校准：已采用（风格距离 original 1.95 → rewrite 2.03 → styled 1.22）

Style distance: 1.53 → 0.72
| # | Before (rewrite) | After (styled) | Habit |
|---|---|---|---|
| 1 | "Fig.~⟦REF1⟧ shows the temporal evolution of the vapor fraction near the wall for contact angles of …" | "Figure~⟦REF1⟧ shows how the vapor fraction near the wall evolves in time. We compare contact angles of …" | "Figure" preference; split long sentence; nominalisation → verb; "we" active voice |
| 2 | "At a wall temperature of 300 K, the onset time … to 125 ps on the 35⟦MATH5⟧ surface, which indicates that a smaller contact angle accelerates nucleation." | "… to 125 ps on the 35⟦MATH5⟧ surface. This indicates that a smaller contact angle accelerates nucleation." | Shorter sentences (data and inference split; hedge "indicates" kept) |
| 3 | "The 70⟦MATH6⟧ surface exhibited an intermediate onset time" | "The 70⟦MATH6⟧ surface gave an intermediate onset time" | Plainer verb |
| 4 | "consistent with a monotonic variation of the onset time with the contact angle over the range studied" | "consistent with the onset time varying monotonically with the contact angle over the range we studied" | Nominalisation → verb; "we"; scope condition kept |

u03: STYLED, distance 1.53 → 0.72

### u05 · styled · 校验 1 次

| # | Before | After | Reason (issue #) |
|---|---|---|---|
| 1 | "The trend can be interpreted using classical nucleation theory" | "The increase in nucleation onset time with contact angle can be interpreted using classical nucleation theory" | Names the trend from the previous paragraph (1) |
| 2 | "where the energy barrier ⟦MATH1⟧ decreases on more hydrophilic surfaces due to the enhanced solid--liquid interaction ⟦CITE1⟧" | Split into a new sentence: "Within this framework, the trend may be attributed to a lower energy barrier ⟦MATH1⟧ on more hydrophilic surfaces, resulting from the enhanced solid--liquid interaction ⟦CITE1⟧." | Asserted mechanism hedged to an interpretation; one idea per sentence (2) |
| 3 | "This innovative finding sheds light on the intricate interplay between interfacial wettability and phase change" | "This result suggests that interfacial wettability affects the onset of phase change" | Removed template phrases and self-praise; concrete statement (3, 4) |
| 4 | "and paves the way for the rational design of high-performance cooling surfaces for next-generation electronic devices" | "and that, under the conditions studied here, wettability could be considered in the design of cooling surfaces for electronic devices" | Removed template phrase; hedged and scoped the design implication; dropped "high-performance", "next-generation" (5) |

- **Claims:** S2 weakened from asserted "decreases … due to" to "may be attributed to" (mechanism not shown in this paragraph). S3 now "suggests" (was implicit assertion via "sheds light on"). Design implication weakened from "paves the way for the rational design of high-performance …" to "could be considered", scoped to "the conditions studied here".
- **Warnings:** none.
- **For the author:** (a) Issue 2: standard heterogeneous CNT predicts a *lower* barrier on more hydrophobic walls; the paragraph claims the opposite. I did not add an explanation (e.g., enhanced heat transfer from stronger solid–liquid coupling) because it would be a new mechanism — please add it with support (data or a citation beyond ⟦CITE1⟧ if carey2018 does not cover it), or reconsider the interpretation. (b) Consider stating the studied conditions explicitly (wall temperature 300 K, three contact angles) in place of "the conditions studied here", or moving the design implication to the Conclusions. (c) Check that "nucleation onset time increasing with contact angle" correctly names the trend from the preceding paragraph.

u05: PASSED after 1 attempt(s)

风格校准：已采用（风格距离 original 1.71 → rewrite 1.79 → styled 1.7）

Style distance: 1.79 → 1.70
| # | Before (rewrite) | After (styled) | Habit |
|---|---|---|---|
| 1 | "The increase in nucleation onset time with contact angle can be interpreted using classical nucleation theory" | "We can interpret the increase in nucleation onset time with contact angle using classical nucleation theory" | Active "we" instead of agentless passive |
| 2 | "…on more hydrophilic surfaces, resulting from the enhanced solid--liquid interaction ⟦CITE1⟧." | "…on more hydrophilic surfaces. This lower barrier would come from the enhanced solid--liquid interaction ⟦CITE1⟧." | Shorter sentences (split) |
| 3 | "This result suggests that interfacial wettability affects the onset of phase change and that, under the conditions studied here, wettability could be considered in the design…" | "This result suggests that interfacial wettability affects the onset of phase change. Under the conditions studied here, wettability could be considered in the design…" | Shorter sentences (split); scope condition kept |

Note: hedges (can, may, would, suggests, could, "under the conditions studied here") are all needed and were kept, so the hedge and nominalisation features stay high; mean sentence length fell 25 → 15.4.

u05: STYLED, distance 1.79 → 1.70

## 3. 论断检查

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

## 4. 校验与指标

- 整节终审：PASS
- AI 套话密度：46.9 → 0.0（每千词）；强论断词：4 → 0
- 字数：192 → 178
- 风格距离（越小越像你，按 results 段落画像）：2.39 → 1.9
- 保留原文的段落：无
- 逐次校验记录见 checks.md

> 投稿时请按期刊政策说明 AI 辅助编辑的使用情况。

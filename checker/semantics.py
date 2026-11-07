"""Meaning checks that go beyond "same numbers":

L3 direction    "from A to B" reversed (error); verb contradicting the numbers when the
                original agreed (error); quantitative sentence flips increase↔decrease (warning).
L4 scope        comparators tied to numbers: "less than 5 nm" → "5 nm" (error),
                "approximately 210 ps" → "210 ps" (warning); scope phrases such as
                "under the investigated conditions" dropped (warning).
L5 claim        claim-verb ladder prove > demonstrate > show > indicate > suggest:
                strongest level rises (error); more strong verbs (warning);
                intensifiers added / hedges removed (warning).

All checks work on prose with LaTeX protected content removed.
"""

from __future__ import annotations

import re
from collections import Counter

from .invariants import _NUM_RE, _UNIT_RE, _norm_num, split_sentences
from .latex_mask import mask, strip_placeholders

Finding = tuple[str, str, str]  # (level, layer, message)

NUM = r"[-+−]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?"


def _prose(text: str) -> str:
    return strip_placeholders(mask(text).text)


def _values(sentence: str) -> list[str]:
    return [_norm_num(m.group("num")) for m in _NUM_RE.finditer(sentence)]


# ------------------------------------------------------------------ L3 direction

UP = (r"increas\w*|ris(?:e|es|ing)|rose|risen|grow(?:s|n|ing)?|grew|higher|larger|greater|"
      r"longer|enhanc\w*|elevat\w*|rais(?:e|es|ed|ing)|expand\w*|faster|accelerat\w*|"
      r"improv\w*|augment\w*|extend\w*|prolong\w*")
DOWN = (r"decreas\w*|reduc\w*|declin\w*|drop(?:s|ped|ping)?|fall(?:s|ing)?|fell|fallen|"
        r"lower(?:ed|s|ing)?|smaller|shorter|shorten\w*|diminish\w*|suppress\w*|weaken\w*|"
        r"slower|shr(?:ink|inks|ank|unk)|decelerat\w*|delay\w*|deteriorat\w*|degrad\w*|contract\w*")
_UP_RE = re.compile(r"\b(?:" + UP + r")\b", re.I)
_DOWN_RE = re.compile(r"\b(?:" + DOWN + r")\b", re.I)
_FROM_TO = re.compile(
    r"\bfrom\s+(?:about\s+|approximately\s+|~\s*)?(?P<a>" + NUM + r")(?:\s*(?:" + _UNIT_RE + r"))?"
    r"[^.;]{0,80}?\bto\s+(?:about\s+|approximately\s+|~\s*)?(?P<b>" + NUM + r")", re.I)


ANTONYMS = [
    (r"higher|highest", r"lower|lowest"), (r"increas\w*", r"decreas\w*"),
    (r"larger|largest|greater", r"smaller|smallest|less"), (r"longer|longest", r"shorter|shortest"),
    (r"faster|fastest", r"slower|slowest"), (r"ris(?:e|es|ing)|rose|risen", r"fall(?:s|ing)?|fell|fallen"),
    (r"grow(?:s|n|ing)?|grew", r"shr(?:ink|inks|ank|unk)"), (r"enhanc\w*|improv\w*", r"reduc\w*|deteriorat\w*|degrad\w*"),
    (r"accelerat\w*", r"decelerat\w*|delay\w*"), (r"rais(?:e|es|ed|ing)", r"lower(?:s|ed|ing)"),
    (r"above", r"below"), (r"thicker", r"thinner"), (r"wider", r"narrower"), (r"stronger", r"weaker"),
]
ANTONYMS_ZH = [("提高|升高", "降低"), ("增加|增大|增多", "减少|减小"), ("延长", "缩短"),
               ("加快|加速", "减缓|减慢|延迟"), ("高于", "低于"), ("大于", "小于"), ("增强", "减弱"),
               ("上升", "下降")]


def _antonym_swaps(a: str, b: str) -> list[str]:
    out = []
    for x, y in ANTONYMS:
        cx = lambda t, p: len(re.findall(r"\b(?:" + p + r")\b", t, re.I))
        ax, ay, bx, by = cx(a, x), cx(a, y), cx(b, x), cx(b, y)
        if (bx < ax and by > ay) or (by < ay and bx > ax):
            out.append(x.split("|")[0].replace("\\w*", "") + "/" + y.split("|")[0].replace("\\w*", ""))
    for x, y in ANTONYMS_ZH:
        ax, ay, bx, by = (len(re.findall(p, t)) for t, p in ((a, x), (a, y), (b, x), (b, y)))
        if (bx < ax and by > ay) or (by < ay and bx > ax):
            out.append(x.split("|")[0] + "/" + y.split("|")[0])
    return out


UP_ZH = re.compile(r"增加|提高|升高|增大|延长|上升|增强|加快|加速|扩大|改善|提升|增多")
DOWN_ZH = re.compile(r"降低|减少|下降|减小|缩短|减弱|减缓|抑制|延迟|恶化|变小|减慢|降至")
_FROM_TO_ZH = re.compile(
    r"(?:从|由)\s*(?P<a>" + NUM + r")\s*(?:" + _UNIT_RE + r")?[^。；，,]{0,20}?(?:到|至)\s*(?P<b>" + NUM + r")")


def _ups(s: str) -> int:
    return len(_UP_RE.findall(s)) + len(UP_ZH.findall(s))


def _downs(s: str) -> int:
    return len(_DOWN_RE.findall(s)) + len(DOWN_ZH.findall(s))


def _polarity(s: str) -> int:
    return _ups(s) - _downs(s)


def _from_to_pairs(sentence: str) -> list[tuple[str, str, int]]:
    """(a, b, verb polarity just before 'from' in the same clause)."""
    out = []
    for m in _FROM_TO.finditer(sentence):
        clause = re.split(r"[,;:]", sentence[: m.start()])[-1]
        words = clause.split()[-8:]
        pol = _polarity(" ".join(words))
        out.append((_norm_num(m.group("a")), _norm_num(m.group("b")), pol))
    for m in _FROM_TO_ZH.finditer(sentence):
        pol = _polarity(sentence[max(0, m.start() - 12): m.end() + 4])
        out.append((_norm_num(m.group("a")), _norm_num(m.group("b")), pol))
    return out


def _best_match(values: list[str], candidates: list[str]) -> int | None:
    if not values:
        return None
    want = Counter(values)
    best, score = None, 0
    for i, c in enumerate(candidates):
        s = sum((want & Counter(_values(c))).values())
        if s > score:
            best, score = i, s
    return best if score >= max(1, (len(set(values)) + 1) // 2) else None


def direction_findings(original: str, revised: str) -> list[Finding]:
    out: list[Finding] = []
    s0, s1 = split_sentences(_prose(original)), split_sentences(_prose(revised))

    pairs0 = [p for s in s0 for p in _from_to_pairs(s)]
    pairs1 = [p for s in s1 for p in _from_to_pairs(s)]
    have1 = {(a, b) for a, b, _ in pairs1}
    for a, b, pol0 in pairs0:
        if (a, b) not in have1 and (b, a) in have1:
            out.append(("error", "L3-direction", f"'from {a} … to {b}' became 'from {b} … to {a}'"))
            continue
        try:
            sign = (float(b) > float(a)) - (float(b) < float(a))
        except ValueError:
            continue
        for a1, b1, pol1 in pairs1:
            if (a1, b1) == (a, b) and sign and pol1 and pol0 * sign >= 0 and pol1 * sign < 0:
                out.append(("error", "L3-direction",
                            f"verb now contradicts the numbers: {a} → {b} is "
                            f"{'an increase' if sign > 0 else 'a decrease'}"))

    for s in s0:
        vals = _values(s)
        p0 = _polarity(s)
        if not vals or not (_ups(s) or _downs(s)):
            continue
        j = _best_match(vals, s1)
        if j is None:
            continue
        u0, d0 = _ups(s), _downs(s)
        u1, d1 = _ups(s1[j]), _downs(s1[j])
        p1 = u1 - d1
        swaps = _antonym_swaps(s, s1[j])
        if swaps or (p1 and (p0 > 0) != (p1 > 0)) or (u1 < u0 and d1 > d0) or (d1 < d0 and u1 > u0):
            if not any(f[1] == "L3-direction" and f[0] == "error" for f in out):
                out.append(("warning", "L3-direction",
                            f"increase/decrease wording flipped around {', '.join(sorted(set(vals)))}"
                            + (f" ({', '.join(swaps)})" if swaps else "") + " "
                            f"— confirm the direction of change is unchanged"))
    return out


# ------------------------------------------------------------------ L4 scope

_STRICT = {
    "lt": r"less\s+than|lower\s+than|smaller\s+than|shorter\s+than|below|up\s+to|at\s+most|"
          r"not\s+exceeding|<|≤|<=",
    "gt": r"greater\s+than|more\s+than|higher\s+than|larger\s+than|longer\s+than|above|"
          r"exceeding|in\s+excess\s+of|at\s+least|>|≥|>=",
}
_APPROX = (r"approximately|approx\.|about|around|nearly|roughly|almost|circa|ca\.|~|∼|≈|"
           r"of\s+the\s+order\s+of|on\s+the\s+order\s+of")
_RANGE = r"between\s+" + NUM + r"(?:\s*(?:" + _UNIT_RE + r"))?\s+and"


_STRICT_ZH = {"lt": r"小于|低于|不超过|少于|不足|不高于", "gt": r"大于|高于|超过|不低于|至少|多于"}
_APPROX_ZH = r"(?:大约|约|接近|将近|近)(?:有|为|是)?"  # 约有 / 约为 / 大约是 …


def _comparators(prose: str) -> Counter:
    c: Counter = Counter()
    for kind, pat in list(_STRICT_ZH.items()) + [("approx", _APPROX_ZH)]:
        for m in re.finditer(r"(?:" + pat + r")\s*(?P<n>" + NUM + r")", prose):
            c[(kind, _norm_num(m.group("n")))] += 1
    for m in re.finditer(r"(?P<n>" + NUM + r")\s*(?:" + _UNIT_RE + r")?\s*(?:左右|上下)", prose):
        c[("approx", _norm_num(m.group("n")))] += 1
    for kind, pat in list(_STRICT.items()) + [("approx", _APPROX)]:
        for m in re.finditer(r"(?<![\w])(?:" + pat + r")\s*(?P<n>" + NUM + r")", prose, re.I):
            c[(kind, _norm_num(m.group("n")))] += 1
    for m in re.finditer(r"\b" + _RANGE + r"\s*(?P<n>" + NUM + r")", prose, re.I):
        c[("range", _norm_num(m.group("n")))] += 1
    return c


SCOPE_PATTERNS = [
    r"\b(?:under|within|for|in|over|at)\s+the\s+(?:investigated|present|studied|considered|"
    r"examined|tested|simulated|current|given|explored)\s+(?:conditions?|ranges?|cases?|"
    r"parameters?|configurations?|regimes?|geometr(?:y|ies))",
    r"\b(?:conditions?|ranges?|cases?|parameters?|configurations?|regimes?)\s+(?:studied|"
    r"investigated|considered|examined|tested|simulated|explored)(?:\s+here|\s+in\s+this\s+\w+)?",
    r"\bin\s+(?:the\s+)?(?:present|this|our)\s+(?:study|work|simulations?|experiments?|"
    r"investigation|model)",
    r"\b(?:in|over|within)\s+the\s+range\s+(?:of|from|studied|considered|investigated)",
    r"\bfor\s+the\s+(?:fluids?|surfaces?|geometr(?:y|ies)|materials?)\s+(?:considered|studied|tested)",
    r"\bat\s+(?:low|high|moderate)\s+(?:heat\s+fluxe?s?|mass\s+fluxe?s?|pressures?|superheats?|"
    r"Reynolds\s+numbers?|temperatures?)",
    r"在本(?:研究|文|实验|模拟)(?:的|所)?(?:考察|研究|测试)?(?:的)?(?:条件|范围|工况|参数范围)(?:下|内)",
    r"在所(?:研究|考察|测试|模拟)的(?:条件|范围|工况|参数范围)(?:下|内)",
    r"在(?:本|该)?(?:实验|模拟|计算)?(?:条件|工况)下",
    r"在[^。；，]{1,12}范围内",
]
_SCOPE_RE = re.compile("|".join(f"(?:{p})" for p in SCOPE_PATTERNS), re.I)


def scope_findings(original: str, revised: str) -> list[Finding]:
    out: list[Finding] = []
    p0, p1 = _prose(original), _prose(revised)
    c0, c1 = _comparators(p0), _comparators(p1)
    for (kind, n), k in (c0 - c1).items():
        replaced = [kk for (kk, nn) in (c1 - c0) if nn == n]
        if kind in ("lt", "gt", "range"):
            what = {"lt": "upper bound", "gt": "lower bound", "range": "range"}[kind]
            out.append(("error", "L4-qualifier",
                        f"{what} on {n} removed or changed" + (f" (now: {replaced[0]})" if replaced else "")))
        else:
            out.append(("warning", "L4-qualifier",
                        f"approximation on {n} removed — value now reads as exact"))
    for (kind, n), k in (c1 - c0).items():
        if kind in ("lt", "gt") and not any(nn == n for (_, nn) in (c0 - c1)):
            out.append(("error", "L4-qualifier", f"new bound added on {n} ('{kind}')"))

    s0 = [m.group(0) for m in _SCOPE_RE.finditer(p0)]
    s1 = [m.group(0) for m in _SCOPE_RE.finditer(p1)]
    if len(s1) < len(s0):
        kept = " ".join(s1).lower()
        lost = [s for s in s0 if s.lower() not in kept][: len(s0) - len(s1)] or s0[: len(s0) - len(s1)]
        out.append(("warning", "L4-scope",
                    "scope condition dropped: " + "; ".join(f"'{_ws(s)}'" for s in lost)))
    return out


def _ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


# ------------------------------------------------------------------ L5 claim strength

LADDER = [
    (5, r"prov(?:e|es|ed|en|ing)|proof"),
    (4, r"demonstrat\w*|confirm\w*|establish\w*|verif(?:y|ies|ied)|validat\w*"),
    (3, r"show(?:s|n|ed|ing)?|reveal\w*"),
    (2, r"indicat\w*|evidenc(?:e|es)"),
    (1, r"suggest\w*|impl(?:y|ies|ied)|hint\w*"),
]
INTENSIFIERS = [
    "clearly", "undoubtedly", "definitely", "certainly", "obviously", "always", "never",
    "dramatically", "remarkably", "significantly", "substantially", "markedly",
    "for the first time", "novel", "unprecedented", "superior", "breakthrough",
    "fully", "completely", "conclusively", "unambiguously",
    "显著", "极大", "大幅", "首次", "国际领先", "国际先进", "突破性", "革命性", "颠覆性",
    "完全", "彻底", "毫无疑问", "必然", "填补",
]
HEDGES = ["may", "might", "could", "possibly", "likely", "appear", "appears", "appeared",
          "seem", "seems", "tend to", "tends to", "presumably", "potentially",
          "可能", "或许", "也许", "有望", "初步", "在一定程度上", "倾向于", "似乎", "推测"]


LADDER_ZH = [(5, r"证明|证实"), (4, r"验证了|确证|确认|充分说明"), (3, r"表明|显示|揭示"),
             (2, r"说明|指示"), (1, r"提示|暗示|意味着")]


def _levels(prose: str) -> Counter:
    c: Counter = Counter()
    for level, pat in LADDER:
        c[level] += len(re.findall(r"\b(?:" + pat + r")\b", prose, re.I))
    for level, pat in LADDER_ZH:
        c[level] += len(re.findall(pat, prose))
    return +c


def _count_words(prose: str, words: list[str]) -> Counter:
    c: Counter = Counter()
    for w in words:
        body = r"\s+".join(map(re.escape, w.split()))
        pat = (r"\b" + body + r"\b") if w.isascii() else body
        n = len(re.findall(pat, prose, re.I))
        if n:
            c[w] = n
    return c


def claim_findings(original: str, revised: str) -> list[Finding]:
    out: list[Finding] = []
    p0, p1 = _prose(original), _prose(revised)
    l0, l1 = _levels(p0), _levels(p1)
    names = {5: "prove", 4: "demonstrate/confirm", 3: "show", 2: "indicate", 1: "suggest"}
    m0, m1 = max(l0, default=0), max(l1, default=0)
    if m1 > m0 and m1 >= 3:
        out.append(("error", "L5-claim",
                    f"strongest claim verb rose from '{names.get(m0, 'none')}' to '{names[m1]}'"))
    elif m1 > m0 and m1 == 2:
        out.append(("warning", "L5-claim",
                    f"claim verb '{names[m1]}' added where the original had at most '{names.get(m0, 'none')}'"))
    elif m1 <= m0:  # 'suggest' (level 1) is a hedge, never a strengthening
        for level in (5, 4, 3):
            n0 = sum(v for k, v in l0.items() if k >= level)
            n1 = sum(v for k, v in l1.items() if k >= level)
            if n1 > n0:
                out.append(("warning", "L5-claim",
                            f"more claims at '{names[level]}' strength or above ({n0} → {n1})"))
                break
    for w, n in (_count_words(p1, INTENSIFIERS) - _count_words(p0, INTENSIFIERS)).items():
        out.append(("warning", "L5-claim", f"intensifier added ({n}×): '{w}'"))
    for w, n in (_count_words(p0, HEDGES) - _count_words(p1, HEDGES)).items():
        out.append(("warning", "L5-claim", f"hedge removed ({n}×): '{w}'"))
    return out

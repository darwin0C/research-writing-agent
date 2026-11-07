"""Word (.docx) support with the standard library only.

Reading: each body-level paragraph becomes plain text in which everything the model
must not touch is a placeholder:

  ⟦EQ1⟧    Word equation (OMML)            ⟦CITE1⟧  Zotero / EndNote / Mendeley field
  ⟦REF1⟧   cross-reference field (REF …)   ⟦SEQ1⟧   caption numbering field
  ⟦FLD1⟧   any other field                 ⟦FMT1⟧   italic / bold / super- / subscript run
  ⟦LINK1⟧  hyperlink                       ⟦OBJ1⟧   image, footnote mark, symbol, …
  ⟦BM1⟧ ⟦MK1⟧ bookmarks, comment anchors   (zero-width, must stay in place)

Writing: only paragraphs that changed are rebuilt; every other byte of the package is
copied unchanged. Changes are written as Word tracked changes (w:ins / w:del) at word
level, or as a clean copy. Protected objects are re-inserted from their original XML.

Limitations: tables, text boxes, headers/footers, footnote text and paragraphs that
already contain tracked changes are left untouched. A protected object that moves
inside a paragraph is moved without tracking (the words around it are tracked).
"""

from __future__ import annotations

import difflib
import html
import re
import time
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

_TAG = re.compile(r"<(/?)([A-Za-z_][\w.\-]*(?::[\w.\-]+)?)((?:\s[^<>]*?)?)(/?)>")
_HEADING_STYLE = re.compile(r'<w:pStyle\s+w:val="(?:Heading|heading|Title|Subtitle|TOC|标题)[^"]*"')
_FORMATTED = re.compile(
    r'<w:(?:i|b|strike|dstrike|caps|smallCaps)(?:\s+w:val="(?:1|true|on)")?\s*/>'
    r'|<w:vertAlign\s+w:val="(?:superscript|subscript)"\s*/>'
    r'|<w:u\s+w:val="(?!none)[^"]*"\s*/>')
AUTHOR = "Claude (research-writing-agent)"


def _children(xml: str, start: int, end: int) -> list[tuple[str, int, int]]:
    """Top-level elements between start and end: (name, abs_start, abs_end)."""
    out, depth, cur = [], 0, None
    for m in _TAG.finditer(xml, start, end):
        closing, name, _, selfclose = m.group(1), m.group(2), m.group(3), m.group(4)
        if closing:
            depth -= 1
            if depth == 0 and cur:
                out.append((cur[0], cur[1], m.end()))
                cur = None
        elif selfclose:
            if depth == 0:
                out.append((name, m.start(), m.end()))
        else:
            if depth == 0:
                cur = (name, m.start())
            depth += 1
    return out


def _inner(xml: str, s: int, e: int) -> tuple[int, int]:
    """Span of an element's content (between its open and close tag)."""
    open_end = xml.index(">", s) + 1
    if xml[open_end - 2] == "/":
        return open_end, open_end
    return open_end, xml.rindex("</", s, e)


def _texts(fragment: str, tag: str = "w:t") -> str:
    return "".join(html.unescape(m.group(1)) for m in
                   re.finditer(r"<" + tag + r"(?:\s[^>]*)?>(.*?)</" + tag + ">", fragment, re.S))


def _esc(t: str) -> str:
    return html.escape(t, quote=False)


@dataclass
class Paragraph:
    index: int            # position among body-level paragraphs
    start: int
    end: int
    open_tag: str
    ppr: str
    text: str             # with placeholders
    mapping: dict[str, str] = field(default_factory=dict)   # placeholder -> raw XML
    display: dict[str, str] = field(default_factory=dict)   # placeholder -> readable text
    base_rpr: str = ""
    heading: bool = False
    tracked: bool = False


@dataclass
class Docx:
    path: Path
    xml: str
    paragraphs: list[Paragraph]


def _classify_field(instr: str) -> str:
    u = instr.upper()
    if any(k in u for k in ("ZOTERO_ITEM", "ADDIN EN.CITE", "CSL_CITATION", "MENDELEY",
                             "ADDIN CITATION", " CITATION ", "ADDIN NE.REF")):
        return "CITE"
    if re.search(r"\b(?:REF|PAGEREF|NOTEREF)\b", u):
        return "REF"
    if re.search(r"\bSEQ\b", u):
        return "SEQ"
    return "FLD"


def _parse_paragraph(xml: str, index: int, s: int, e: int) -> Paragraph:
    open_end = xml.index(">", s) + 1
    open_tag = xml[s:open_end]
    p = Paragraph(index, s, e, open_tag, "", "")
    if open_tag.endswith("/>"):
        return p
    a, b = _inner(xml, s, e)
    pieces: list[str] = []
    counters: Counter = Counter()
    rprs: Counter = Counter()
    goback: set[str] = set()
    field_buf: list[str] = []
    field_depth = 0

    def hold(kind: str, raw: str, display: str = "") -> None:
        counters[kind] += 1
        key = f"⟦{kind}{counters[kind]}⟧"
        p.mapping[key] = raw
        p.display[key] = display
        pieces.append(key)

    for name, cs, ce in _children(xml, a, b):
        raw = xml[cs:ce]
        if field_depth:
            field_buf.append(raw)
            field_depth += raw.count('w:fldCharType="begin"') - raw.count('w:fldCharType="end"')
            if field_depth <= 0:
                field_depth = 0
                whole = "".join(field_buf)
                instr = _texts(whole, "w:instrText")
                after = whole.split('w:fldCharType="separate"', 1)[-1] if "separate" in whole else ""
                hold(_classify_field(instr), whole, _texts(after))
                field_buf = []
            continue
        if name == "w:pPr":
            p.ppr = raw
            p.heading = bool(_HEADING_STYLE.search(raw)) or "<w:outlineLvl" in raw
        elif name == "w:proofErr":
            continue
        elif name == "w:bookmarkStart" and 'w:name="_GoBack"' in raw:
            goback.add(re.search(r'w:id="([^"]*)"', raw).group(1))
        elif name == "w:bookmarkEnd" and re.search(r'w:id="([^"]*)"', raw).group(1) in goback:
            continue
        elif name in ("w:bookmarkStart", "w:bookmarkEnd"):
            hold("BM", raw)
        elif name in ("w:commentRangeStart", "w:commentRangeEnd", "w:permStart", "w:permEnd"):
            hold("MK", raw)
        elif name in ("m:oMath", "m:oMathPara"):
            hold("EQ", raw, _texts(raw, "m:t"))
        elif name == "w:fldSimple":
            instr = html.unescape(re.search(r'w:instr="([^"]*)"', raw).group(1))
            hold(_classify_field(instr), raw, _texts(raw))
        elif name == "w:hyperlink":
            hold("LINK", raw, _texts(raw))
        elif name in ("w:ins", "w:del", "w:moveFrom", "w:moveTo"):
            p.tracked = True
            hold("OBJ", raw, _texts(raw))
        elif name == "w:r":
            begins = raw.count('w:fldCharType="begin"')
            if begins:
                field_buf = [raw]
                field_depth = begins - raw.count('w:fldCharType="end"')
                if field_depth <= 0:
                    field_depth = 0
                    hold(_classify_field(_texts(raw, "w:instrText")), raw)
                    field_buf = []
                continue
            if re.search(r"<w:(?:drawing|pict|object|footnoteReference|endnoteReference|"
                         r"commentReference|sym|ruby|fldChar|instrText)\b", raw):
                hold("OBJ", raw, _texts(raw))
                continue
            rpr_m = re.search(r"<w:rPr>.*?</w:rPr>|<w:rPr/>", raw, re.S)
            rpr = rpr_m.group(0) if rpr_m else ""
            text = ""
            ra, rb = _inner(raw, 0, len(raw))
            kids = _children(raw, ra, rb)
            for cname, xs, xe in kids:
                frag = raw[xs:xe]
                if cname == "w:t":
                    text += _texts(frag)
                elif cname == "w:tab":
                    text += "\t"
                elif cname in ("w:br", "w:cr"):
                    text += " "
                elif cname == "w:noBreakHyphen":
                    text += "-"
            if not text:
                harmless = {"w:rPr", "w:t", "w:tab", "w:br", "w:cr", "w:lastRenderedPageBreak"}
                if not {k[0] for k in kids} <= harmless:
                    hold("OBJ", raw)
                continue
            if _FORMATTED.search(rpr) and text.strip():
                hold("FMT", raw, text)
            else:
                pieces.append(text)
                rprs[rpr] += len(text)
        else:
            hold("OBJ", raw, _texts(raw))
    if field_buf:  # unterminated field: keep as is
        hold("FLD", "".join(field_buf))
    p.text = "".join(pieces)
    p.base_rpr = rprs.most_common(1)[0][0] if rprs else ""
    return p


def read(path: Path | str) -> Docx:
    path = Path(path)
    with zipfile.ZipFile(path) as z:
        xml = z.read("word/document.xml").decode("utf-8")
    m = re.search(r"<w:body>", xml)
    body_start, body_end = m.end(), xml.rindex("</w:body>")
    paras = []
    for name, s, e in _children(xml, body_start, body_end):
        if name == "w:p":
            paras.append(_parse_paragraph(xml, len(paras), s, e))
    return Docx(path, xml, paras)


# ------------------------------------------------------------------ writing

_TOKEN = re.compile(r"⟦[A-Z]+\d+⟧|\s+|\w+|[^\w\s]")


def _text_runs(text: str, rpr: str, deleted: bool = False) -> str:
    out = []
    for i, part in enumerate(text.split("\t")):
        if i:
            out.append(f"<w:r>{rpr}<w:tab/></w:r>")
        if part:
            tag = "w:delText" if deleted else "w:t"
            out.append(f'<w:r>{rpr}<{tag} xml:space="preserve">{_esc(part)}</{tag}></w:r>')
    return "".join(out)


class _Ids:
    def __init__(self, xml: str):
        ids = [int(x) for x in re.findall(r'w:id="(\d+)"', xml)]
        self.n = (max(ids) if ids else 0) + 1000

    def next(self) -> int:
        self.n += 1
        return self.n


def build_paragraph(p: Paragraph, new_text: str, tracked: bool, ids: _Ids, date: str) -> str:
    old_toks, new_toks = _TOKEN.findall(p.text), _TOKEN.findall(new_text)
    body: list[str] = []
    is_ph = lambda t: t.startswith("⟦") and t in p.mapping

    def emit(tokens: list[str], mode: str) -> None:
        buf = ""

        def flush() -> None:
            nonlocal buf
            if not buf:
                return
            if mode == "del":
                body.append(f'<w:del w:id="{ids.next()}" w:author="{AUTHOR}" w:date="{date}">'
                            f"{_text_runs(buf, p.base_rpr, deleted=True)}</w:del>")
            elif mode == "ins":
                body.append(f'<w:ins w:id="{ids.next()}" w:author="{AUTHOR}" w:date="{date}">'
                            f"{_text_runs(buf, p.base_rpr)}</w:ins>")
            else:
                body.append(_text_runs(buf, p.base_rpr))
            buf = ""

        for t in tokens:
            if is_ph(t):
                flush()
                if mode != "del":  # a moved object appears once, at its new place
                    body.append(p.mapping[t])
            else:
                buf += t
        flush()

    if not tracked:
        emit(new_toks, "eq")
    else:
        sm = difflib.SequenceMatcher(a=old_toks, b=new_toks, autojunk=False)
        for op, i1, i2, j1, j2 in sm.get_opcodes():
            if op == "equal":
                emit(new_toks[j1:j2], "eq")
            if op in ("delete", "replace"):
                emit(old_toks[i1:i2], "del")
            if op in ("insert", "replace"):
                emit(new_toks[j1:j2], "ins")
    return p.open_tag + p.ppr + "".join(body) + "</w:p>"


def write(doc: Docx, new_texts: dict[int, str], out: Path | str, tracked: bool = True) -> int:
    """new_texts: paragraph index -> new text (with the same placeholders). Returns the
    number of paragraphs rewritten."""
    ids, date = _Ids(doc.xml), time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    xml, n = doc.xml, 0
    for p in sorted(doc.paragraphs, key=lambda p: -p.start):
        new = new_texts.get(p.index)
        if new is None or new == p.text or p.tracked:
            continue
        missing = [k for k in p.mapping if new.count(k) != 1]
        if missing:
            raise ValueError(f"paragraph {p.index}: protected objects missing or duplicated: {missing}")
        xml = xml[: p.start] + build_paragraph(p, new, tracked, ids, date) + xml[p.end:]
        n += 1
    out = Path(out)
    with zipfile.ZipFile(doc.path) as zin, zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            data = xml.encode("utf-8") if info.filename == "word/document.xml" else zin.read(info)
            zout.writestr(info, data)
    return n


# ------------------------------------------------------------------ minimal writer

_CT = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
       '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
       '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
       '<Default Extension="xml" ContentType="application/xml"/>'
       '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-'
       'officedocument.wordprocessingml.document.main+xml"/></Types>')
_RELS = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
         '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
         '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
         'relationships/officeDocument" Target="word/document.xml"/></Relationships>')
NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"')


def write_document(path: Path | str, body_xml: str) -> None:
    doc = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {NS}>'
           f"<w:body>{body_xml}<w:sectPr/></w:body></w:document>")
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", _CT)
        z.writestr("_rels/.rels", _RELS)
        z.writestr("word/document.xml", doc)


def para(*runs: tuple[str, str], style: str | None = None) -> str:
    """runs: (text, flags) with flags from 'b' bold, 'i' italic, 'g' grey, 'u' blue."""
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ""
    out = []
    for text, flags in runs:
        rpr = "".join(x for f, x in (("b", "<w:b/>"), ("i", "<w:i/>"),
                                     ("g", '<w:color w:val="666666"/>'),
                                     ("u", '<w:color w:val="1F4E79"/>')) if f in flags)
        out.append(_text_runs(text, f"<w:rPr>{rpr}</w:rPr>" if rpr else ""))
    return f"<w:p>{ppr}{''.join(out)}</w:p>"

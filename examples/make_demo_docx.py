"""Build examples/section.docx: a Word version of the demo section with the things real
papers contain — heading style, split runs, italic symbols, superscript units, a Zotero
citation field, an OMML equation, a cross-reference field, a bookmark, a table, and the
mc:Ignorable / w14 namespaces Word writes.

    python3 examples/make_demo_docx.py
"""

import zipfile
from pathlib import Path

OUT = Path(__file__).resolve().parent / "section.docx"

NS = ('xmlns:wpc="http://schemas.microsoft.com/office/word/2010/wordprocessingCanvas" '
      'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:m="http://schemas.openxmlformats.org/officeDocument/2006/math" '
      'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:w14="http://schemas.microsoft.com/office/word/2010/wordml" '
      'mc:Ignorable="w14"')

R = '<w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/></w:rPr><w:t xml:space="preserve">{}</w:t></w:r>'
I = '<w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/><w:i/></w:rPr><w:t>{}</w:t></w:r>'
SUP = '<w:r><w:rPr><w:rFonts w:ascii="Times New Roman" w:hAnsi="Times New Roman"/><w:vertAlign w:val="superscript"/></w:rPr><w:t>{}</w:t></w:r>'


def zotero(display: str, key: str) -> str:
    instr = (f' ADDIN ZOTERO_ITEM CSL_CITATION {{&quot;citationID&quot;:&quot;{key}&quot;,'
             f'&quot;citationItems&quot;:[{{&quot;id&quot;:1}}]}} ')
    return ('<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            f'<w:r><w:instrText xml:space="preserve">{instr}</w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
            f'<w:r><w:t>{display}</w:t></w:r>'
            '<w:r><w:fldChar w:fldCharType="end"/></w:r>')


def ref(display: str) -> str:
    return ('<w:r><w:fldChar w:fldCharType="begin"/></w:r>'
            '<w:r><w:instrText xml:space="preserve"> REF _Ref1001 \\h </w:instrText></w:r>'
            '<w:r><w:fldChar w:fldCharType="separate"/></w:r>'
            f'<w:r><w:t>{display}</w:t></w:r>'
            '<w:r><w:fldChar w:fldCharType="end"/></w:r>')


MATH = ('<m:oMath><m:r><m:t>t</m:t></m:r><m:sSub><m:e><m:r><m:t>on</m:t></m:r></m:e></m:sSub>'
        '<m:r><m:t>=</m:t></m:r><m:r><m:t>t</m:t></m:r><m:r><m:t>0</m:t></m:r>'
        '<m:r><m:t>exp(ΔG*/kT)</m:t></m:r></m:oMath>')

BODY = [
    '<w:p w14:paraId="1A2B3C01"><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>'
    + R.format("Results and discussion") + "</w:p>",

    '<w:p w14:paraId="1A2B3C02">'
    + R.format("In recent years, the nucleation behavior of liquids on solid surfaces has ")
    + '<w:proofErr w:type="spellStart"/>' + R.format("garnered") + '<w:proofErr w:type="spellEnd"/>'
    + R.format(" significant attention. It is worth noting that the wettability of the wall plays a pivotal role in determining both the nucleation onset and the subsequent bubble growth ")
    + zotero("[1,2]", "a1") + R.format(".") + "</w:p>",

    '<w:p w14:paraId="1A2B3C03">'
    + ref("Fig. 1") + R.format(" presents the vapor fraction near the wall for contact angles ")
    + I.format("θ") + R.format(" of 35°, 70° and 110°. Our results clearly demonstrate that the hydrophilic surface significantly accelerates nucleation: the onset time decreases from 350 ps to 125 ps at a wall temperature of 300 K and a heat flux of 2 MW/m")
    + SUP.format("2") + R.format(", which proves that the onset time varies monotonically with the contact angle.")
    + "</w:p>",

    '<w:p w14:paraId="1A2B3C04"><w:pPr><w:jc w:val="center"/></w:pPr>' + MATH + "</w:p>",

    '<w:p w14:paraId="1A2B3C05">'
    + R.format("The trend can be interpreted using classical nucleation theory, where the energy barrier decreases due to the enhanced solid–liquid interaction ")
    + zotero("[3]", "a2") + R.format(". This innovative finding sheds light on the intricate interplay between wettability and phase change ")
    + '<w:bookmarkStart w:id="7" w:name="_Ref2002"/>' + R.format("and paves the way for better cooling surfaces.")
    + '<w:bookmarkEnd w:id="7"/>' + "</w:p>",

    '<w:tbl><w:tblPr><w:tblW w:w="0" w:type="auto"/></w:tblPr><w:tr><w:tc><w:p>'
    + R.format("Contact angle (°)") + '</w:p></w:tc><w:tc><w:p>' + R.format("Onset time (ps)")
    + "</w:p></w:tc></w:tr></w:tbl>",
]


def main() -> None:
    doc = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<w:document {NS}><w:body>'
           + "".join(BODY) + '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr></w:body></w:document>')
    ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
          '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
          '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
          '<Default Extension="xml" ContentType="application/xml"/>'
          '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-'
          'officedocument.wordprocessingml.document.main+xml"/></Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/officeDocument" Target="word/document.xml"/></Relationships>')
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", ct)
        z.writestr("_rels/.rels", rels)
        z.writestr("word/document.xml", doc)
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()

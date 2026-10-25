"""Builds a minimal in-memory xlsx with one «Таблица» sheet, for tests."""
import io
import zipfile
from xml.sax.saxutils import escape

NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


def _color_attr(fill: str) -> str:
    """'FF00FF00' -> rgb="FF00FF00"; 'theme:4' / 'indexed:10' -> theme="4" / indexed="10"."""
    kind, sep, value = fill.partition(":")
    return f'{kind}="{value}"' if sep else f'rgb="{fill}"'


def make_xlsx(rows: dict[int, dict[str, tuple[str, str | None]]]) -> bytes:
    """rows: row number -> column letter -> (text, fill ARGB / 'theme:N' / 'indexed:N' or None)."""
    fills = [None]
    for cols in rows.values():
        for _, fill in cols.values():
            if fill and fill not in fills:
                fills.append(fill)
    fill_xml = ['<fill><patternFill patternType="none"/></fill>',
                '<fill><patternFill patternType="gray125"/></fill>']
    fill_xml += [f'<fill><patternFill patternType="solid"><fgColor {_color_attr(f)}/></patternFill></fill>'
                 for f in fills[1:]]
    # style 0 -> no fill; style i -> fillId i+1 (ids 0/1 are the mandatory none/gray125)
    xfs = ['<xf fillId="0"/>'] + [f'<xf fillId="{i + 1}"/>' for i in range(1, len(fills))]
    styles = (f'<styleSheet xmlns="{NS}"><fills count="{len(fill_xml)}">{"".join(fill_xml)}</fills>'
              f'<cellXfs count="{len(xfs)}">{"".join(xfs)}</cellXfs></styleSheet>')

    row_xml = []
    for r in sorted(rows):
        cells = []
        for col, (text, fill) in sorted(rows[r].items()):
            s = fills.index(fill) if fill else 0
            cells.append(f'<c r="{col}{r}" s="{s}" t="inlineStr"><is><t>{escape(text)}</t></is></c>')
        row_xml.append(f'<row r="{r}">{"".join(cells)}</row>')
    sheet = f'<worksheet xmlns="{NS}"><sheetData>{"".join(row_xml)}</sheetData></worksheet>'

    workbook = (f'<workbook xmlns="{NS}" xmlns:r="{REL_NS}"><sheets>'
                f'<sheet name="Таблица" sheetId="1" r:id="rId1"/></sheets></workbook>')
    rels = ('<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            f'<Relationship Id="rId1" Type="{REL_NS}/worksheet" Target="worksheets/sheet1.xml"/>'
            '</Relationships>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", rels)
        z.writestr("xl/styles.xml", styles)
        z.writestr("xl/worksheets/sheet1.xml", sheet)
    return buf.getvalue()

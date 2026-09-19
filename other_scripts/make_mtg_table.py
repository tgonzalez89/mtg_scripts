from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt

# Data: 3 columns (label, number, note)
rows = [
    ("Basic lands", "100", "20 per type"),
    ("Dual lands", "40", "10 per cycle"),
    ("Other lands", "5", ""),
    ("Colorless/Artifacts", "12", ""),
    ("Multicolor", "20", "2 per color pair"),
    ("Single color", "115", "23 per color"),
    ("Total", "192", "(non-basics)"),
    ("Players", "4", ""),
    ("Packs per player", "4", ""),
    ("Cards per booster", "12", ""),
]

# Create document
doc = Document()

# Make page landscape
section = doc.sections[0]
section.orientation = WD_ORIENT.LANDSCAPE
# Swap width/height to match landscape
section.page_width, section.page_height = section.page_height, section.page_width

# Create table: 10 rows, 3 columns
table = doc.add_table(rows=len(rows), cols=3)
table.alignment = WD_TABLE_ALIGNMENT.CENTER

# Set table outer size: 88 mm wide, 63 mm tall
table_width_mm = 88
table_height_mm = 63

# Column widths (Option A): 40 / 20 / 28 mm
col_widths_mm = [40, 20, 28]

for i, width_mm in enumerate(col_widths_mm):
    for cell in table.columns[i].cells:
        cell.width = Mm(width_mm)

# Let Word distribute row heights automatically, but set preferred height
row_height_mm = table_height_mm / len(rows)
for row in table.rows:
    row.height = Mm(row_height_mm)

# Fill table cells
for (label, number, note), row in zip(rows, table.rows):
    row.cells[0].text = label
    row.cells[1].text = number
    row.cells[2].text = note

# Make borders transparent/white
# (Word doesn't truly support "no color" via python-docx, so we set width to 0)
for row in table.rows:
    for cell in row.cells:
        tc = cell._tc
        tcPr = tc.get_or_add_tcPr()
        for tag in ("top", "bottom", "left", "right"):
            element = tcPr.xpath(f"w:tcBorders/w:{tag}")
            if element:
                border = element[0]
            else:
                from docx.oxml import OxmlElement

                borders = tcPr.xpath("w:tcBorders")
                if not borders:
                    borders = [OxmlElement("w:tcBorders")]
                    tcPr.append(borders[0])
                border = OxmlElement(f"w:{tag}")
                borders[0].append(border)
            border.set(qn("w:val"), "nil")  # hide border
            border.set(qn("w:sz"), "0")  # size 0
            border.set(qn("w:color"), "FFFFFF")  # white (optional)

# Optional: set a readable default font size
style = doc.styles["Normal"]
style.font.size = Pt(10)

# Save document
doc.save("mtg_table_63x88mm.docx")
print("Document saved as mtg_table_63x88mm.docx")

#!/usr/bin/env python3
"""Generate PDF version of the Business Plan with Azirella branding."""

import markdown
from weasyprint import HTML
from pathlib import Path
import base64

REPO_ROOT = Path(__file__).parent.parent
MD_PATH = REPO_ROOT / "docs" / "external" / "BUSINESS_PLAN.md"
LOGO_PATH = REPO_ROOT / "docs" / "Azirella_Logo.jpg"
PDF_PATH = REPO_ROOT / "docs" / "external" / "pdf" / "BUSINESS_PLAN.pdf"


def main():
    # Read markdown
    md_text = MD_PATH.read_text(encoding="utf-8")

    # Remove the markdown image references to the logo (we'll use CSS headers)
    md_text = md_text.replace("![Azirella](../Azirella_Logo.jpg)", "")

    # Embed chart images as base64 in the markdown before conversion
    import re
    chart_pattern = re.compile(r'!\[([^\]]*)\]\((pdf/charts/[^)]+)\)')
    def replace_chart_ref(match):
        alt_text = match.group(1)
        rel_path = match.group(2)
        chart_path = MD_PATH.parent / rel_path
        if chart_path.exists():
            chart_bytes = chart_path.read_bytes()
            chart_b64 = base64.b64encode(chart_bytes).decode("utf-8")
            ext = chart_path.suffix.lstrip(".")
            return f'![{alt_text}](data:image/{ext};base64,{chart_b64})'
        return match.group(0)
    md_text = chart_pattern.sub(replace_chart_ref, md_text)

    # Convert markdown to HTML
    html_body = markdown.markdown(
        md_text,
        extensions=["tables", "toc", "fenced_code"],
    )

    # Encode logo as base64 for embedding
    logo_b64 = ""
    if LOGO_PATH.exists():
        logo_bytes = LOGO_PATH.read_bytes()
        logo_b64 = base64.b64encode(logo_bytes).decode("utf-8")

    logo_img = f'<img src="data:image/jpeg;base64,{logo_b64}" class="logo" />' if logo_b64 else "Azirella"

    # Full HTML with CSS for headers/footers
    full_html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    @page {{
        size: A4;
        margin: 25mm 20mm 25mm 20mm;

        @top-left {{
            content: element(header-logo);
        }}
        @top-right {{
            content: "Page " counter(page) " of " counter(pages);
            font-family: 'Helvetica Neue', Arial, sans-serif;
            font-size: 9pt;
            color: #666;
            padding-top: 5mm;
        }}
        @top-center {{
            content: "";
            border-bottom: 0.5pt solid #ccc;
            width: 100%;
        }}
        @bottom-center {{
            content: "Copyright \\00a9  2026 Azirella Ltd. All rights reserved. STRICTLY CONFIDENTIAL.";
            font-family: 'Helvetica Neue', Arial, sans-serif;
            font-size: 7pt;
            color: #999;
            border-top: 0.5pt solid #ccc;
            padding-top: 3mm;
        }}
    }}

    @page :first {{
        @top-left {{ content: none; }}
        @top-right {{ content: none; }}
        @top-center {{ content: none; border: none; }}
    }}

    #header-logo-container {{
        position: running(header-logo);
    }}

    #header-logo-container .logo {{
        height: 12mm;
    }}

    body {{
        font-family: 'Helvetica Neue', Arial, sans-serif;
        font-size: 10pt;
        line-height: 1.5;
        color: #1a1a1a;
        max-width: 100%;
    }}

    /* Title page styling */
    h1 {{
        font-size: 22pt;
        color: #1a3a5c;
        margin-top: 30mm;
        margin-bottom: 5mm;
        page-break-before: avoid;
    }}

    h2 {{
        font-size: 16pt;
        color: #1a3a5c;
        margin-top: 15mm;
        border-bottom: 1.5pt solid #1a3a5c;
        padding-bottom: 3mm;
        page-break-after: avoid;
    }}

    h3 {{
        font-size: 13pt;
        color: #2a5a8c;
        margin-top: 8mm;
        page-break-after: avoid;
    }}

    h4 {{
        font-size: 11pt;
        color: #3a6a9c;
        margin-top: 5mm;
        page-break-after: avoid;
    }}

    /* Cover page */
    .cover-block {{
        text-align: center;
        margin-top: 40mm;
        margin-bottom: 20mm;
    }}

    .cover-block .logo {{
        height: 30mm;
        margin-bottom: 10mm;
    }}

    /* Tables */
    table {{
        width: 100%;
        border-collapse: collapse;
        margin: 5mm 0;
        font-size: 9pt;
        page-break-inside: auto;
    }}

    thead {{
        display: table-header-group;
    }}

    tr {{
        page-break-inside: avoid;
    }}

    th {{
        background-color: #1a3a5c;
        color: white;
        padding: 3mm 2mm;
        text-align: left;
        font-weight: 600;
        font-size: 8.5pt;
    }}

    td {{
        padding: 2mm;
        border-bottom: 0.5pt solid #ddd;
        vertical-align: top;
    }}

    tr:nth-child(even) td {{
        background-color: #f8f9fa;
    }}

    /* Blockquotes for confidentiality notices */
    blockquote {{
        background-color: #fff3cd;
        border-left: 3pt solid #ffc107;
        padding: 3mm 5mm;
        margin: 5mm 0;
        font-size: 8.5pt;
        color: #664d03;
    }}

    /* Code blocks */
    pre {{
        background-color: #f4f4f4;
        border: 0.5pt solid #ddd;
        border-radius: 2mm;
        padding: 3mm;
        font-size: 8pt;
        font-family: 'Courier New', monospace;
        overflow-wrap: break-word;
        white-space: pre-wrap;
        page-break-inside: avoid;
    }}

    code {{
        font-family: 'Courier New', monospace;
        font-size: 8.5pt;
        background-color: #f4f4f4;
        padding: 0.5mm 1mm;
        border-radius: 1mm;
    }}

    pre code {{
        background: none;
        padding: 0;
    }}

    /* Strong / bold */
    strong {{
        color: #1a3a5c;
    }}

    /* Links */
    a {{
        color: #2a5a8c;
        text-decoration: none;
    }}

    /* Horizontal rule */
    hr {{
        border: none;
        border-top: 1pt solid #1a3a5c;
        margin: 10mm 0;
    }}

    /* Lists */
    ul, ol {{
        margin: 2mm 0;
        padding-left: 6mm;
    }}

    li {{
        margin-bottom: 1mm;
    }}

    /* Page breaks before major sections */
    h2 {{
        page-break-before: always;
    }}

    /* Don't break before first h2 */
    h1 + hr + h2,
    body > h2:first-of-type {{
        page-break-before: avoid;
    }}

    /* Images (charts) */
    img {{
        max-width: 100%;
        height: auto;
        display: block;
        margin: 5mm auto;
        page-break-inside: avoid;
    }}

    /* Paragraph spacing */
    p {{
        margin: 2mm 0;
    }}
</style>
</head>
<body>

<!-- Running header element -->
<div id="header-logo-container">
    {logo_img}
</div>

<!-- Cover page -->
<div class="cover-block">
    {logo_img.replace('class="logo"', 'class="logo" style="height:30mm"')}
    <h1 style="margin-top:15mm; text-align:center; border:none;">Autonomy Platform</h1>
    <h2 style="text-align:center; border:none; page-break-before:avoid; color:#2a5a8c; font-size:18pt; margin-top:5mm;">Business Plan</h2>
    <p style="text-align:center; font-size:12pt; color:#666; margin-top:10mm;">
        Seed Investment Round &mdash; EUR 5M+
    </p>
    <p style="text-align:center; font-size:10pt; color:#999; margin-top:5mm;">
        March 2026 &bull; Version 1.0
    </p>
    <p style="text-align:center; font-size:9pt; color:#999; margin-top:15mm;">
        <strong>STRICTLY CONFIDENTIAL AND PROPRIETARY</strong><br/>
        Copyright &copy; 2026 Azirella Ltd. All rights reserved worldwide.
    </p>
    <p style="text-align:center; font-size:8pt; color:#aaa; margin-top:3mm;">
        Azirella Ltd, 27, 25 Martiou St., #105, 2408 Engomi, Nicosia, Cyprus
    </p>
</div>

<!-- Main content -->
{html_body}

</body>
</html>"""

    # Ensure output directory exists
    PDF_PATH.parent.mkdir(parents=True, exist_ok=True)

    # Generate PDF
    html_doc = HTML(string=full_html, base_url=str(REPO_ROOT))
    html_doc.write_pdf(PDF_PATH)

    print(f"PDF generated: {PDF_PATH}")
    print(f"Size: {PDF_PATH.stat().st_size / 1024:.0f} KB")


if __name__ == "__main__":
    main()

"""Canonical page rendering shared by extraction, verification and assessment.

Stored text contains table placeholders; always restore structured tables before
using it as evidence. Table cells are rendered after header/footer cleanup.
"""
from .text_cleaning import clean_text, remove_repeated_headers_footers

def _placeholder(index):
    """A letters-only line marking where table `index` sits in the page text: header/footer removal masks
    digits, so a numbered marker repeated on many pages could be dropped as a footer."""
    return 'AIOSTABLEMARKER' + ''.join(chr(97 + int(c)) for c in str(index))


#: A header cell longer than this is a paragraph the table detector took as a header (an SSR metric
#: question, say), not a column label: it is printed once in the title line, never before every row.
LABEL_MAX_CHARS = 60


def render_table(table, page_number):
    """A table as text the AI reads row by row, with its header and page, e.g.
    [Table 1 on page 5 -- columns: Year | Students]
    Year: 2023 | Students: 420"""
    header = table.get('header') or []
    lines = [f'[Table {table["index"]} on page {page_number} -- columns: {" | ".join(header) or "(none)"}]']
    for row in table.get('rows') or []:
        if header and len(header) == len(row):
            lines.append(' | '.join(f'{h}: {v}' if h and len(h) <= LABEL_MAX_CHARS else v for h, v in zip(header, row)))
        else:
            lines.append(' | '.join(row))
    return '\n'.join(lines)


def _with_tables(text, tables, page_number):
    for table in tables or []:
        marker = _placeholder(table['index'])
        rendered = render_table(table, page_number)
        text = text.replace(marker, rendered) if marker in text else f'{text}\n{rendered}'.strip()
    return text


def evidence_pages(pages):
    """Input/output page dicts; preserve page numbers, status and other metadata."""
    cleaned = remove_repeated_headers_footers([clean_text(p.get('text') or '') for p in pages])
    return [{**p, 'text': _with_tables(clean_text(text), p.get('tables'), p['page_number'])}
            for p, text in zip(pages, cleaned)]

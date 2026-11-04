"""Reusable, token-bounded source spans. Embedding text is never citation text."""
import hashlib
import json
import re
from dataclasses import dataclass


@dataclass
class Passage:
    source: dict
    start: int
    end: int
    kind: str
    heading: tuple | None
    embedding_text: str
    tokens: int
    split_unit: bool = False
    heading_clipped: bool = False
    parent_heading: tuple | None = None

    @property
    def key(self):
        return self.source['id'], self.start, self.end

    @property
    def text(self):
        return self.source['text'][self.start:self.end]

    @property
    def spans(self):
        return [(self.start, self.end)] + self.context_spans

    @property
    def context_spans(self):
        return ([self.parent_heading] if self.parent_heading else []) + ([self.heading] if self.heading else [])


def corpus_key(sources):
    digest = hashlib.sha256()
    for source in sorted(sources, key=lambda s: s['id']):
        digest.update(json.dumps(source, sort_keys=True, ensure_ascii=False).encode())
    return digest.hexdigest()


def section_heading(text):
    text = text.strip()
    return bool(text and len(text) <= 160 and '|' not in text and (
        text.startswith('#') or text.isupper() or text.endswith(':') or
        re.match(r'^\d+(?:\.\d+)+\s+\D', text) or
        re.match(r'^(?:(?:academic|financial|reporting)\s+(?:year|period)|(?:department|programme|program|school)\s+(?:of|:))', text, re.I)))


def segments(source):
    """Page-local sections/tables, with original offsets. No invented cross-page headings."""
    text = source['text']
    heading, section, table, start, kind, offset = None, None, False, 0, 'prose', 0
    for line in text.splitlines(keepends=True):
        is_table = line.lstrip().startswith('[Table ') and ' -- columns:' in line
        is_heading = not is_table and section_heading(line)
        if is_table or is_heading:
            if start < offset:
                yield start, offset, kind, heading, section if section != heading else None
            heading = (offset, offset + len(line.rstrip()))
            if is_heading:
                section = heading
            table, kind, start = is_table, 'table' if is_table else 'prose', offset
        elif table and not line.strip():
            if start < offset:
                yield start, offset, kind, heading, section if section != heading else None
            table, kind, start, heading = False, 'prose', offset, section
        offset += len(line)
    if start < len(text):
        yield start, len(text), kind, heading, section if section != heading else None


def construct_passages(sources, ranker):
    """Bound the COMPLETE encoder string, including heading, by actual tokenizer tokens."""
    passages = []
    target = min(240, ranker.token_limit - 32)
    if target < 32:
        raise ValueError('Embedding model token allowance is too small for evidence passages.')
    for source in sorted(sources, key=lambda s: s['id']):
        text = source['text']
        for low, high, kind, heading, parent in segments(source):
            original_heading, original_parent = heading, parent
            if heading:
                offsets = ranker.token_offsets(text[heading[0]:heading[1]])
                heading_limit = min(96, max(1, ranker.token_limit - 64))
                if len(offsets) > heading_limit:
                    heading = (heading[0], heading[0] + offsets[heading_limit - 1][1])
            prefix = text[heading[0]:heading[1]] if heading else ''
            if parent:
                parent_tokens = ranker.token_offsets(text[parent[0]:parent[1]])
                limit = min(48, max(0, ranker.token_limit - 64 - len(ranker.token_offsets(prefix))))
                if not limit:
                    parent = None
                elif len(parent_tokens) > limit:
                    parent = (parent[0], parent[0] + parent_tokens[limit - 1][1])
            parent_prefix = text[parent[0]:parent[1]] if parent else ''
            heading_prefix = prefix
            prefix = '\n'.join(p for p in (parent_prefix, heading_prefix) if p)
            def embedding_text(body):
                parts = [parent_prefix] if parent_prefix else []
                if heading_prefix and not body.startswith(heading_prefix):
                    parts.append(heading_prefix)
                return '\n'.join(parts + [body])
            # Reserve separator/special-token margin; verify actual complete input below.
            allowance = min(target, ranker.token_limit - 32 - len(ranker.token_offsets(prefix)))
            offsets = ranker.token_offsets(text[low:high])
            cursor = 0
            while cursor < len(offsets):
                stop = min(len(offsets), cursor + allowance)
                begin, end = low + offsets[cursor][0], low + offsets[stop - 1][1]
                # Prefer a whole sentence/row boundary in the second half of this window.
                boundaries = list(re.finditer(r'\n|(?<=[.!?])\s+(?=[A-Z])', text[begin:end]))
                boundary = next((begin + m.end() for m in reversed(boundaries)
                                 if m.end() >= (end - begin) // 2), None)
                start_split = cursor > 0 and text[begin - 1:begin] != '\n'
                split_unit = start_split or stop < len(offsets)
                if boundary is not None and stop < len(offsets):
                    end = boundary
                    while stop > cursor + 1 and low + offsets[stop - 1][0] >= end:
                        stop -= 1
                    split_unit = start_split
                body = text[begin:end]
                embedded = embedding_text(body)
                while len(ranker.token_offsets(embedded)) > ranker.token_limit - 8 and stop > cursor + 1:
                    stop -= 1
                    end = low + offsets[stop - 1][1]
                    body = text[begin:end]
                    embedded = embedding_text(body)
                count = len(ranker.token_offsets(embedded))
                if count > ranker.token_limit - 8:
                    raise ValueError('Cannot construct a token-safe evidence passage.')
                passages.append(Passage(source, begin, end, kind, heading, embedded, count, split_unit, heading != original_heading or parent != original_parent, parent))
                if stop == len(offsets):
                    break
                cursor = max(cursor + 1, stop - min(32, (stop - cursor) // 4))
    return passages

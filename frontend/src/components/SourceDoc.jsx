import React, { useMemo } from 'react';
import { normalize } from '../lib/text';

/**
 * Normalise like core/normalize.py (NFKC, collapse whitespace, trim) while remembering,
 * for every character of the normalised string, where it came from in the display text.
 * The display text keeps its line breaks, so paragraphs stay readable.
 */
function indexed(text) {
  const display = (text || '').normalize('NFKC').replace(/\r\n?/g, '\n');
  let norm = '';
  const map = [];
  let pendingSpace = false;
  for (let i = 0; i < display.length; i += 1) {
    const ch = display[i];
    if (/\s/.test(ch)) {
      pendingSpace = norm.length > 0;
      continue;
    }
    if (pendingSpace) {
      norm += ' ';
      map.push(i - 1);
      pendingSpace = false;
    }
    norm += ch;
    map.push(i);
  }
  return { display, norm, map };
}

/**
 * Render a text with highlighted spans.
 * spans: [{ id, start, end, text, tone }] where start/end index the normalised text.
 * If an offset does not line up, the span text is searched instead; unmatched spans are skipped.
 */
export default function SourceDoc({ text, spans, activeId, onHover, onSelect, toneClass }) {
  const { display, norm, map } = useMemo(() => indexed(text), [text]);

  const segments = useMemo(() => {
    const placed = [];
    for (const s of spans) {
      let { start, end } = s;
      const want = normalize(s.text);
      if (!(start >= 0 && norm.slice(start, end) === want)) {
        const i = norm.indexOf(want);
        if (i < 0 || !want) continue;
        start = i;
        end = i + want.length;
      }
      // Normalised offsets -> display offsets (end is exclusive).
      const ds = map[start];
      const de = map[end - 1] + 1;
      if (placed.some((p) => ds < p.end && de > p.start)) continue; // no overlaps
      placed.push({ ...s, start: ds, end: de });
    }
    placed.sort((a, b) => a.start - b.start);
    const out = [];
    let cur = 0;
    for (const p of placed) {
      if (p.start > cur) out.push({ text: display.slice(cur, p.start) });
      out.push({ text: display.slice(p.start, p.end), span: p });
      cur = p.end;
    }
    if (cur < display.length) out.push({ text: display.slice(cur) });
    return out;
  }, [display, norm, map, spans]);

  return (
    <p className="whitespace-pre-wrap font-serif text-[15.5px] leading-[1.9] text-ink-300">
      {segments.map((seg, i) =>
        seg.span ? (
          <mark
            key={i}
            data-active={activeId === seg.span.id}
            className={toneClass ? toneClass(seg.span) : 'mark-evidence'}
            onMouseEnter={() => onHover?.(seg.span.id)}
            onMouseLeave={() => onHover?.(null)}
            onClick={() => onSelect?.(seg.span.id)}
            title={seg.span.label || seg.span.id}
          >
            {seg.text}
          </mark>
        ) : (
          <span key={i}>{seg.text}</span>
        ),
      )}
    </p>
  );
}

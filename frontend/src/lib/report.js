import { jsPDF } from 'jspdf';
import { SECTION_COPY, modelName } from './steps';

// A4 portrait in points.
const PAGE = { w: 595.28, h: 841.89, margin: 48 };
const BRAND = [36, 54, 94];
const MUTED = [95, 103, 117];
const TEXT = [30, 34, 42];
const GREEN = [4, 120, 87];
const RED = [190, 18, 60];
const AMBER = [180, 83, 9];

/** jsPDF's built-in fonts cover Windows-1252 only; replace anything else. */
function clean(s) {
  return String(s ?? '')
    .replace(/→/g, '->')
    .replace(/₹/g, 'Rs.')
    .replace(/[\u2002-\u200B\u202F\u00A0]/g, ' ')
    .replace(/[^\t\n\r\u0020-\u007E\u00A1-\u00FF\u2013\u2014\u2018\u2019\u201C\u201D\u2022\u2026\u20AC]/g, '?');
}

function writer(title, subtitle) {
  const doc = new jsPDF({ unit: 'pt', format: 'a4' });
  const width = PAGE.w - PAGE.margin * 2;
  let y = 0;

  const header = () => {
    doc.setFillColor(...BRAND);
    doc.rect(0, 0, PAGE.w, 64, 'F');
    doc.setTextColor(255, 255, 255);
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(15);
    doc.text('CourtroomAI', PAGE.margin, 30);
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(10);
    doc.text(clean(title), PAGE.margin, 47);
    doc.text(clean(subtitle), PAGE.w - PAGE.margin, 47, { align: 'right' });
    y = 92;
  };

  const ensure = (needed) => {
    if (y + needed > PAGE.h - 60) {
      doc.addPage();
      header();
    }
  };

  const para = (text, { size = 10.5, color = TEXT, font = 'helvetica', style = 'normal', indent = 0, gap = 6, lineHeight = 1.45 } = {}) => {
    doc.setFont(font, style);
    doc.setFontSize(size);
    doc.setTextColor(...color);
    const lines = doc.splitTextToSize(clean(text), width - indent);
    const lh = size * lineHeight;
    for (const line of lines) {
      ensure(lh);
      doc.text(line, PAGE.margin + indent, y);
      y += lh;
    }
    y += gap;
  };

  const heading = (text, note) => {
    ensure(44);
    y += 6;
    doc.setDrawColor(227, 230, 235);
    doc.setLineWidth(0.8);
    doc.line(PAGE.margin, y - 12, PAGE.w - PAGE.margin, y - 12);
    para(text, { size: 14, style: 'bold', color: TEXT, gap: 2 });
    if (note) para(note, { size: 9, color: MUTED, gap: 8 });
  };

  const label = (text, color) => {
    ensure(16);
    doc.setFont('helvetica', 'bold');
    doc.setFontSize(8.5);
    doc.setTextColor(...color);
    doc.text(clean(text).toUpperCase(), PAGE.margin, y);
    y += 13;
  };

  const link = (text, url) => {
    ensure(14);
    doc.setFont('helvetica', 'normal');
    doc.setFontSize(9);
    doc.setTextColor(...BRAND);
    const t = clean(text).slice(0, 110);
    doc.textWithLink(t, PAGE.margin + 12, y, { url });
    y += 13;
  };

  const footer = () => {
    const n = doc.getNumberOfPages();
    for (let i = 1; i <= n; i += 1) {
      doc.setPage(i);
      doc.setFont('helvetica', 'normal');
      doc.setFontSize(8);
      doc.setTextColor(...MUTED);
      doc.text('Research aid only, not legal advice. Read every source before relying on it.', PAGE.margin, PAGE.h - 28);
      doc.text(`Page ${i} of ${n}`, PAGE.w - PAGE.margin, PAGE.h - 28, { align: 'right' });
    }
  };

  header();
  return { doc, para, heading, label, link, footer, space: (h) => { y += h; } };
}

function stamp() {
  const d = new Date();
  return {
    human: d.toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' }),
    file: d.toISOString().slice(0, 16).replace(/[:T]/g, '-'),
  };
}

function modelsUsed(events) {
  const seen = new Set((events || []).map((e) => e.model).filter((m) => m && m.includes('/')));
  return [...seen].map(modelName).join(', ');
}

export function buildBriefReport({ brief, claims, firText, perspective, events }) {
  const t = stamp();
  const w = writer('Case brief report', `Generated ${t.human}`);
  const byId = Object.fromEntries((claims || []).map((c) => [c.id, c]));
  const shown = brief.sections.reduce((n, s) => n + s.items.length, 0);

  w.para(`Prepared for the ${perspective === 'prosecution' ? 'prosecution' : 'defence'}.`, { size: 11, color: MUTED, gap: 2 });
  w.para(`${shown} points in the brief · ${brief.flagged.length} left out after checks · ${brief.lint_drops.length} sentences removed in the final check`, { size: 11, color: MUTED });
  w.para('Every point below passed a check against its source: facts are quoted word for word from the FIR, and each judgment was found in our library, its quote matched word for word, and an independent AI reviewer confirmed it supports the point. Suggestions are ideas to weigh, not findings.', { size: 9.5, color: MUTED, gap: 10 });

  if (brief.abstained) {
    w.heading('Not enough judgments found');
    w.para('Our library has no judgments close enough to this FIR, so no judgments or suggestions were added. The facts from the FIR are still listed.');
  }

  for (const sec of brief.sections) {
    const copy = SECTION_COPY[sec.type] || { title: sec.title };
    w.heading(copy.title, sec.type === 'fact' ? 'Quoted word for word from the FIR.' : copy.note);
    for (const it of sec.items) {
      const c = byId[it.claim_id] || {};
      const passage = (c.evidence || []).find((e) => e.kind === 'judgment_passage');
      if (sec.type === 'precedent_holding' && passage) {
        w.label('Verified against source text', GREEN);
        w.para(passage.title || passage.case_id, { size: 11.5, style: 'bold', gap: 1 });
        w.para([passage.court, passage.date].filter(Boolean).join(' · '), { size: 9, color: MUTED, gap: 4 });
        const point = it.text.includes(': ') ? it.text.slice(it.text.indexOf(': ') + 2).split(' The judgment says:')[0] : it.text;
        w.para(point, { gap: 4 });
        w.para(`“${passage.quote}”`, { font: 'times', style: 'italic', size: 11, indent: 12, gap: 4 });
        if (passage.source_url) w.link(`Full judgment: ${passage.source_url}`, passage.source_url);
        w.space(6);
      } else if (sec.type === 'good_law_status') {
        w.para(it.text, { gap: 3 });
        for (const e of (c.evidence || []).filter((x) => x.kind === 'web_result')) w.link(e.title || e.url, e.url);
        w.space(6);
      } else if (sec.type === 'fact') {
        w.para(it.text.replace(/^The FIR states: /, ''), { font: 'times', size: 11.5, gap: 8 });
      } else {
        if (sec.type === 'strategy_suggestion' && c.refs?.length) w.label(`Suggestion · based on points ${c.refs.join(', ')}`, BRAND);
        w.para(sec.type === 'strategy_suggestion' ? it.text.replace(/^Suggestion: /, '') : it.text, { gap: 8 });
      }
    }
  }

  if (brief.flagged.length || brief.lint_drops.length) {
    w.heading('Left out of the brief, and why', 'These did not pass a check, so none of them appear above.');
    for (const f of brief.flagged) {
      w.label(f.status === 'weak' ? 'Only partly supported' : f.status === 'failed' ? 'Did not pass checks' : 'Could not be checked', f.status === 'weak' ? AMBER : f.status === 'failed' ? RED : MUTED);
      w.para(f.text, { gap: 2 });
      w.para(`Reason: ${f.reason}`, { size: 9, color: MUTED, gap: 8 });
    }
    for (const d of brief.lint_drops) {
      w.para(`Removed sentence: “${d.sentence}”`, { gap: 2 });
      w.para(`Reason: it mentions ${d.unknown.join(', ')}, which is not in any checked source.`, { size: 9, color: MUTED, gap: 8 });
    }
  }

  w.heading('Appendix: the FIR as submitted');
  w.para(firText, { font: 'times', size: 10.5, gap: 10 });
  const models = modelsUsed(events);
  w.heading('How this report was produced');
  w.para(`Models: ${models || 'NVIDIA Nemotron'} on Nebius Token Factory. Later-case search: Tavily. Judgments: Indian Kanoon.`, { size: 9.5, color: MUTED });

  w.footer();
  return { doc: w.doc, filename: `CourtroomAI-brief-${t.file}.pdf` };
}

export function downloadBriefReport(args) {
  const { doc, filename } = buildBriefReport(args);
  doc.save(filename);
}

const AUDIT_LABEL = {
  verified: ['Verified against source text', GREEN],
  weak: ['Only partly supported', AMBER],
  found_online_unverified: ['Found online only, judgment text not checked', AMBER],
  contradicted: ['The judgment says the opposite', RED],
  not_supported: ['The judgment does not support this point', RED],
  not_found: ['Not found, possibly fabricated', RED],
  unverified: ['Could not be checked', MUTED],
};

export function buildAuditReport({ verdicts, draft, events }) {
  const t = stamp();
  const w = writer('Citation check report', `Generated ${t.human}`);
  const count = (keys) => verdicts.filter((v) => keys.includes(v.verdict)).length;
  w.para(`${verdicts.length} citations checked · ${count(['verified'])} verified · ${count(['not_found', 'not_supported', 'contradicted'])} with problems · ${count(['weak', 'found_online_unverified', 'unverified'])} need a closer look`, { size: 11, color: MUTED, gap: 10 });

  w.heading('Citations', 'Each citation found in the draft, the point it was used for, and what we found.');
  for (const v of verdicts) {
    const [text, color] = AUDIT_LABEL[v.verdict] || AUDIT_LABEL.unverified;
    w.label(text, color);
    w.para(`${v.case_name || '(no case name)'}${v.citation ? `, ${v.citation}` : ''}`, { size: 11.5, style: 'bold', gap: 2 });
    w.para(`Used for: ${v.proposition}`, { gap: 2 });
    w.para(`Why: ${v.reason}`, { size: 9.5, color: MUTED, gap: 4 });
    if (v.fetched_from) w.para(`This judgment is not in our library; its full text was read from ${v.fetched_from} and checked the same way.`, { size: 9, color: MUTED, gap: 4 });
    const ev = v.claim?.evidence || [];
    const passage = ev.find((e) => e.kind === 'judgment_passage');
    if (passage?.quote) w.para(`“${passage.quote}”`, { font: 'times', style: 'italic', size: 11, indent: 12, gap: 4 });
    if (passage?.source_url) w.link(`Full judgment: ${passage.source_url}`, passage.source_url);
    for (const e of ev.filter((x) => x.kind === 'web_result')) w.link(e.title || e.url, e.url);
    w.space(8);
  }

  w.heading('Appendix: the draft as submitted');
  w.para(draft, { font: 'times', size: 10.5, gap: 10 });
  w.heading('How this report was produced');
  w.para(`Models: ${modelsUsed(events) || 'NVIDIA Nemotron'} on Nebius Token Factory. Web search: Tavily. Judgments: Indian Kanoon.`, { size: 9.5, color: MUTED });
  w.footer();
  return { doc: w.doc, filename: `CourtroomAI-citation-check-${t.file}.pdf` };
}

export function downloadAuditReport(args) {
  const { doc, filename } = buildAuditReport(args);
  doc.save(filename);
}

import React, { useEffect, useMemo, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { ArrowRight, Check, ChevronDown, Copy, Download, FileSearch, FileText, Landmark, Lightbulb, RotateCcw, Scale } from 'lucide-react';
import { getSamples, runBrief } from '../api/client';
import ClaimCard from '../components/ClaimCard';
import PipelineRail from '../components/PipelineRail';
import SourceDoc from '../components/SourceDoc';
import { ErrorNote, Label, Shell, StatusBadge } from '../components/ui';
import { friendlyError } from '../lib/errors';
import { downloadBriefReport } from '../lib/report';
import { BRIEF_STEPS, SECTION_COPY } from '../lib/steps';

const SAMPLE_LABELS = { fir_snatching: 'Phone snatching', fir_dowry: 'Dowry harassment', fir_cheating: 'Cheating and forgery' };
const SECTION_ICON = { fact: FileText, statute_mapping: Landmark, precedent_holding: Scale, good_law_status: FileSearch, strategy_suggestion: Lightbulb };

export default function Brief() {
  const [firText, setFirText] = useState('');
  const [perspective, setPerspective] = useState('defense');
  const [samples, setSamples] = useState({});
  const [events, setEvents] = useState([]);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [tab, setTab] = useState('edit');
  const [active, setActive] = useState(null);
  const [refActive, setRefActive] = useState(null);
  const [submitted, setSubmitted] = useState('');
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    getSamples().then(setSamples).catch(() => setSamples({}));
  }, []);

  const claimsById = useMemo(() => Object.fromEntries((result?.claims || []).map((c) => [c.id, c])), [result]);
  const brief = result?.brief;

  const factSpans = useMemo(
    () => (result?.claims || [])
      .filter((c) => c.type === 'fact' && c.status === 'passed')
      .map((c) => ({ id: c.id, start: c.evidence[0]?.start, end: c.evidence[0]?.end, text: c.evidence[0]?.text || c.text, label: `Point ${c.id}` })),
    [result],
  );

  const counts = useMemo(() => brief && ({
    shown: brief.sections.reduce((n, s) => n + s.items.length, 0),
    flagged: brief.flagged.length,
    dropped: brief.lint_drops.length,
  }), [brief]);

  const submit = async (e) => {
    e?.preventDefault();
    setRunning(true);
    setEvents([]);
    setResult(null);
    setError(null);
    setSubmitted(firText);
    try {
      const r = await runBrief({ firText, perspective }, (s) => setEvents((prev) => [...prev, s]));
      setResult(r);
      if (r.error) setError(friendlyError(r.error));
      else setTab('source');
    } catch (err) {
      setError(friendlyError(err.message));
    } finally {
      setRunning(false);
    }
  };

  const reset = () => {
    setResult(null);
    setEvents([]);
    setError(null);
    setTab('edit');
  };

  const copyBrief = () => {
    if (!brief) return;
    const text = brief.sections
      .map((s) => `${(SECTION_COPY[s.type] || s).title}\n${s.items.map((i) => `- ${i.text}`).join('\n')}`)
      .join('\n\n');
    navigator.clipboard?.writeText(`${text}\n\nResearch aid only, not legal advice. Read every source before relying on it.`);
    setCopied(true);
    setTimeout(() => setCopied(false), 1800);
  };

  return (
    <Shell>
      <div className="flex flex-wrap items-end justify-between gap-4 pt-10 pb-8">
        <div>
          <Label>Case brief</Label>
          <h1 className="mt-2 text-3xl font-semibold sm:text-[34px]">Turn an FIR into a brief you can rely on</h1>
          <p className="mt-2 max-w-2xl text-[15px] text-ink-400">
            Paste the FIR and choose who you are acting for. Every point in the brief is checked against its source first, and anything that does not pass is listed separately with the reason.
          </p>
        </div>
        {brief && (
          <div className="flex flex-wrap gap-2">
            <button type="button" onClick={copyBrief} className="btn-ghost">
              {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}{copied ? 'Copied' : 'Copy text'}
            </button>
            <button type="button" className="btn-primary"
              onClick={() => downloadBriefReport({ brief, claims: result.claims, firText: submitted, perspective, events })}>
              <Download className="h-4 w-4" />Download PDF report
            </button>
          </div>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,0.92fr)_minmax(0,1.08fr)]">
        <div className="space-y-6 lg:sticky lg:top-20 lg:self-start">
          <section className="panel overflow-hidden">
            <div className="flex items-center justify-between border-b border-ink-700 px-5 py-3">
              <div className="flex gap-1 rounded-lg bg-ink-800 p-1" role="tablist">
                {[['edit', 'FIR'], ['source', 'Highlighted facts']].map(([k, text]) => (
                  <button key={k} type="button" role="tab" aria-selected={tab === k} disabled={k === 'source' && !result?.claims}
                    onClick={() => setTab(k)}
                    className={`rounded-md px-3 py-1 text-sm font-medium transition disabled:opacity-40 ${tab === k ? 'bg-ink-900 text-ink-100 shadow-sm' : 'text-ink-400 hover:text-ink-100'}`}>
                    {text}
                  </button>
                ))}
              </div>
              {brief && <button type="button" onClick={reset} className="inline-flex items-center gap-1 text-sm text-ink-400 hover:text-brand-600"><RotateCcw className="h-3.5 w-3.5" />New brief</button>}
            </div>

            {tab === 'edit' ? (
              <form onSubmit={submit} className="space-y-5 p-5">
                <div>
                  <label htmlFor="fir" className="mb-2 block text-sm font-medium text-ink-200">FIR or legal notice</label>
                  <textarea id="fir" value={firText} onChange={(e) => setFirText(e.target.value)} rows={11}
                    placeholder="Paste the full text of the FIR here…" className="field" />
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <span className="text-xs text-ink-500">No FIR to hand? Try a made-up example:</span>
                    {Object.keys(samples).map((k) => (
                      <button key={k} type="button" onClick={() => setFirText(samples[k])}
                        className={`chip transition ${firText === samples[k] ? 'border-brand-500 bg-brand-100 text-brand-600' : 'border-ink-700 bg-ink-900 text-ink-300 hover:border-brand-500 hover:text-brand-600'}`}>
                        {SAMPLE_LABELS[k] || k}
                      </button>
                    ))}
                  </div>
                </div>
                <div>
                  <span className="mb-2 block text-sm font-medium text-ink-200">I am acting for the</span>
                  <div className="inline-flex rounded-lg border border-ink-700 bg-ink-800 p-1">
                    {[['defense', 'Defence'], ['prosecution', 'Prosecution']].map(([p, text]) => (
                      <button key={p} type="button" onClick={() => setPerspective(p)} aria-pressed={perspective === p}
                        className={`rounded-md px-4 py-1.5 text-sm font-medium transition ${perspective === p ? 'bg-ink-900 text-ink-100 shadow-sm' : 'text-ink-400 hover:text-ink-100'}`}>
                        {text}
                      </button>
                    ))}
                  </div>
                </div>
                <div className="flex flex-wrap items-center justify-between gap-3 border-t border-ink-800 pt-4">
                  <p className="text-xs text-ink-500">Usually takes about a minute.</p>
                  <button type="submit" disabled={running || firText.trim().length < 40} className="btn-primary">
                    {running ? 'Preparing your brief…' : 'Prepare brief'} <ArrowRight className="h-4 w-4" />
                  </button>
                </div>
              </form>
            ) : (
              <div className="max-h-[56vh] overflow-y-auto p-5">
                <p className="mb-3 text-xs text-ink-500">Facts used in the brief are highlighted. Click one to jump to it.</p>
                <SourceDoc text={submitted} spans={factSpans} activeId={active} onHover={setActive}
                  onSelect={(id) => document.getElementById(`claim-${id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })} />
              </div>
            )}
          </section>

          {!running && events.length > 0 && <PipelineRail steps={BRIEF_STEPS} events={events} running={false} title="How this brief was prepared" />}
        </div>

        <div className="min-w-0 space-y-6">
          {error && <ErrorNote>{error}</ErrorNote>}
          {!brief && !running && !error && <EmptyState />}
          {!brief && running && <PipelineRail steps={BRIEF_STEPS} events={events} running title="Preparing your brief" />}

          {brief && (
            <>
              <motion.div initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }} className="panel grid grid-cols-3 divide-x divide-ink-700">
                <Stat n={counts.shown} label="points in your brief" cls="text-verdict-pass" />
                <Stat n={counts.flagged} label="left out after checks" cls="text-verdict-weak" />
                <Stat n={counts.dropped} label="sentences removed in final check" cls="text-ink-300" />
              </motion.div>

              {brief.abstained && (
                <div className="panel border-amber-200 bg-amber-50 p-5">
                  <p className="font-semibold text-ink-100">We could not find close enough judgments</p>
                  <p className="mt-1 text-sm text-ink-300">Our judgment library has nothing close enough to this FIR, so we have not suggested any judgments or arguments. The facts from your FIR are still listed below.</p>
                </div>
              )}

              {brief.sections.map((sec) => {
                const Icon = SECTION_ICON[sec.type] || FileText;
                const copy = SECTION_COPY[sec.type] || { title: sec.title };
                return (
                  <section key={sec.title}>
                    <div className="mb-1 flex items-center gap-2">
                      <span className="grid h-7 w-7 place-items-center rounded-md bg-brand-100"><Icon className="h-4 w-4 text-brand-600" /></span>
                      <h2 className="text-lg font-semibold">{copy.title}</h2>
                      <span className="rounded-full bg-ink-800 px-2 text-xs font-medium text-ink-400">{sec.items.length}</span>
                    </div>
                    {copy.note && <p className="mb-3 ml-9 text-sm text-ink-400">{copy.note}</p>}
                    <div className="space-y-3">
                      {sec.items.map((it, i) => (
                        <ClaimCard key={it.claim_id} id={it.claim_id} text={it.text} claim={claimsById[it.claim_id]} type={sec.type}
                          index={i} active={active === it.claim_id} refsActive={refActive === it.claim_id}
                          onHover={setActive} onRefHover={setRefActive} />
                      ))}
                    </div>
                  </section>
                );
              })}

              <LeftOut brief={brief} claimsById={claimsById} />
            </>
          )}
        </div>
      </div>
    </Shell>
  );
}

function Stat({ n, label, cls }) {
  return (
    <div className="p-4 text-center sm:p-5">
      <div className={`text-3xl font-semibold tabular-nums ${cls}`}>{n}</div>
      <div className="mt-0.5 text-xs text-ink-400">{label}</div>
    </div>
  );
}

function LeftOut({ brief, claimsById }) {
  const [open, setOpen] = useState(false);
  const n = brief.flagged.length + brief.lint_drops.length;
  if (!n) return null;
  return (
    <section className="panel">
      <button type="button" onClick={() => setOpen(!open)} aria-expanded={open} className="flex w-full items-center justify-between gap-4 p-5 text-left">
        <div>
          <h2 className="text-lg font-semibold">Left out of the brief, and why ({n})</h2>
          <p className="text-sm text-ink-400">These did not pass a check, so none of them appear above. Shown here so nothing is hidden from you.</p>
        </div>
        <ChevronDown className={`h-5 w-5 shrink-0 text-ink-400 transition ${open ? 'rotate-180' : ''}`} />
      </button>
      <AnimatePresence initial={false}>
        {open && (
          <motion.ul initial={{ height: 0, opacity: 0 }} animate={{ height: 'auto', opacity: 1 }} exit={{ height: 0, opacity: 0 }}
            className="divide-y divide-ink-700 overflow-hidden border-t border-ink-700">
            {brief.flagged.map((f) => {
              const passage = claimsById[f.claim_id]?.evidence?.find((e) => e.kind === 'judgment_passage');
              return (
                <li key={f.claim_id} className="px-5 py-4">
                  <div className="mb-1 flex flex-wrap items-center gap-2">
                    <StatusBadge type={f.type} status={f.status} />
                    {passage?.title && <span className="text-xs text-ink-500">{passage.title}</span>}
                  </div>
                  <p className="text-sm text-ink-200">{f.text}</p>
                  <p className="mt-1 text-xs text-ink-500">Reason: {f.reason}</p>
                </li>
              );
            })}
            {brief.lint_drops.map((d, i) => (
              <li key={`lint-${i}`} className="px-5 py-4">
                <p className="text-sm text-ink-200">Removed sentence: “{d.sentence}”</p>
                <p className="mt-1 text-xs text-ink-500">Reason: it mentions {d.unknown.join(', ')}, which is not in any checked source.</p>
              </li>
            ))}
          </motion.ul>
        )}
      </AnimatePresence>
    </section>
  );
}

function EmptyState() {
  const checks = [
    ['Facts', 'are quoted word for word from your FIR.'],
    ['Sections', 'are matched to the new codes from the official table, using the date of the offence.'],
    ['Judgments', 'must exist in our library, the quote must match the judgment word for word, and an independent AI reviewer must confirm it supports the point.'],
    ['Every sentence', 'gets a final check: no case name, citation or figure can appear unless it comes from a checked source.'],
  ];
  return (
    <div className="panel p-6 sm:p-8">
      <h2 className="text-lg font-semibold">What you will get</h2>
      <p className="mt-1 text-sm text-ink-400">A brief made only of points that passed these checks, plus a downloadable PDF report.</p>
      <ul className="mt-5 space-y-4">
        {checks.map(([k, v]) => (
          <li key={k} className="flex gap-3">
            <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-full bg-emerald-50 ring-1 ring-emerald-200"><Check className="h-3 w-3 text-verdict-pass" /></span>
            <p className="text-[15px] text-ink-300"><span className="font-semibold text-ink-100">{k}</span> {v}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

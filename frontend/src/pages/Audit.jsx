import React, { useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { ArrowRight, Download, ExternalLink, Globe, RotateCcw } from 'lucide-react';
import { runAudit } from '../api/client';
import PipelineRail from '../components/PipelineRail';
import SourceDoc from '../components/SourceDoc';
import { ErrorNote, Label, ModelChip, Shell, Stamp } from '../components/ui';
import { friendlyError } from '../lib/errors';
import { downloadAuditReport } from '../lib/report';
import { AUDIT_STEPS } from '../lib/steps';
import { normalize } from '../lib/text';

// Demo draft. Citation 1 is a real judgment in our library cited for what it says;
// citation 2 cites the same judgment for a point it does not make; citation 3 is a
// real judgment NOT in our library (read from the web); citation 4 is DELIBERATELY
// FABRICATED (a future year) to show how fake citations are caught.
const SAMPLE_DRAFT = `The defence relies on the following authorities.

1. In Swaroop Singh v. State of M.P., 2013 (15) SCC 240, the Supreme Court reiterated that corroboration of the prosecutrix's testimony is not a requirement of law and her evidence, if it inspires confidence, can sustain a conviction.

2. Swaroop Singh v. State of M.P., 2013 (15) SCC 240 also holds that anticipatory bail must be granted to every first-time offender.

3. In Arnesh Kumar v. State of Bihar, (2014) 8 SCC 273, the Supreme Court directed that police officers should not arrest an accused automatically and must satisfy themselves about the necessity of arrest under Section 41 CrPC.

4. In Imaginary Kumar v. State of Nowhere, (2031) 4 SCC 777, the Supreme Court held that bail is automatic for all offences punishable with less than ten years.`;

const VERDICT = {
  verified: { tone: 'pass', label: 'Verified against source text' },
  weak: { tone: 'weak', label: 'Only partly supported' },
  found_online_unverified: { tone: 'weak', label: 'Found online only' },
  contradicted: { tone: 'fail', label: 'Judgment says the opposite' },
  not_supported: { tone: 'fail', label: 'Judgment does not support this' },
  not_found: { tone: 'fail', label: 'Not found, possibly fabricated' },
  unverified: { tone: 'unknown', label: 'Could not be checked' },
};

const MARK = {
  pass: 'cursor-pointer rounded-[3px] bg-emerald-100 px-0.5 text-ink-100 data-[active=true]:ring-2 data-[active=true]:ring-emerald-400',
  weak: 'cursor-pointer rounded-[3px] bg-amber-100 px-0.5 text-ink-100 data-[active=true]:ring-2 data-[active=true]:ring-amber-400',
  fail: 'cursor-pointer rounded-[3px] bg-rose-100 px-0.5 text-ink-100 underline decoration-rose-500 decoration-wavy underline-offset-4 data-[active=true]:ring-2 data-[active=true]:ring-rose-400',
  unknown: 'cursor-pointer rounded-[3px] bg-ink-800 px-0.5 text-ink-100 data-[active=true]:ring-2 data-[active=true]:ring-ink-500',
};

export default function Audit() {
  const [draft, setDraft] = useState('');
  const [submitted, setSubmitted] = useState('');
  const [events, setEvents] = useState([]);
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [active, setActive] = useState(null);

  const verdicts = useMemo(() => result?.verdicts || [], [result]);

  // Highlight each cited case in the draft, coloured by its verdict.
  const spans = useMemo(() => {
    const norm = normalize(submitted);
    const used = [];
    const out = [];
    for (const v of verdicts) {
      for (const needle of [v.case_name, v.citation].filter(Boolean)) {
        const n = normalize(needle);
        let from = 0;
        let i = norm.indexOf(n, from);
        while (i >= 0 && used.some(([a, b]) => i < b && i + n.length > a)) {
          from = i + 1;
          i = norm.indexOf(n, from);
        }
        if (i >= 0) {
          used.push([i, i + n.length]);
          out.push({ id: `v${v.index}`, start: i, end: i + n.length, text: n, tone: VERDICT[v.verdict]?.tone || 'unknown', label: VERDICT[v.verdict]?.label });
          break;
        }
      }
    }
    return out;
  }, [verdicts, submitted]);

  const tally = useMemo(() => {
    const t = { pass: 0, weak: 0, fail: 0, unknown: 0 };
    for (const v of verdicts) t[VERDICT[v.verdict]?.tone || 'unknown'] += 1;
    return t;
  }, [verdicts]);

  const submit = async (e) => {
    e.preventDefault();
    setRunning(true);
    setEvents([]);
    setResult(null);
    setError(null);
    setSubmitted(draft);
    try {
      const r = await runAudit({ draftText: draft }, (s) => setEvents((prev) => [...prev, s]));
      setResult(r);
      if (r.error) setError(friendlyError(r.error));
    } catch (err) {
      setError(friendlyError(err.message));
    } finally {
      setRunning(false);
    }
  };

  return (
    <Shell>
      <div className="flex flex-wrap items-end justify-between gap-4 pt-10 pb-8">
        <div>
          <Label>Check citations</Label>
          <h1 className="mt-2 text-3xl font-semibold sm:text-[34px]">Check every citation in a draft</h1>
          <p className="mt-2 max-w-2xl text-[15px] text-ink-400">
            Paste any draft, including one written by another AI tool. We find each case it cites, read the judgment (from our library, or from the web if needed), and tell you whether it really supports the point.
          </p>
        </div>
        {result && verdicts.length > 0 && (
          <button type="button" className="btn-primary" onClick={() => downloadAuditReport({ verdicts, draft: submitted, events })}>
            <Download className="h-4 w-4" />Download PDF report
          </button>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="space-y-6 lg:sticky lg:top-20 lg:self-start">
          <section className="panel p-5">
            {result && !running ? (
              <>
                <div className="mb-3 flex items-center justify-between">
                  <span className="text-sm font-medium text-ink-200">Your draft, with each citation marked</span>
                  <button type="button" onClick={() => { setResult(null); setEvents([]); }} className="inline-flex items-center gap-1 text-sm text-ink-400 hover:text-brand-600">
                    <RotateCcw className="h-3.5 w-3.5" />Check another draft
                  </button>
                </div>
                <Legend />
                <div className="mt-3 max-h-[55vh] overflow-y-auto pr-1">
                  <SourceDoc text={submitted} spans={spans} activeId={active} onHover={setActive}
                    onSelect={(id) => document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'center' })}
                    toneClass={(s) => MARK[s.tone]} />
                </div>
              </>
            ) : (
              <form onSubmit={submit} className="space-y-4">
                <div>
                  <label htmlFor="draft" className="mb-2 block text-sm font-medium text-ink-200">Draft to check</label>
                  <textarea id="draft" value={draft} onChange={(e) => setDraft(e.target.value)} rows={13}
                    placeholder="Paste a draft that cites cases…" className="field" />
                  <div className="mt-2 flex flex-wrap items-center gap-2">
                    <span className="text-xs text-ink-500">Want to see it work?</span>
                    <button type="button" onClick={() => setDraft(SAMPLE_DRAFT)} className="chip border-ink-700 bg-ink-900 text-ink-300 hover:border-brand-500 hover:text-brand-600">
                      Load an example (one citation is made up on purpose)
                    </button>
                  </div>
                </div>
                <div className="flex flex-wrap items-center justify-between gap-3 border-t border-ink-800 pt-4">
                  <p className="text-xs text-ink-500">Usually takes under 30 seconds.</p>
                  <button type="submit" disabled={running || draft.trim().length < 40} className="btn-primary">
                    {running ? 'Checking citations…' : 'Check citations'} <ArrowRight className="h-4 w-4" />
                  </button>
                </div>
              </form>
            )}
          </section>
          {!running && events.length > 0 && <PipelineRail steps={AUDIT_STEPS} events={events} running={false} title="How this check was done" />}
        </div>

        <div className="min-w-0 space-y-4">
          {error && <ErrorNote>{error}</ErrorNote>}
          {!result && !running && !error && <Explainer />}
          {running && !result && <PipelineRail steps={AUDIT_STEPS} events={events} running title="Checking your citations" />}

          {result && (
            <>
              <div className="panel grid grid-cols-2 divide-ink-700 sm:grid-cols-4 sm:divide-x">
                <Tally n={tally.pass} label="verified" cls="text-verdict-pass" />
                <Tally n={tally.fail} label="have a problem" cls="text-verdict-fail" />
                <Tally n={tally.weak} label="need a closer look" cls="text-verdict-weak" />
                <Tally n={tally.unknown} label="could not be checked" cls="text-ink-300" />
              </div>
              {verdicts.length === 0 && <div className="panel p-5 text-sm text-ink-300">We did not find any case citations in this draft.</div>}
              {verdicts.map((v, i) => <VerdictCard key={v.index} v={v} i={i} active={active === `v${v.index}`} onHover={setActive} />)}
            </>
          )}
        </div>
      </div>
    </Shell>
  );
}

function Legend() {
  return (
    <div className="flex flex-wrap gap-3 text-xs text-ink-400">
      <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-emerald-200" />Verified</span>
      <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-amber-200" />Needs a closer look</span>
      <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-rose-200" />Problem</span>
    </div>
  );
}

function Explainer() {
  const rows = [
    ['pass', 'Verified against source text', 'The judgment says it. Our reviewer quoted the passage, and we confirmed that quote appears in the judgment.'],
    ['fail', 'Judgment does not support this', 'The case is real, but it does not say what the draft claims.'],
    ['weak', 'Found online only', 'Not in our library and we could not read the full judgment online, but a web page names the case.'],
    ['fail', 'Not found, possibly fabricated', 'Not in our library and not found on the web. Treat it with suspicion.'],
  ];
  return (
    <div className="panel p-6 sm:p-8">
      <h2 className="text-lg font-semibold">What each result means</h2>
      <ul className="mt-5 space-y-4">
        {rows.map(([tone, label, text]) => (
          <li key={label} className="flex flex-col gap-1.5 sm:flex-row sm:items-start sm:gap-4">
            <div className="sm:w-60 sm:shrink-0"><Stamp tone={tone}>{label}</Stamp></div>
            <p className="text-sm text-ink-300">{text}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Tally({ n, label, cls }) {
  return (
    <div className="p-4 text-center">
      <div className={`text-3xl font-semibold tabular-nums ${cls}`}>{n}</div>
      <div className="mt-0.5 text-xs text-ink-400">{label}</div>
    </div>
  );
}

function VerdictCard({ v, i, active, onHover }) {
  const meta = VERDICT[v.verdict] || VERDICT.unverified;
  const ev = v.claim?.evidence || [];
  const passage = ev.find((e) => e.kind === 'judgment_passage');
  const web = ev.filter((e) => e.kind === 'web_result');
  return (
    <motion.article id={`v${v.index}`} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: i * 0.06 }}
      onMouseEnter={() => onHover(`v${v.index}`)} onMouseLeave={() => onHover(null)}
      className={`rounded-xl border bg-ink-900 p-5 transition ${active ? 'border-brand-500 shadow-glow' : 'border-ink-700'}`}>
      <div className="flex flex-wrap items-center gap-2">
        <Stamp tone={meta.tone}>{meta.label}</Stamp>
        {v.fetched_from && (
          <span className="chip border-brand-100 bg-brand-100 text-brand-600" title="This judgment is not in our library; its full text was fetched from the web with Tavily and checked the same way.">
            <Globe className="h-3 w-3" />Judgment read from {v.fetched_from}
          </span>
        )}
      </div>
      <h3 className="mt-3 text-[16px] font-semibold">{v.case_name || 'Unnamed citation'}</h3>
      {v.citation && <p className="text-xs text-ink-500">{v.citation}</p>}
      <dl className="mt-3 space-y-2 text-sm">
        <div><dt className="inline font-medium text-ink-200">Used in the draft for: </dt><dd className="inline text-ink-300">{v.proposition || 'no point stated'}</dd></div>
        <div><dt className="inline font-medium text-ink-200">What we found: </dt><dd className="inline text-ink-300">{v.reason}</dd></div>
      </dl>
      {passage?.quote && (
        <figure className="mt-3 rounded-lg border-l-4 border-brand-500 bg-ink-850 px-4 py-3">
          <figcaption className="mb-1 text-xs font-medium text-ink-400">What the judgment says{passage.court ? ` · ${passage.court}` : ''}</figcaption>
          <blockquote className="font-serif text-[15px] leading-relaxed text-ink-200">“{passage.quote}”</blockquote>
        </figure>
      )}
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {passage?.source_url && (
          <a href={passage.source_url} target="_blank" rel="noreferrer" className="chip border-ink-700 text-brand-600 hover:border-brand-500">
            Read the full judgment <ExternalLink className="h-3 w-3" />
          </a>
        )}
        <ModelChip model={passage?.judge_model} />
      </div>
      {web.length > 0 && (
        <ul className="mt-3 space-y-1 border-t border-ink-800 pt-3">
          {web.map((w) => (
            <li key={w.url} className="flex items-start gap-2 text-sm">
              <Globe className="mt-0.5 h-4 w-4 shrink-0 text-ink-500" />
              <a href={w.url} target="_blank" rel="noreferrer" className="text-brand-600 underline decoration-brand-100 underline-offset-2">{w.title || w.url}</a>
            </li>
          ))}
        </ul>
      )}
    </motion.article>
  );
}

import React from 'react';
import { Check, LoaderCircle, Minus, X } from 'lucide-react';
import { Label, ModelChip } from './ui';

/**
 * Step-by-step progress. Status per step comes from the server-sent trace events;
 * repeated events for one step (e.g. two re-check rounds) are merged.
 */
export default function PipelineRail({ steps, events, running, title = 'Progress' }) {
  const byStep = {};
  const rounds = {};
  for (const e of events) {
    if (e.step === 'start') continue;
    byStep[e.step] = e;
    rounds[e.step] = (rounds[e.step] || 0) + 1;
  }
  const finished = !running && events.length > 0;
  const firstPending = steps.findIndex((s) => !byStep[s.key] && !(s.optional && byStep.good_law));
  const errored = events.some((e) => e.status === 'error');
  const stopped = events.some((e) => e.status === 'abstain');
  const done = steps.filter((s) => byStep[s.key]).length;

  return (
    <section className="panel p-5" aria-live="polite">
      <div className="mb-4 flex items-center justify-between gap-3">
        <Label>{title}</Label>
        {running && <span className="text-xs font-medium text-brand-600">Step {Math.min(done + 1, steps.length)} of {steps.length}</span>}
        {finished && !errored && <span className="chip border-emerald-200 bg-emerald-50 text-verdict-pass"><Check className="h-3 w-3" />Done</span>}
      </div>
      {running && (
        <div className="mb-5 h-1.5 overflow-hidden rounded-full bg-ink-800">
          <div className="h-full rounded-full bg-brand-500 transition-all duration-500" style={{ width: `${Math.max(6, (done / steps.length) * 100)}%` }} />
        </div>
      )}
      <ol>
        {steps.map((s, i) => {
          const ev = byStep[s.key];
          let state = 'todo';
          if (ev) state = ev.status === 'error' ? 'error' : 'done';
          else if (running && i === firstPending) state = 'active';
          else if (finished || (stopped && i > 2) || errored) state = 'skipped';
          if (s.optional && !ev && state !== 'active') state = finished || byStep.good_law ? 'skipped' : 'todo';
          if (s.optional && state === 'skipped') return null;
          const last = i === steps.length - 1;
          return (
            <li key={s.key} className="relative flex gap-3 pb-4 last:pb-0">
              {!last && <span className={`absolute left-[11px] top-7 h-[calc(100%-16px)] w-px ${state === 'done' ? 'bg-emerald-300' : 'bg-ink-700'}`} />}
              <Dot state={state} />
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <span className={`text-sm font-medium ${state === 'todo' || state === 'skipped' ? 'text-ink-500' : 'text-ink-100'}`}>{s.name}</span>
                  {rounds[s.key] > 1 && <span className="text-xs text-ink-400">{rounds[s.key]} rounds</span>}
                  {ev?.elapsed_s != null && <span className="text-xs text-ink-500">{ev.elapsed_s}s</span>}
                  {ev?.model && <ModelChip model={ev.model} />}
                </div>
                <p className={`text-[13px] ${ev ? (ev.status === 'error' ? 'text-verdict-fail' : 'text-ink-400') : 'text-ink-500'}`}>
                  {ev?.detail || (state === 'skipped' ? 'Not needed' : s.hint)}
                </p>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function Dot({ state }) {
  const base = 'relative z-10 mt-0.5 grid h-6 w-6 shrink-0 place-items-center rounded-full border';
  if (state === 'done') return <span className={`${base} border-emerald-300 bg-emerald-50`}><Check className="h-3.5 w-3.5 text-verdict-pass" /></span>;
  if (state === 'error') return <span className={`${base} border-rose-300 bg-rose-50`}><X className="h-3.5 w-3.5 text-verdict-fail" /></span>;
  if (state === 'active') return <span className={`${base} border-brand-500 bg-brand-100`}><LoaderCircle className="h-3.5 w-3.5 animate-spin text-brand-600" /></span>;
  if (state === 'skipped') return <span className={`${base} border-ink-700 bg-ink-900`}><Minus className="h-3 w-3 text-ink-500" /></span>;
  return <span className={`${base} border-ink-700 bg-ink-900`}><span className="h-1.5 w-1.5 rounded-full bg-ink-600" /></span>;
}

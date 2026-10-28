import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { ChevronDown, ExternalLink, Globe } from 'lucide-react';
import { ModelChip, StatusBadge } from './ui';

/** One point in the brief: `text` is the checked sentence, `claim` holds its evidence. */
export default function ClaimCard({ id, text, claim, type, active, onHover, refsActive, onRefHover, index = 0 }) {
  const ev = claim?.evidence || [];
  const passage = ev.find((e) => e.kind === 'judgment_passage');
  const web = ev.filter((e) => e.kind === 'web_result');
  const mapping = ev.find((e) => e.kind === 'mapping_row');

  return (
    <motion.article
      id={`claim-${id}`}
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, delay: Math.min(index * 0.04, 0.3) }}
      onMouseEnter={() => onHover?.(id)}
      onMouseLeave={() => onHover?.(null)}
      className={`rounded-xl border bg-ink-900 p-5 transition ${active || refsActive ? 'border-brand-500 shadow-glow' : 'border-ink-700 hover:border-ink-600'}`}
    >
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <StatusBadge type={type} status={claim?.status || 'passed'} />
        <span className="text-xs text-ink-500">Point {id}</span>
        {type === 'strategy_suggestion' && claim?.refs?.length > 0 && (
          <span className="flex flex-wrap items-center gap-1 text-xs text-ink-500">
            · based on
            {claim.refs.map((r) => (
              <button key={r} type="button" onMouseEnter={() => onRefHover?.(r)} onMouseLeave={() => onRefHover?.(null)}
                onClick={() => document.getElementById(`claim-${r}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' })}
                className="rounded border border-ink-700 bg-ink-800 px-1.5 font-medium text-ink-300 hover:border-brand-500 hover:text-brand-600">
                {r}
              </button>
            ))}
          </span>
        )}
      </div>

      {type === 'precedent_holding' && passage ? (
        <PrecedentBody text={text} passage={passage} />
      ) : (
        <p className={`leading-relaxed text-ink-200 ${type === 'fact' ? 'font-serif text-[16px]' : 'text-[15px]'}`}>
          {type === 'strategy_suggestion' ? text.replace(/^Suggestion: /, '') : text}
        </p>
      )}

      {mapping && <MappingSource source={mapping.source} />}

      {web.length > 0 && (
        <ul className="mt-3 space-y-1.5 border-t border-ink-800 pt-3">
          {web.map((w) => (
            <li key={w.url} className="flex items-start gap-2 text-sm">
              <Globe className="mt-0.5 h-4 w-4 shrink-0 text-ink-500" />
              <a href={w.url} target="_blank" rel="noreferrer" className="text-brand-600 underline decoration-brand-100 underline-offset-2 hover:decoration-brand-500">
                {w.title || w.url}
              </a>
            </li>
          ))}
        </ul>
      )}
    </motion.article>
  );
}

function PrecedentBody({ text, passage }) {
  const [open, setOpen] = useState(false);
  // Rendered text is "<title>: <point>. The judgment says: "<quote>"" — show the parts separately.
  const point = text.includes(': ') ? text.slice(text.indexOf(': ') + 2).split(' The judgment says:')[0] : text;
  const name = passage.title?.replace(/ on \d.*$/, '') || passage.case_id;
  return (
    <div>
      <h4 className="text-[16px] font-semibold text-ink-100">{name}</h4>
      <p className="mb-3 text-xs text-ink-500">{[passage.court, passage.date].filter(Boolean).join(' · ')}</p>
      <p className="text-[15px] leading-relaxed text-ink-200">{point}</p>
      <figure className="mt-3 rounded-lg border-l-4 border-brand-500 bg-ink-850 px-4 py-3">
        <figcaption className="mb-1 text-xs font-medium text-ink-400">What the judgment says</figcaption>
        <blockquote className="font-serif text-[15px] leading-relaxed text-ink-200">“{passage.quote}”</blockquote>
      </figure>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        {passage.source_url && (
          <a href={passage.source_url} target="_blank" rel="noreferrer" className="chip border-ink-700 text-brand-600 hover:border-brand-500">
            Read the full judgment <ExternalLink className="h-3 w-3" />
          </a>
        )}
        {passage.judge_verdict && <span className="chip border-ink-700 bg-ink-800 text-ink-400">Reviewer: {passage.judge_verdict.replace('_', ' ')}</span>}
        <ModelChip model={passage.judge_model} />
        {passage.judge_quote && passage.judge_quote !== passage.quote && (
          <button type="button" onClick={() => setOpen(!open)} className="chip border-ink-700 text-ink-400 hover:text-ink-100">
            Reviewer's passage <ChevronDown className={`h-3 w-3 transition ${open ? 'rotate-180' : ''}`} />
          </button>
        )}
      </div>
      {open && <p className="mt-2 border-l-2 border-ink-700 pl-3 font-serif text-[14px] text-ink-300">“{passage.judge_quote}”</p>}
    </div>
  );
}

/** "CAPT Bhopal … table, p. 10 (https://…)" -> readable label with the link behind it. */
function MappingSource({ source }) {
  const m = /^(.*?)\s*\((https?:[^)]+)\)\s*$/.exec(source || '');
  const label = (m ? m[1] : source || 'mapping table').replace(/^CAPT Bhopal BNS-IPC correspondence table/, 'official CAPT Bhopal table').replace(/, p\. /, ', page ');
  return (
    <p className="mt-2 text-xs text-ink-500">
      Source:{' '}
      {m ? <a href={m[2]} target="_blank" rel="noreferrer" className="text-brand-600 underline decoration-brand-100 underline-offset-2">{label}</a> : label}
    </p>
  );
}

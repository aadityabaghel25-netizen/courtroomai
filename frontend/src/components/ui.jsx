import React from 'react';
import { Link, NavLink } from 'react-router-dom';
import { CircleCheck, CircleHelp, CircleX, Cpu, Info, Scale, TriangleAlert } from 'lucide-react';
import { modelName } from '../lib/steps';

export function Shell({ children }) {
  return (
    <div className="flex min-h-screen flex-col bg-chambers text-ink-200">
      <Nav />
      <main className="mx-auto w-full max-w-shell flex-1 px-4 pb-20 sm:px-6">{children}</main>
      <Footer />
    </div>
  );
}

function Nav() {
  const link = ({ isActive }) =>
    `rounded-md px-3 py-1.5 text-sm font-medium transition ${isActive ? 'bg-brand-100 text-brand-600' : 'text-ink-400 hover:bg-ink-800 hover:text-ink-100'}`;
  return (
    <header className="sticky top-0 z-30 border-b border-ink-700 bg-ink-900/90 backdrop-blur">
      <div className="mx-auto flex h-14 max-w-shell items-center justify-between px-4 sm:px-6">
        <Link to="/" className="flex items-center gap-2.5">
          <span className="grid h-8 w-8 place-items-center rounded-lg bg-brand-600">
            <Scale className="h-4 w-4 text-white" />
          </span>
          <span className="text-[15px] font-semibold text-ink-100">CourtroomAI</span>
        </Link>
        <nav className="flex items-center gap-1">
          <NavLink to="/brief" className={link}>Case brief</NavLink>
          <NavLink to="/audit" className={link}>Check citations</NavLink>
        </nav>
      </div>
    </header>
  );
}

function Footer() {
  return (
    <footer className="border-t border-ink-700 bg-ink-900">
      <div className="mx-auto flex max-w-shell flex-col items-center justify-between gap-2 px-4 py-6 text-xs text-ink-400 sm:flex-row sm:px-6">
        <p>CourtroomAI is a research aid, not legal advice. Please read every source before relying on it.</p>
        <p>Powered by NVIDIA Nemotron on Nebius Token Factory, with Tavily search</p>
      </div>
    </footer>
  );
}

export function Label({ children, className = '' }) {
  return <span className={`label ${className}`}>{children}</span>;
}

export function ModelChip({ model }) {
  if (!model) return null;
  return (
    <span className="chip border-ink-700 bg-ink-800 text-ink-400" title={model}>
      <Cpu className="h-3 w-3 text-brand-500" />
      {modelName(model)}
    </span>
  );
}

// "Verified against source text" is used only for a judgment that passed every check.
const PASSED_LABEL = {
  precedent_holding: 'Verified against source text',
  fact: 'Quoted from the FIR',
  statute_mapping: 'From the official table',
  good_law_status: 'Not a good-law confirmation',
  strategy_suggestion: 'Suggestion',
};

const STYLES = {
  pass: { cls: 'border-emerald-200 bg-emerald-50 text-verdict-pass', Icon: CircleCheck },
  info: { cls: 'border-brand-100 bg-brand-100 text-brand-600', Icon: Info },
  weak: { cls: 'border-amber-200 bg-amber-50 text-verdict-weak', Icon: TriangleAlert },
  fail: { cls: 'border-rose-200 bg-rose-50 text-verdict-fail', Icon: CircleX },
  unknown: { cls: 'border-ink-700 bg-ink-800 text-ink-400', Icon: CircleHelp },
};

function statusTone(type, status) {
  if (status === 'passed') {
    if (type === 'good_law_status' || type === 'strategy_suggestion') return 'info';
    return 'pass';
  }
  if (status === 'weak') return 'weak';
  if (status === 'failed') return 'fail';
  return 'unknown';
}

export function StatusBadge({ type, status }) {
  const tone = statusTone(type, status);
  const text = status === 'passed' ? PASSED_LABEL[type] || 'Passed'
    : status === 'weak' ? 'Only partly supported' : status === 'failed' ? 'Did not pass checks' : 'Could not be checked';
  const { cls, Icon } = STYLES[tone];
  return (
    <span className={`chip ${cls}`}>
      <Icon className="h-3.5 w-3.5" />
      {text}
    </span>
  );
}

/** Verdict pill for citation checks. */
export function Stamp({ tone, children }) {
  const { cls, Icon } = STYLES[tone] || STYLES.unknown;
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs font-semibold ${cls}`}>
      <Icon className="h-3.5 w-3.5" />
      {children}
    </span>
  );
}

export function ErrorNote({ children }) {
  return (
    <div role="alert" className="flex items-start gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-ink-200">
      <CircleX className="mt-0.5 h-4 w-4 shrink-0 text-verdict-fail" />
      <div>{children}</div>
    </div>
  );
}

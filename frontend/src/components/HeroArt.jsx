import React from 'react';
import { motion } from 'framer-motion';
import { Check, FileText, Quote, Scale, X } from 'lucide-react';

/** Original illustration for the landing page: a brief being checked line by line. */
export default function HeroArt() {
  const rows = [
    { icon: FileText, label: 'Fact quoted from the FIR', ok: true },
    { icon: Scale, label: 'IPC 420 → BNS 318(4), from the official table', ok: true },
    { icon: Quote, label: 'Judgment quote matches word for word', ok: true },
    { icon: Quote, label: 'Cited case not found anywhere', ok: false },
  ];
  return (
    <div className="relative mx-auto w-full max-w-md">
      <div className="absolute -inset-6 rounded-[36px] bg-gradient-to-br from-brand-100 via-white to-emerald-50" />
      <div className="relative rounded-2xl border border-ink-700 bg-ink-900 p-6 shadow-card">
        <div className="mb-4 flex items-center justify-between">
          <div>
            <p className="text-xs font-semibold uppercase tracking-label text-ink-400">Case brief</p>
            <p className="text-sm font-semibold text-ink-100">Checking each point…</p>
          </div>
          <span className="grid h-9 w-9 place-items-center rounded-lg bg-brand-600"><Scale className="h-5 w-5 text-white" /></span>
        </div>
        <ul className="space-y-2.5">
          {rows.map((r, i) => (
            <motion.li key={r.label} initial={{ opacity: 0, x: 12 }} animate={{ opacity: 1, x: 0 }} transition={{ delay: 0.3 + i * 0.35 }}
              className={`flex items-center gap-3 rounded-lg border px-3 py-2.5 text-sm ${r.ok ? 'border-ink-700 bg-ink-850' : 'border-rose-200 bg-rose-50'}`}>
              <r.icon className="h-4 w-4 shrink-0 text-ink-400" />
              <span className={`flex-1 ${r.ok ? 'text-ink-200' : 'text-ink-200 line-through decoration-rose-400'}`}>{r.label}</span>
              {r.ok
                ? <span className="grid h-5 w-5 place-items-center rounded-full bg-emerald-50 ring-1 ring-emerald-200"><Check className="h-3 w-3 text-verdict-pass" /></span>
                : <span className="grid h-5 w-5 place-items-center rounded-full bg-rose-100 ring-1 ring-rose-200"><X className="h-3 w-3 text-verdict-fail" /></span>}
            </motion.li>
          ))}
        </ul>
        <motion.p initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 1.9 }} className="mt-4 text-xs text-ink-400">
          Illustration. Only points that pass reach your brief; the rest are listed with the reason.
        </motion.p>
      </div>
    </div>
  );
}

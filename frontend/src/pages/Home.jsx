import React from 'react';
import { Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { ArrowRight, BookOpen, Check, Download, FileSearch, FileText, ListChecks, Quote, ShieldCheck, X } from 'lucide-react';
import HeroArt from '../components/HeroArt';
import { Label, Shell } from '../components/ui';

const fade = (d = 0) => ({ initial: { opacity: 0, y: 10 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.5, delay: d } });

export default function Home() {
  return (
    <Shell>
      <section className="grid items-center gap-12 pt-12 pb-16 lg:grid-cols-[1.1fr_0.9fr] lg:pt-16">
        <div>
          <motion.div {...fade(0)}>
            <span className="chip border-brand-100 bg-brand-100 text-brand-600">For criminal law practitioners in India</span>
          </motion.div>
          <motion.h1 {...fade(0.06)} className="mt-5 text-4xl font-bold leading-[1.1] sm:text-5xl">
            Case research you can check, line by line.
          </motion.h1>
          <motion.p {...fade(0.12)} className="mt-5 max-w-xl text-lg leading-relaxed text-ink-400">
            Paste an FIR and get a case brief where every point is backed by its source: the FIR itself, the official section tables, or the exact words of a judgment. Or paste any draft and find out which of its citations hold up.
          </motion.p>
          <motion.div {...fade(0.18)} className="mt-8 flex flex-wrap gap-3">
            <Link to="/brief" className="btn-primary px-6 py-3">Prepare a case brief <ArrowRight className="h-4 w-4" /></Link>
            <Link to="/audit" className="btn-ghost px-6 py-3">Check a draft's citations</Link>
          </motion.div>
          <motion.ul {...fade(0.24)} className="mt-8 grid gap-2 text-sm text-ink-300 sm:grid-cols-2">
            {['Every point shows its source', 'Fake citations are flagged', 'Nothing hidden: rejected points are listed', 'Download a PDF report'].map((t) => (
              <li key={t} className="flex items-center gap-2"><Check className="h-4 w-4 text-verdict-pass" />{t}</li>
            ))}
          </motion.ul>
        </div>

        <motion.div initial={{ opacity: 0, scale: 0.98 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 0.6 }}>
          <HeroArt />
        </motion.div>
      </section>

      <section className="grid gap-6 border-t border-ink-700 py-16 md:grid-cols-3">
        <div>
          <Label>Why this matters</Label>
          <h2 className="mt-3 text-2xl font-semibold sm:text-3xl">AI tools can cite cases that do not exist, or that say something else.</h2>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 md:col-span-2">
          <Compare icon={X} tone="text-verdict-fail" title="The usual approach" text="Ask the AI to be careful. It can still write any case name, citation or section number, and you cannot tell which ones are real." />
          <Compare icon={ShieldCheck} tone="text-verdict-pass" title="How CourtroomAI works" text="The AI can only suggest points with a named source. Each point is checked against that source, and only the ones that pass reach your brief." highlight />
        </div>
      </section>

      <section className="border-t border-ink-700 py-16">
        <Label>How each point is checked</Label>
        <h2 className="mt-3 max-w-2xl text-2xl font-semibold sm:text-3xl">Different kinds of points, different checks.</h2>
        <div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-5">
          {[
            [FileText, 'Facts', 'Quoted word for word from your FIR.'],
            [BookOpen, 'Sections', 'Matched from IPC to BNS and CrPC to BNSS using the official tables and the date of the offence.'],
            [Quote, 'Judgments', 'The case must exist, the quote must match the judgment exactly, and an independent reviewer must confirm it supports the point.'],
            [FileSearch, 'Later cases', 'Web results that mention each judgment, so you can see how later courts treated it.'],
            [ListChecks, 'Suggestions', 'Ideas to consider, built only on points that passed. Clearly marked as suggestions.'],
          ].map(([Icon, t, d], i) => (
            <motion.div key={t} initial={{ opacity: 0, y: 10 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ delay: i * 0.05 }} className="panel p-5">
              <span className="grid h-9 w-9 place-items-center rounded-lg bg-brand-100"><Icon className="h-5 w-5 text-brand-600" /></span>
              <h3 className="mt-4 font-semibold">{t}</h3>
              <p className="mt-1.5 text-sm leading-relaxed text-ink-400">{d}</p>
            </motion.div>
          ))}
        </div>
      </section>

      <section className="grid gap-4 border-t border-ink-700 py-16 md:grid-cols-2">
        <ModeCard to="/brief" title="Prepare a case brief" text="Paste an FIR. Get facts, sections, supporting judgments, later cases and suggested arguments, each with its source."
          points={['Live progress you can follow', 'Facts highlighted in your FIR', 'Download as a PDF report']} />
        <ModeCard to="/audit" title="Check a draft's citations" text="Paste any draft. Each case it cites is looked up and read, and you get a clear result for every citation."
          points={['Works on drafts from any AI tool', 'Made-up citations are called out', 'Download as a PDF report']} />
      </section>

      <section className="mb-4 rounded-2xl border border-ink-700 bg-ink-900 p-6 text-sm text-ink-400 sm:p-8">
        <p><span className="font-semibold text-ink-200">Please note:</span> CourtroomAI is a research aid for advocates, not legal advice. It does not predict outcomes. Always read the judgments it points you to before relying on them.</p>
      </section>
    </Shell>
  );
}

function Compare({ icon: Icon, tone, title, text, highlight }) {
  return (
    <div className={`panel p-6 ${highlight ? 'ring-2 ring-brand-100' : ''}`}>
      <Icon className={`h-5 w-5 ${tone}`} />
      <h3 className="mt-3 font-semibold">{title}</h3>
      <p className="mt-1.5 text-sm leading-relaxed text-ink-400">{text}</p>
    </div>
  );
}

function ModeCard({ to, title, text, points }) {
  return (
    <Link to={to} className="group panel p-7 transition hover:border-brand-500">
      <h3 className="text-xl font-semibold">{title}</h3>
      <p className="mt-2 text-[15px] text-ink-400">{text}</p>
      <ul className="mt-4 space-y-1.5">
        {points.map((p) => (
          <li key={p} className="flex items-center gap-2 text-sm text-ink-300">
            {p.startsWith('Download') ? <Download className="h-4 w-4 text-brand-500" /> : <Check className="h-4 w-4 text-verdict-pass" />}{p}
          </li>
        ))}
      </ul>
      <span className="mt-5 inline-flex items-center gap-1 text-sm font-semibold text-brand-600">Get started <ArrowRight className="h-4 w-4 transition group-hover:translate-x-1" /></span>
    </Link>
  );
}

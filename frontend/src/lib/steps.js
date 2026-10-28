// Plain-English names for each pipeline step, shared by the screen and the PDF report.
export const BRIEF_STEPS = [
  { key: 'intake', name: 'Reading the FIR', hint: 'Finding the people, sections, dates and key facts' },
  { key: 'statutes', name: 'Matching sections to the new codes', hint: 'IPC to BNS and CrPC to BNSS, from the official table' },
  { key: 'retrieve', name: 'Searching the judgment library', hint: 'Keyword and meaning-based search, then re-ranked' },
  { key: 'draft', name: 'Drafting points', hint: 'Each point must name its source' },
  { key: 'verify', name: 'Checking each point', hint: 'Case exists, quote matches word for word, reviewer confirms support' },
  { key: 'redraft', name: 'Re-checking points that failed', hint: 'Up to two more attempts', optional: true },
  { key: 'good_law', name: 'Looking for later cases', hint: 'Web search for cases that followed or departed from these judgments' },
  { key: 'render', name: 'Putting the brief together', hint: 'Only points that passed, then a final check of every sentence' },
];

export const AUDIT_STEPS = [
  { key: 'extract', name: 'Finding citations in your draft', hint: 'Each citation and the point it is used for' },
  { key: 'verify', name: 'Checking each citation', hint: 'Against the judgment text, or a web search if it is not in our library' },
];

export const SECTION_COPY = {
  fact: { title: 'What the FIR says', note: 'Quoted word for word from the FIR. Hover a point to see it highlighted in the FIR.' },
  statute_mapping: { title: 'Sections and their new-law equivalents', note: 'Taken from the official IPC to BNS and CrPC to BNSS tables, based on the date of the offence.' },
  precedent_holding: { title: 'Supporting judgments', note: 'Each judgment is in our library, its quote matches the judgment word for word, and an independent AI reviewer confirmed it supports the point.' },
  good_law_status: { title: 'Later cases to read', note: 'Web results that mention these judgments. Read them before relying on a judgment; this is not a confirmation that it is still good law.' },
  strategy_suggestion: { title: 'Suggested lines of argument', note: 'Ideas for you to weigh. Each one is built only on points above that passed every check.' },
};

export const MODEL_NAMES = {
  'nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B': 'Nemotron Nano',
  'nvidia/nemotron-3-super-120b-a12b': 'Nemotron Super',
  'nvidia/Nemotron-3-Ultra-550b-a55b': 'Nemotron Ultra',
};

export function modelName(id) {
  if (!id) return '';
  if (id === 'tavily') return 'Tavily';
  if (id.includes('reranker')) return 'Search engine';
  return MODEL_NAMES[id] || (id.includes('/') ? id.split('/').pop() : id);
}

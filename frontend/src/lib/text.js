/** Same normalisation as core/normalize.py: NFKC + collapse whitespace + trim. */
export function normalize(text) {
  return (text || '').normalize('NFKC').replace(/\s+/g, ' ').trim();
}

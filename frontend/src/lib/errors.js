/** Turn technical failures into something a user can act on. */
export function friendlyError(message) {
  const m = (message || '').toLowerCase();
  if (m.includes('rate limit')) return 'You have made several requests in a short time. Please wait a minute and try again.';
  if (m.includes('usage cap')) return 'The demo has reached today’s usage limit. Please try again tomorrow.';
  if (m.includes('failed to fetch') || m.includes('network')) return 'We could not reach the server. Please check your connection and try again.';
  if (m.includes('too large')) return 'That text is too long. Please paste a shorter document.';
  if (m.includes('intake failed')) return 'We could not read this FIR. Please check the text and try again.';
  return message || 'Something went wrong. Please try again.';
}

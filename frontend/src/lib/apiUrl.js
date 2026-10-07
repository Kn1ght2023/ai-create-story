// Must stay in sync with resolveChatCompletionsURL in api.go.

function hasAPIVersionSegment(u) {
  for (const seg of u.split('/')) {
    if (seg.length >= 2 && seg[0] === 'v' && seg[1] >= '0' && seg[1] <= '9') {
      return true;
    }
  }
  return false;
}

/** @returns {string} resolved chat/completions URL, or '' if base is empty */
export function resolveChatCompletionsURL(base, strict) {
  let b = (base || '').trim().replace(/\/+$/, '');
  if (!b) return '';
  if (b.endsWith('/chat/completions')) return b;
  if (strict) return b + '/chat/completions';
  if (hasAPIVersionSegment(b)) return b + '/chat/completions';
  return b + '/v1/chat/completions';
}

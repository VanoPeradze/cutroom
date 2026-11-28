/* Shared transcript helpers for Script view and prompt edits. Pure functions,
   all in edit time. */

const PAD = 0.04;
const MIN_RANGE = 0.08;
const round = (n) => Math.round(n * 1000) / 1000;

/** Lower case, no Hebrew points, no surrounding punctuation. */
export function normalizeWord(word) {
  return String(word ?? '').normalize('NFKC').toLowerCase().replace(/[֑-ׇ]/g, '')
    .replace(/^[^\p{L}\p{N}]+|[^\p{L}\p{N}]+$/gu, '');
}

/** Paragraphs of words in edit time: [{id, dir, estimated, words:[{i,start,end,text}]}] */
export function scriptParagraphs(captions) {
  let i = 0;
  return (captions || []).filter((c) => !c.hidden && Array.isArray(c.words) && c.words.length)
    .sort((a, b) => a.start - b.start)
    .map((c) => ({ id: c.id, dir: c.direction === 'rtl' ? 'rtl' : 'auto', estimated: Boolean(c.estimated_words),
      words: c.words.map(([start, end, text]) => ({ start: Number(start), end: Number(end), text: String(text).trim() }))
        .filter((w) => w.text && Number.isFinite(w.start) && Number.isFinite(w.end)).map((w) => ({ i: i++, ...w })) }))
    .filter((p) => p.words.length);
}

/** The edit-time range covering words a..b, reaching into the pauses around them. */
export function selectionRange(words, a, b) {
  const lo = Math.min(a, b), hi = Math.max(a, b);
  const first = words[lo], last = words[hi];
  if (!first || !last) return null;
  const before = words[lo - 1], after = words[hi + 1];
  const start = before ? Math.max(before.end, first.start - PAD) : Math.max(0, first.start - PAD);
  const end = after ? Math.min(after.start, last.end + PAD) : last.end + PAD;
  return end - start >= MIN_RANGE ? { start: round(start), end: round(end) } : null;
}

/**
 * Word index spans [lo, hi] where the query's words are said in a row.
 * With prefix (the default, for typing) the last query word may be the start
 * of a spoken word, and a one-word query may appear inside a word.
 */
export function findMatches(words, query, { prefix = true } = {}) {
  const q = String(query ?? '').split(/\s+/).map(normalizeWord).filter(Boolean);
  if (!q.length) return [];
  const spoken = (words || []).map((w) => normalizeWord(w.text ?? w.word));
  const out = [];
  for (let i = 0; i + q.length <= spoken.length; i++) {
    const hit = q.every((part, k) => {
      const said = spoken[i + k];
      if (!prefix) return said === part;
      if (q.length === 1) return said.includes(part);
      return k === q.length - 1 ? said.startsWith(part) : said === part;
    });
    if (hit) { out.push([i, i + q.length - 1]); i += q.length - 1; }
  }
  return out;
}

/** Sorted, merged, non-overlapping ranges of at least 0.08 s. */
export function mergeRanges(ranges) {
  const rows = (ranges || []).filter(Boolean).map((r) => ({ start: r.start, end: r.end })).sort((a, b) => a.start - b.start);
  const merged = [];
  for (const row of rows) {
    const last = merged.at(-1);
    if (last && row.start <= last.end + 0.02) last.end = Math.max(last.end, row.end);
    else merged.push(row);
  }
  return merged.filter((r) => r.end - r.start >= MIN_RANGE).map((r) => ({ start: round(r.start), end: round(r.end) }));
}

/** "1:23.5", "83", "83s", "1:02:03" → seconds, or null. */
export function parseTime(text) {
  const raw = String(text ?? '').trim().replace(/(?:s|sec|secs|seconds|שניות|שנ׳)$/i, '').trim();
  if (!/^\d+(?::\d{1,2})*(?:\.\d+)?$/.test(raw)) return null;
  return raw.split(':').reduce((sum, part) => sum * 60 + Number(part), 0);
}

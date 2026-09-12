# Offline transcript evaluation

`scripts/evaluate_transcript.py` compares existing transcript JSON with a human
reference. It uses only the Python standard library, reads inputs without changing
them, and prints a JSON report to stdout. It does not load models, transcribe audio,
download assets, or contact any service.

```powershell
.venv\Scripts\python.exe scripts/evaluate_transcript.py reference.json project.json
```

The second argument can also be a standalone CUTROOM transcript JSON. Both inputs
accept the same formats: a transcript object, a segment array, or a project object
whose transcript is stored at `analysis.transcript`. JSON must be UTF-8; a BOM is
accepted. Invalid JSON, malformed transcript structures, and invalid timing values
produce a diagnostic on stderr and exit code 2.

## Human reference format

Create the reference by listening to the whole recording and checking the wording,
including later sections. Use the source audio clock for all times, in seconds.

```json
{
  "language": "en",
  "text": "Welcome back. Here is the conclusion.",
  "segments": [
    {"start": 1.0, "end": 2.2, "text": "Welcome back."},
    {"start": 20.0, "end": 22.0, "text": "Here is the conclusion."}
  ],
  "speech_intervals": [
    {"start": 1.0, "end": 2.2},
    {"start": 20.0, "end": 22.0}
  ]
}
```

`language` is optional metadata and never changes scoring. `text` is optional when
`segments` are supplied: segment text is then joined in array order. If `text` is
present, it is authoritative for lexical scoring; keep it consistent with the
segments. A text-only reference is sufficient for WER and CER.

Optional reference `speech_intervals` are human-annotated speech spans, excluding
silence. They take precedence over reference segment spans. Without that field,
timed reference segments containing normalized nonempty text define the expected
speech intervals. Hypothesis coverage always uses timed segments with nonempty
normalized text; it does not trust a hypothesis coverage flag, media duration, or
last timestamp. Every timed row must have finite numeric `0 <= start < end`.

## What the scores mean

- **WER** is unit-cost Levenshtein word errors divided by reference words. Words
  are whitespace-separated tokens; there is no language-specific tokenizer.
- **CER** is unit-cost Levenshtein character errors divided by reference
  characters, excluding whitespace. Characters are Unicode code points, not
  grapheme clusters. CER is more informative for Chinese or Japanese text without
  word spaces; whitespace WER should not be presented as linguistically segmented
  WER for those languages.
- Both report `errors`, `reference_units`, `hypothesis_units`, `rate`, and
  `status`. Lower error rates are better. Rates are fractions and may exceed 1
  when there are many insertions. These are text-error measures, not percentages
  of confidently recognized speech.

Normalization applies Unicode NFKC, case folding, punctuation removal, removal of
Unicode format controls (including invisible direction marks), and whitespace
collapse. CER additionally removes spaces. Diacritics and vowel marks are retained;
there is no English-only cleanup, stemming, transliteration, or translation.
Punctuation is removed rather than replaced by spaces: `can't` becomes `cant`,
and `hello,world` becomes `helloworld`. Use consistent annotation conventions when
comparing systems. Case and punctuation quality are deliberately not measured.

For a zero-length normalized reference, `status` is `empty_reference`. The rate is
0 only if the hypothesis is also empty; otherwise it is JSON `null` because division
by zero is undefined. The insertion error count is still reported. Empty-reference
items need separate review and must not disappear from an aggregate report.

`timing.speech_coverage` is the fraction of reference speech seconds intersected by
the union of hypothesis segment spans. Overlapping segments are merged before
measurement, so duplicated timing cannot inflate the score. The report also gives
covered and missed reference speech seconds and hypothesis seconds outside the
reference speech. A final segment near the end of a long file cannot stand in for
the omitted middle. Conversely, an excessively broad segment can cover the whole
reference while containing wrong words: inspect extra seconds and lexical scores
together. Timing coverage measures overlap, not word alignment, transcription
accuracy, decoder completion, or story quality.

If either side lacks timing, coverage is `null` with status `unavailable`. An
explicit empty hypothesis segment array represents zero recognized speech and gives
zero coverage against a nonempty speech reference. With no reference speech, timing
status is `empty_reference`, coverage is `null`, and any hypothesis speech is
reported outside the reference. Text-only segments can be evaluated lexically;
mixed timed/untimed segment rows are rejected rather than silently undercounted.

## Test fixtures versus measured quality

The automated tests are synthetic scorer checks. They cover matching and corrupted
English, Hebrew, Arabic, and CJK text, opening-only versus complete transcripts,
empty references, Unicode normalization, interval overlaps, and read-only CLI
behavior. Passing them is **not evidence of real ASR accuracy**, language detection
quality, full-audio decoding, or good editing decisions.

To measure an ASR change, retain a consented set of actual recordings and independent
human transcripts. Include short and long recordings, early/middle/late speech,
silence, different speakers and accents, background noise, and the languages you
intend to support. Save the model/version, settings, source identity, reference
revision, and per-recording reports for each run. For corpus WER/CER, sum errors and
reference units before dividing; do not average clip rates. Keep empty references
and unavailable timing counts visible. Inspect errors rather than assuming one
fixed threshold has the same meaning across languages and recording conditions.

## Human story review

Score the final edit separately from transcription. Reviewers should watch the full
source and the edit, record examples and timecodes, and use the same 1–5 scale
(1 = seriously flawed, 3 = usable with revision, 5 = strong) for each criterion:

| Criterion | Evidence to check |
| --- | --- |
| Meaning and factual fidelity | Cuts preserve qualifications, negation, speaker intent, and factual claims. |
| Context and continuity | Necessary setup survives; references and transitions remain understandable. |
| Story structure | The edit has a clear opening, relevant development, and a supported ending. |
| Source coverage | Later important material is considered; selection is justified by the brief. |
| Pacing and completeness | Pauses/cuts feel intentional; sentences and ideas end naturally. |
| Captions and presentation | Names, terminology, language, timing, framing, and audio remain clear. |

Have reviewers note any meaning-changing cut as a separate failure regardless of
the average score. Compare edits against the same brief; a short highlight and a
full-length cleanup have different coverage goals. Neither WER/CER nor interval
coverage can substitute for this review.

# Edit quality evaluation

`scripts/evaluate_edit.py` scores a CUTROOM edit against what a person decided
while watching the original recording. It is offline and read-only: it reads two
JSON files, prints a JSON report, and never renders, transcribes or uploads.

Use it to build a small **evaluation set** of your own real recordings (for
example five gameplay sessions and five talking-head Shorts) and re-run it after
every Director, Clips board or long-form change, so quality is measured instead
of guessed.

> **בעברית בקצרה:** בוחרים כמה הקלטות אמיתיות, צופים בכל אחת פעם אחת ורושמים
> בקובץ JSON מה חייב להישאר, מה חייב לצאת, איפה הרגעים הכי טובים ואיפה מתחילים
> פרקים. אחרי כל שינוי בעורך מריצים את הסט ומקבלים ציון לכל הקלטה ועבר/נכשל.

## 1. Write a reference for one recording

Times are seconds on the **original recording** (source A), exactly as you hear
them when playing the file. Every field is optional; score only what you marked.

```json
{
  "must_keep": [{"start": 12.0, "end": 41.5, "label": "the clutch"}],
  "must_cut": [{"start": 300.0, "end": 420.0, "label": "lobby wait"}],
  "highlights": [{"start": 610.0, "end": 640.0}],
  "chapters": [0, 185.0, 902.5],
  "target_duration": 600,
  "clip_length": 30
}
```

- `must_keep`: moments the edit must not lose (story beats, payoffs).
- `must_cut`: dead time the edit should remove (menus, loading, AFK).
- `highlights`: the moments you would post as Shorts. Compared with the Clips board.
- `chapters`: where you would start YouTube chapters (seconds, or `{"source_start": s}`).
- `target_duration`: the length you asked the Director for.
- `clip_length`: Clips board length to compare with (15, 30, 45, 60 or 90).

## 2. Score one project

Build the edit in CUTROOM as usual, then point the script at the project file
(`data/projects/<id>/project.json`):

```powershell
.venv\Scripts\python.exe scripts/evaluate_edit.py reference.json data\projects\project_123\project.json
```

| Score | Meaning | Better |
| --- | --- | --- |
| `must_keep_recall` | Share of must-keep seconds still in the edit | higher |
| `must_cut_leak` | Share of must-cut seconds that survived | lower |
| `duration_error` | Distance from `target_duration`, as a fraction | lower |
| `mid_word_cut_rate` | Cut boundaries that split a spoken word (needs word timings) | lower |
| `highlight_hit_rate` | Your highlights found on the Clips board | higher |
| `board_precision` | Clips board moments that match one of your highlights | higher |
| `chapter_mean_error_seconds` | Average distance from your chapter starts to the draft's | lower |

## 3. Run the whole set

Keep references and project copies together and list them in a manifest:

```json
{
  "thresholds": {"must_keep_recall": 0.9, "must_cut_leak": 0.2, "highlight_hit_rate": 0.5},
  "cases": [
    {"name": "valorant-ranked-01", "reference": "valorant-01.reference.json", "project": "valorant-01.project.json"},
    {"name": "talking-short-03", "reference": "talk-03.reference.json", "project": "talk-03.project.json"}
  ]
}
```

```powershell
.venv\Scripts\python.exe scripts/evaluate_edit.py --suite evaluation\suite.json
```

The report has one row per case (with `passed` and the failed limits) and a
summary with the mean of each score. Exit code 0 means every case passed, 1 means
a threshold failed, 2 means an input file is invalid. Default limits are
`must_keep_recall ≥ 0.9`, `must_cut_leak ≤ 0.2`, `highlight_hit_rate ≥ 0.5` and
`mid_word_cut_rate ≤ 0.1`; a manifest can override them.

Recordings and project files are private. Keep the evaluation folder outside the
repository, or add it to `.gitignore`.

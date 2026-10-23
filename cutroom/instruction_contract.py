"""Conservative request bookkeeping, separate from Story's semantic proof.

This is deliberately a small recognizer, not a natural-language verifier. The
verbatim request always remains authoritative. Recognized controls can expose a
provable conflict; everything else remains visible and explicitly unverified.
"""
from __future__ import annotations

import copy
import hashlib
import math
import re
from typing import Any

from .cache_keys import stable_fingerprint
from .story_budget import StoryBudgetError


INSTRUCTION_CONTRACT_VERSION = "instruction-contract-2026-10-23-v7.request-review"
MAX_INSTRUCTION_CHARACTERS = 8000
MAX_REQUIREMENT_ROWS = 64
MAX_EVIDENCE_REFERENCES = 8
MAX_EVIDENCE_TEXT_CHARACTERS = 512
_CHRONOLOGICAL_GOALS = {"short", "podcast", "youtube", "clean"}

_QUALIFIED = re.compile(
    r"\b(?:if|or|when|provided|assuming|depending|preferably|ideally|approximately|roughly|around|unless|minimum|maximum|at most|at least|up to)\b"
    r"|\b(?:אם|או|כאשר|בתנאי|לפחות|מינימום|מקסימום)\b|לכל היותר|במידה ש|במידת האפשר|רצוי|בערך|עדיף", re.I,
)
_UNIT = r"(?P<unit>seconds?|secs?|s|minutes?|mins?|שניות|שנייה|שניה|דקות|דקה)\b"
_NUMBER = r"(?P<seconds>\d+(?:\.\d+)?)\s*[-–]?\s*"
_DURATION_PREFIXES = (
    r"(?:please\s+)?(?:make|create|produce|deliver|edit|cut)\s+(?:me\s+)?(?:an?\s+)?(?:it\s+)?(?:exactly\s+)?",
    r"(?:the\s+)?(?:target(?:\s+duration)?|duration)\s*(?:(?:is|of)\s+|[:=]\s*)?(?:exactly\s+)?",
    r"(?:please\s+)?(?:make|create|edit|cut)\s+(?:an?\s+)?(?:short|video|clip|podcast)\s+(?:of|for|lasting|that is)\s+",
    r"(?:i\s+(?:want|need))\s+(?:an?\s+)?",
    r"(?:נא\s+)?(?:צור|צרי|תיצור|תיצרי|עשה|עשי|תעשה|ערוך|ערכי|תערוך|הכן|הכיני)\s+(?:לי\s+)?(?:(?:סרטון|קליפ|שורט|פודקאסט)\s+)?(?:(?:של|באורך)\s+)?",
    r"(?:אני רוצה|אני צריך|אני צריכה)\s+(?:(?:סרטון|קליפ|שורט|פודקאסט)\s+)?(?:(?:של|באורך)\s+)?",
    r"(?:משך|אורך|אורך היעד|משך היעד)\s*[:=]?\s*",
)
_DURATIONS = [re.compile(r"^" + prefix + _NUMBER + _UNIT, re.I) for prefix in _DURATION_PREFIXES]
# A bounded imperative grammar: numbers in dialogue, negations, alternatives,
# conditions and quoted examples do not become a duration command. A stated
# interval remains an interval even when introduced with "aim for".
_RANGE_PREFIX = (
    r"(?:(?:please\s+)?(?:aim\s+for|target(?:\s+duration)?\s*(?:is|of|:|=)?|"
    r"(?:make|create|produce|deliver|edit|cut)\s+(?:me\s+)?(?:an?\s+)?(?:it\s+)?"
    r"(?:(?:short|video|clip|podcast)\s+(?:of|for|lasting|that\s+is)\s+)?|"
    r"(?:duration|length)\s*(?:is|of|:|=)?)\s*|"
    r"(?:בבקשה\s+)?(?:כוון|שאף)\s+(?:לאורך\s+של\s+|ל[־-]?\s*)|"
    r"(?:בבקשה\s+)?(?:צור|תיצור|הכן|ערוך|תעשה)\s+(?:לי\s+)?"
    r"(?:(?:סרטון|קליפ|שורט|פודקאסט)\s+)?(?:(?:באורך|של)\s+)?|"
    r"(?:משך|אורך|משך\s+הסרטון|אורך\s+הסרטון)\s*[:=]?\s*)"
)
_DURATION_RANGE = re.compile(
    r"^" + _RANGE_PREFIX + r"(?:between\s+|בין\s+)?"
    r"(?P<minimum>\d+(?:\.\d+)?)\s*(?:[-–—־]|to\b|and\b|עד\b|ל[־-]?)\s*"
    r"(?P<maximum>\d+(?:\.\d+)?)\s*[-־]?\s*"
    r"(?P<unit>seconds?|secs?|s|minutes?|mins?|שניות|שנייה|שניה|דקות|דקה)\b", re.I,
)
_CHRONOLOGY = re.compile(
    r"(?:please\s+)?(?:keep|preserve|maintain)\s+(?:the\s+)?(?:original\s+)?"
    r"(?:chronology|chronological(?:\s+source)?\s+order|source\s+order)"
    r"|(?:שמור|שמרי|שמרו)\s+(?:על\s+)?(?:הסדר הכרונולוגי|סדר המקור|הכרונולוגיה)", re.I,
)
_REORDER = re.compile(
    r"^(?:please\s+)?(?:(?:start|begin|open)\s+with\s+(?:the\s+)?(?:ending|final\s+scene|last\s+(?:scene|segment|passage))\b"
    r"|(?:move|put|place)\s+(?:the\s+)?(?:last|final|ending)\s+(?:scene|segment|passage|first|at\s+the\s+(?:start|beginning))\b.*(?:first|before|start|beginning))"
    r"|^(?:נא\s+)?(?:(?:התחל|התחילי|פתח|פתחי)\s+עם\s+(?:הסוף|הקטע האחרון|הסצנה האחרונה)"
    r"|(?:העבר|העבירי|שים|שימי)\s+(?:את\s+)?(?:הקטע האחרון|הסצנה האחרונה|הסוף)\s+(?:להתחלה|לפני))", re.I,
)
_UNSUPPORTED = re.compile(
    r"^(?:please\s+)?(?P<action>add\s+(?:background\s+)?music|generate\s+(?:new\s+|missing\s+)?(?:footage|video|scenes)"
    r"|upload\s+(?:it\s+|this\s+|the\s+(?:video|clip)\s+)?to\s+(?:youtube|instagram|tiktok)"
    r"|translate\s+(?:the\s+)?spoken\s+(?:audio|words))\b"
    r"|^(?:נא\s+)?(?P<he_action>(?:הוסף|הוסיפי|תוסיף|תוסיפי)\s+(?:מוזיקה|מוסיקה)"
    r"|(?:צור|צרי|תיצור)\s+(?:וידאו|סצנות|צילומים)\s+חדשים"
    r"|(?:העלה|העלי|תעלה)\s+(?:את\s+)?(?:הסרטון\s+)?ל(?:יוטיוב|אינסטגרם|טיקטוק))", re.I,
)

# Passage count and approximate duration are different controls. In particular,
# "one passage, about a minute" still explicitly requests one source passage.
_PASSAGE_MODIFIER = r"(?:coherent|self[- ]contained|stand[- ]alone|continuous|contiguous|complete|interesting|clear|source)"
_SINGLE_PASSAGE = re.compile(
    r"^(?:please\s+)?(?:choose|select|pick|find)\s+(?:(?:exactly|only)\s+)?"
    r"(?:one|1|(?:a\s+)?single)\s+"
    + rf"(?:{_PASSAGE_MODIFIER}(?:\s*,\s*|\s+and\s+|\s+))*"
    + r"(?:segment|passage|clip)\b"
    r"|^(?:בבקשה\s+)?(?:בחר|בחרי|בחרו|מצא|מצאי|מצאו)\s+(?:רק\s+)?"
    r"(?:קטע|מקטע|קליפ|רצף)\s+(?:(?:מקור|מעניין|ברור|עצמאי|שלם|רציף|קוהרנטי)\s+)*(?:אחד|1)\b",
    re.I,
)
_PASSAGE_UNCERTAIN = re.compile(
    r"\b(?:if|or|when|provided|assuming|depending|unless|maybe|perhaps|preferably|ideally|would|could|should|"
    r"consider|hypothetical|hypothetically|example|minimum|maximum|at most|at least|up to|not necessarily)\b"
    r"|(?:^|\s)(?:אם|או|כאשר|בתנאי|אולי|אפשר|ניתן|הייתי|נניח|לדוגמה|למשל|רצוי|עדיף|כדאי|ייתכן|לפחות|מינימום|מקסימום)(?=\s|[,.!?;:]|$)"
    r"|במידה\s+ש|במידת\s+האפשר|לכל\s+היותר|לא\s+בהכרח",
    re.I,
)
_PASSAGE_COUNT_NEGATED = re.compile(
    r"\b(?:not|never|don't|do not)\s+(?:(?:choose|select|pick|find|use)\b|(?:one|single)\b)"
    r"|(?:^|\s)(?:אל|לא)\s+(?:תבחר|תבחרי|תבחרו|בחר|לבחור|בחרי|תמצא|תמצאי|תמצאו|מצא|רק\s+קטע|קטע\s+אחד)\b",
    re.I,
)
_PASSAGE_DISTRIBUTIVE = re.compile(
    r"\b(?:each|every|per)\b|(?:^|\s)(?:מכל|לכל|בכל)(?=\s|$)", re.I,
)
_PASSAGE_MULTIPLE = re.compile(
    r"\b(?:montage|compilation|mash[- ]?up|highlight\s+reel)\b"
    r"|\b(?:(?:two|three|four|five|six|seven|eight|nine|ten|multiple|several|many|[2-9]\d*|1\d+)\s+"
    r"(?:(?:independent|unrelated|separate|distinct)\s+)?|(?:independent|unrelated|separate|distinct)\s+)"
    r"(?:moments|passages|segments|clips|ideas|topics|events)\b"
    r"|(?:^|\s)(?:מונטאז|אוסף\s+קטעים|לקט\s+קטעים)"
    r"|(?:^|\s)(?:שני|שתי|שלושה|שלוש|ארבעה|ארבע|כמה|מספר|[2-9]\d*|1\d+)\s+"
    r"(?:רגעים|קטעים|מקטעים|רעיונות|נושאים|אירועים)\b"
    r"|(?:^|\s)(?:רגעים|קטעים|מקטעים|רעיונות|נושאים|אירועים)\s+"
    r"(?:נפרדים|עצמאיים|שונים|בלתי\s+קשורים)\b",
    re.I,
)
_CLIP_NOUN = re.compile(r"\bclip\b|(?:^|\s)קליפ(?=\s|$)", re.I)
_SEMANTIC_UNIT_CUE = re.compile(
    r"\b(?:coherent|self[- ]contained|stand[- ]alone)\b|\b(?:one|single)\s+(?:idea|thought|topic)\b"
    r"|(?:^|\s)(?:עצמאי|קוהרנטי)(?=\s|[,.!?;:]|$)|רעיון\s+(?:אחד|יחיד)\b", re.I,
)
_CONTINUITY_OPPOSITION = re.compile(
    r"\bnot\s+(?:uncut|continuous|contiguous|uninterrupted)\b"
    r"|(?:אבל|אך)\s+לא\s+(?:רציף|ללא\s+חיתוכים)\b", re.I,
)
_SOURCE_CONTINUITY = re.compile(
    r"^(?:please\s+)?(?:choose|select|pick|find|use|keep|preserve)\s+"
    r"(?:(?:one|a|an|a single|the|single|exactly one)\s+)?"
    r"(?:continuous|contiguous|uninterrupted|uncut)\s+(?:source\s+)?(?:passage|segment|take)\b"
    r"|^(?:please\s+)?(?:choose|select|pick|find|use|keep|preserve)\s+"
    r"(?:(?:one|a|an|a single|the|single|exactly one)\s+)?"
    r"(?:continuous|contiguous|uninterrupted|uncut)\s+(?:source\s+)?clip\b"
    r"|^(?:please\s+)?(?:choose|select|pick|find|use|keep|preserve)\s+"
    r"(?:(?:one|a|an|a single|the|single|exactly one)\s+)?"
    r"(?:short|video|clip|passage|segment|take)\s+(?:without|with no)\s+(?:any\s+)?(?:internal\s+)?cuts\b"
    r"|^(?:please\s+)?(?:keep|preserve|use)\s+(?:the\s+)?(?:selected\s+)?source\s+"
    r"(?:passage|segment|clip|take|footage)\s+(?:continuous|contiguous|uninterrupted|uncut)\b"
    r"|^(?:please\s+)?(?:keep|preserve|use)\s+(?:the\s+)?(?:selected\s+)?source\s+"
    r"(?:passage|segment|clip|take|footage)[^.!?;\n]*?\b(?:without|with no)\s+(?:any\s+)?(?:internal\s+)?cuts\b"
    r"|^(?:please\s+)?(?:do not|don't|never)\s+(?:cut|split)\s+"
    r"(?:(?:within|inside)\s+)?(?:the\s+)?(?:selected\s+)?source\s+(?:passage|segment|clip|take|footage)\b"
    r"|^(?:please\s+)?(?:do not|don't|never)\s+(?:make|add)\s+(?:any\s+)?(?:internal\s+)?cuts\s+"
    r"(?:within|inside|in)\s+(?:the\s+)?(?:selected\s+)?source\s+(?:passage|segment|clip|take|footage)\b"
    r"|^(?:בבקשה\s+)?(?:בחר|בחרי|בחרו|מצא|מצאי|מצאו)\s+(?:רק\s+)?"
    r"(?:קטע|מקטע|רצף|קליפ)\s+(?:מקור\s+)?(?:(?:אחד|1)\s+)?(?:רציף|ללא\s+חיתוכים)\b"
    r"|^(?:בבקשה\s+)?(?:השאר|השאירי|שמור|שמרי)\s+(?:את\s+|על\s+)?"
    r"(?:קטע|מקטע)\s+(?:המקור|מקור)\s+(?:רציף|ללא\s+(?:כל\s+)?חיתוכים|בלי\s+חיתוכים)\b"
    r"|^(?:בבקשה\s+)?(?:אל\s+(?:תחתוך|תחתכי|תחתכו)|אין\s+לחתוך)\s+"
    r"(?:(?:בתוך|את)\s+|ב)?(?:קטע|מקטע)\s+(?:המקור|מקור)\b"
    r"|^(?:בבקשה\s+)?אל\s+(?:תבצע|תבצעי|תבצעו)\s+חיתוכים\s+"
    r"(?:בתוך\s+|ב)(?:קטע|מקטע)\s+(?:המקור|מקור)\b",
    re.I,
)
_SOURCE_CUTS_ALLOWED = re.compile(
    r"^(?:please\s+)?(?:allow|permit)\s+(?:(?:internal|related|source)\s+)?cuts\b"
    r"|^(?:internal|related|source)\s+cuts\s+are\s+allowed\b"
    r"|^you\s+may\s+cut\s+(?:within|inside)\s+(?:the\s+)?source\s+(?:passage|segment|clip|take|footage)\b"
    r"|^(?:אפשר|מותר)\s+(?:לבצע\s+)?חיתוכים\s+(?:קשורים|פנימיים)\b"
    r"|^אפשר\s+לחתוך\s+בין\s+אמירות\s+קשורות\b",
    re.I,
)
_CUT_POLICY_CONJUNCTION = re.compile(
    r"\s*,?\s*\b(?:but|however|and)\s+|\s*,?\s*(?:אבל|אך)\s+", re.I,
)

# Output cardinality alone says nothing about source continuity. Only a direct
# cut policy attached to a singular output is recognized here. Full matching of
# each conjunction part excludes local scopes ("in the intro", "to the audio")
# rather than upgrading them to a global source constraint.
_OUTPUT_CUT_POLICY = re.compile(
    r"(?:(?:please\s+)?(?:make|create|produce|deliver|edit)(?:\s+me)?|i\s+(?:want|need))\s+"
    r"(?:exactly\s+)?(?:one|1|a(?:\s+single)?|single|the)\s+(?:video|short|clip|output)\s*,?\s+"
    r"(?P<en_policy>without|with\s+no|with)\s+(?:any\s+)?(?:internal\s+)?cuts"
    r"|(?:(?:בבקשה\s+)?(?:צור|צרי|צרו|תיצור|תיצרי|תיצרו|עשה|עשי|עשו|תעשה|תעשי|תעשו|"
    r"הכן|הכיני|הכינו|תכין|תכיני|תכינו|ערוך|ערכי|ערכו|תערוך|תערכי|תערכו)(?:\s+לי)?|"
    r"אני\s+(?:רוצה|צריך|צריכה))\s+(?:סרטון|וידאו|קליפ|סרט)\s+(?:(?:אחד|1|יחיד)\s+)?"
    r"(?P<he_policy>בלי|ללא|עם)\s+(?:כל\s+)?(?:חיתוכים|קאטים)(?:\s+פנימיים)?", re.I,
)


def _output_cut_policies(text: str):
    """None: legacy grammar; (None,None): new mixed scope is unparsed.

    Full matching applies to EVERY combined part, including old source-policy
    forms. A locally qualified old clause must not bypass this via the legacy
    prefix matcher merely because it precedes the new output clause.
    """
    parts = [part.strip().rstrip('.!?').rstrip() for part in _CUT_POLICY_CONJUNCTION.split(text)]
    matches = [_OUTPUT_CUT_POLICY.fullmatch(part) for part in parts]
    if not any(matches):
        return None
    required = permission = None
    for part,match in zip(parts,matches):
        if match:
            if str(match['en_policy'] or '').lower() == 'with' or match['he_policy'] == 'עם':
                permission = match
            else:
                required = match
        else:
            source = _SOURCE_CONTINUITY.fullmatch(part)
            allowed = _SOURCE_CUTS_ALLOWED.fullmatch(part)
            if not source and not allowed:
                return (None,None)  # unknown conjunct may narrow/negate shared scope
            required = source or required
            permission = allowed or permission
    return required,permission


def _unquoted(text: str) -> str:
    # Quoted examples and source dialogue are not imperative controls.
    return re.sub(r'''"[^"]*"|“[^”]*”|(?<!\w)'[\s\S]*?'(?!\w)''',
                  lambda match: " " * len(match[0]), text)


def _clauses(instruction: str) -> list[tuple[int, int, str]]:
    result = []
    # Do not split conjunctions: a negation or qualification may govern both.
    for match in re.finditer(r"[^\n;]+", instruction):
        for sentence in re.finditer(r".+?(?:[.!?](?=\s+[A-Za-zא-ת]|$)|$)", match[0]):
            text = sentence[0]
            left = len(text) - len(text.lstrip())
            right = len(text.rstrip())
            if right > left:
                start = match.start() + sentence.start() + left
                result.append((start, start + right - left, text[left:right]))
    return result


def _explicit_control_clauses(instruction: Any) -> list[tuple[int, int, str]]:
    """Retain offsets while masking quoted or unresolved shared-scope controls.

    Conditions/list scope or unmatched quotations remain unknown. This does not
    interpret topic, coherence, quality, speaker identity or a generic one-video
    output request. The complete verbatim instruction remains authoritative.
    """
    if not isinstance(instruction, str) or len(instruction) > MAX_INSTRUCTION_CHARACTERS:
        return []
    apostrophes = re.findall(r"(?<!\w)'|'(?!\w)", instruction)
    if (instruction.count('"') % 2 or instruction.count("“") != instruction.count("”")
            or len(apostrophes) % 2 or instruction.count("`") % 2
            or len(re.findall(r"(?<!\w)״|״(?!\w)", instruction)) % 2
            or instruction.count("‘") != len(re.findall(r"’(?!\w)", instruction))):
        return []
    masked = _unquoted(instruction)
    masked = re.sub(r"`[^`]*`|‘[^’]*’|(?<!\w)״[^״]*״(?!\w)",
                    lambda match: " " * len(match[0]), masked)
    if re.search(r":\s*(?:\n|;)", masked):
        return []
    if re.search(r"(?im)^\s*(?:if (?:possible|needed|necessary)|when possible|for example|hypothetically|"
                 r"אם (?:אפשר|ניתן|צריך)|לדוגמה|למשל)\s*[:.;]?\s*\n", masked):
        return []
    clauses = _clauses(instruction)
    # The final overflow row is intentionally unparsed in the public contract.
    if len(clauses) > MAX_REQUIREMENT_ROWS:
        clauses = clauses[:MAX_REQUIREMENT_ROWS - 1]
    return [(start, end, masked[start:end].strip()) for start, end, _text in clauses]


def _single_passage_matches(instruction: Any) -> dict[int, str]:
    recognized = {}
    for start, _end, text in _explicit_control_clauses(instruction):
        match = _SINGLE_PASSAGE.search(text)
        if (match and not _PASSAGE_UNCERTAIN.search(text) and not _PASSAGE_COUNT_NEGATED.search(text)
                and not _PASSAGE_DISTRIBUTIVE.search(text) and not _PASSAGE_MULTIPLE.search(text)):
            # A generic clip can be an output containing several ideas. Only an
            # explicit semantic cue permits treating its count as an idea/unit.
            if _CLIP_NOUN.search(match[0]) and not _SEMANTIC_UNIT_CUE.search(text):
                continue
            recognized[start] = match[0]
    return recognized


def _source_continuity_matches(instruction: Any) -> dict[int, str]:
    permissions = _source_cuts_allowed_matches(instruction)
    recognized = {}
    for start, _end, text in _explicit_control_clauses(instruction):
        output = _output_cut_policies(text)
        if output is not None:
            if (output[0] and not _PASSAGE_UNCERTAIN.search(text) and not _PASSAGE_DISTRIBUTIVE.search(text)
                    and not _CONTINUITY_OPPOSITION.search(text)):
                recognized[start] = output[0][0]
            continue  # no legacy fallback for an unresolved mixed output policy
        match = _SOURCE_CONTINUITY.search(text)
        # An independently recognized permission (Hebrew "אפשר לחתוך...")
        # opposes the preceding continuity control; it does not condition it.
        # Conditions before the conjunction remain in scope and still reject.
        scope = _CUT_POLICY_CONJUNCTION.split(text)[0] if start in permissions else text
        if (match and not _PASSAGE_UNCERTAIN.search(scope) and not _PASSAGE_DISTRIBUTIVE.search(text)
                and not _CONTINUITY_OPPOSITION.search(text)):
            recognized[start] = match[0]
    return recognized


def _source_cuts_allowed_matches(instruction: Any) -> dict[int, str]:
    recognized = {}
    for start, _end, text in _explicit_control_clauses(instruction):
        output = _output_cut_policies(text)
        if output is not None:
            if output[1] and not _PASSAGE_UNCERTAIN.search(text) and not _PASSAGE_DISTRIBUTIVE.search(text):
                recognized[start] = output[1][0]  # permission only, never a required edit
            continue
        # Opposed cut policies can share one sentence. Inspect only direct
        # conjunction-led permission clauses, retaining the original span.
        parts = _CUT_POLICY_CONJUNCTION.split(text)
        for part in parts:
            match = _SOURCE_CUTS_ALLOWED.search(part)
            if (match and not _PASSAGE_UNCERTAIN.search(part[match.end():])
                    and not _PASSAGE_DISTRIBUTIVE.search(part)):
                recognized[start] = match[0]
                break
    return recognized


def single_source_passage_requested(brief: dict[str, Any]) -> bool:
    """Whether a narrow affirmative clause requests one semantic editorial unit.

    This API never requires consecutive source beats or forbids related cuts.
    Count/coherence and source continuity are separate controls. Neither a match
    nor a single output range proves meaning. The grammar is deliberately partial.
    """
    return isinstance(brief, dict) and bool(_single_passage_matches(brief.get("instruction")))


def single_output_requested(brief: dict[str, Any]) -> bool:
    """Recognize an output count only, never source continuity or meaning."""
    pattern = re.compile(r"^(?:please\s+)?(?:make|create|produce|deliver|edit|choose|select)\s+"
        r"(?:me\s+)?(?:one|1|a\s+single)\s+(?:short|video|clip|output)\b"
        r"|^(?:בבקשה\s+)?(?:צור|תיצור|הכן|ערוך|בחר)\s+(?:לי\s+)?"
        r"(?:סרטון|קליפ|שורט|תוצר)\s+(?:אחד|1)\b", re.I)
    return any(pattern.search(text) and not _PASSAGE_UNCERTAIN.search(text)
               and not _PASSAGE_DISTRIBUTIVE.search(text)
               for _start, _end, text in _explicit_control_clauses(brief.get("instruction")))


def explicit_source_continuity_requested(brief: dict[str, Any]) -> bool:
    """Recognize an explicit continuous-source or no-internal-cuts directive.

    One output, one Short, one idea, self-contained speech and whole utterances
    do not imply source continuity. Unknown/qualified wording stays unspecified.
    Conflicting explicit cut permission is exposed by build_instruction_contract.
    """
    return isinstance(brief, dict) and (brief.get("source_continuity") == "required"
                                      or bool(_source_continuity_matches(brief.get("instruction"))))


def _facets(text: str) -> list[str]:
    """Hints for review only. These labels never prove an interpretation."""
    patterns = {
        "topic": r"\b(?:about|topic|focus on|discuss)\b|בנושא|על הנושא|התמקד|התמקדי",
        "exclusion": r"\b(?:exclude|omit|without|don't include|do not include|remove)\b|אל תכלול|אל תכללי|ללא|בלי|הסר|הסירי",
        "negation_or_qualification": r"\b(?:not|never|unless|only|except|qualified|qualification)\b|\bdon't\b|(?:^|\s)(?:לא|אל|רק|אלא)(?:\s|$)|הסתייגות|סייג",
        "speaker": r"\b(?:speaker|speaking|says|said)\b|דובר|דוברת|אומר|אמר|אמרה",
        "ordering": r"\b(?:first|begin|start|open|chronolog|order|ending|last)\w*\b|כרונולוג|בהתחלה|בתחילה|התוצאה|הסוף|האחרון",
    }
    return [name for name, pattern in patterns.items() if re.search(pattern, text, re.I)]


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def build_instruction_contract(brief: dict[str, Any]) -> dict[str, Any]:
    """Record every clause and recognize only a bounded set of explicit controls.

    Unknown wording, topic coverage, identity, absence, negation and qualified
    claims require semantic review. A matching source string cannot verify them.
    """
    raw = brief.get("instruction")
    instruction = "" if raw is None else raw
    goal = str(brief.get("goal") or "short")
    target = _finite(brief.get("target_duration") or 60)
    contract: dict[str, Any] = {
        "version": INSTRUCTION_CONTRACT_VERSION,
        "instruction": instruction,
        "instruction_fingerprint": stable_fingerprint("editing-instruction", instruction),
        "understanding": "conservative_explicit_controls_only",
        "goal": goal, "scope": "request",
        "settings": {"target_duration": target, "duration_mode": str(brief.get("duration_mode") or "target"),
                     "source_order": "chronological" if goal in _CHRONOLOGICAL_GOALS else "unverified",
                     "source_continuity": "unspecified"},
        "selection_controls": {"source_continuity": "unspecified", "source_continuity_origin": "unspecified",
                               "origin": "unspecified"},
        "requirements": [], "issues": [], "verification_status": "not_requested",
    }

    def issue(code: str, reason: str, requirement: dict[str, Any] | None = None) -> None:
        contract["issues"].append({"code": code, "reason": reason, "blocking": True,
                                   "requirement_id": requirement["id"] if requirement else None})
        if requirement:
            requirement.update(status="not_fulfilled", reason=reason)

    if not isinstance(instruction, str):
        issue("invalid_instruction_type", "Editing instruction must be text.")
    elif len(instruction) > MAX_INSTRUCTION_CHARACTERS:
        issue("instruction_too_long", f"Editing instruction exceeds {MAX_INSTRUCTION_CHARACTERS} characters; it was not shortened or applied.")
    else:
        contract["character_count"] = len(instruction)
        single_passages = _single_passage_matches(instruction)
        continuity = _source_continuity_matches(instruction)
        cuts_allowed = _source_cuts_allowed_matches(instruction)
        if single_passages:
            contract["selection_controls"].update(single_source_passage=True, semantic_unit_count=1,
                                                  semantic_unit_scope="editorial_meaning",
                                                  semantic_unit_origin="explicit_user_instruction",
                                                  origin="explicit_user_instruction",
                                                  semantic_coherence_verification="unverified")
        if continuity:
            contract["selection_controls"].update(source_continuity="required", origin="explicit_user_instruction",
                                                  source_continuity_origin="explicit_user_instruction")
            contract["settings"]["source_continuity"] = "required"
        if cuts_allowed:
            contract["selection_controls"].update(related_source_cuts_allowed=True, origin="explicit_user_instruction")
        masked_instruction = _unquoted(instruction)
        # A list may share its preface's quotation, negation or condition. Do
        # not turn later lines into mandatory commands without parsing scope.
        shared_scope = bool(re.search(r":\s*(?:\n|;)", masked_instruction))
        shared_scope = shared_scope or instruction.count('"') % 2 == 1 or instruction.count('“') != instruction.count('”')
        clauses = _clauses(instruction)
        omitted_clause_count = max(0, len(clauses) - (MAX_REQUIREMENT_ROWS - 1)) if len(clauses) > MAX_REQUIREMENT_ROWS else 0
        if omitted_clause_count:
            remainder_start = clauses[MAX_REQUIREMENT_ROWS - 1][0]
            clauses = clauses[:MAX_REQUIREMENT_ROWS - 1] + [(remainder_start, len(instruction), instruction[remainder_start:])]
            contract["understanding_limit"] = {"explicit_rows": MAX_REQUIREMENT_ROWS - 1,
                                                "unparsed_remainder_clauses": omitted_clause_count}
        for index, (start, end, text) in enumerate(clauses):
            requirement = {"id": f"r{index + 1:03d}", "text": text, "instruction_start": start, "instruction_end": end,
                           "kind": "request", "facets": _facets(text), "status": "unverified",
                           "reason": "Custom instruction coverage has no independent semantic verification.",
                           "source_evidence": [], "recognized_controls": []}
            contract["requirements"].append(requirement)
            if omitted_clause_count and index == MAX_REQUIREMENT_ROWS - 1:
                requirement.update(kind="unparsed_remainder", reason=f"The remaining {omitted_clause_count} clauses are retained verbatim and require review; their requirements are unverified.")
                continue
            if start in single_passages:
                requirement["recognized_controls"].append({
                    "kind": "source_passage_count", "requested_count": 1, "mandatory": True,
                    "text": instruction[start:start + len(single_passages[start])],
                    "verification": "semantic_coherence_unverified",
                    "scope": "semantic_unit", "source_continuity": "unspecified",
                    "instruction_start": start, "instruction_end": start + len(single_passages[start]),
                })
            if start in continuity:
                requirement["recognized_controls"].append({
                    "kind": "source_continuity", "mandatory": True, "cut_policy": "no_internal_source_cuts",
                    "text": text, "instruction_start": start, "instruction_end": end,
                    "origin": "explicit_user_instruction", "verification": "source_continuity_unverified",
                })
            if start in cuts_allowed:
                requirement["recognized_controls"].append({
                    "kind": "source_cuts_allowed", "permission": True, "mandatory": False,
                    "text": text, "instruction_start": start, "instruction_end": end,
                    "origin": "explicit_user_instruction", "verification": "unverified",
                })
            control_text = masked_instruction[start:end].strip()
            qualified = shared_scope or bool(_QUALIFIED.search(control_text))
            if shared_scope:
                requirement["reason"] = "Shared negation, quotation or conditional scope requires review; no mandatory control was inferred."
            duration_range = _DURATION_RANGE.search(control_text)
            if duration_range:
                multiplier = 60 if duration_range["unit"].lower().startswith(("min", "דק")) else 1
                lower, upper = (_finite(duration_range[key]) for key in ("minimum", "maximum"))
                if lower is None or upper is None or not math.isfinite(lower * multiplier) or not math.isfinite(upper * multiplier):
                    issue("invalid_instruction_duration_range", "The requested duration range is not finite.", requirement)
                elif lower <= 0 or upper < lower:
                    if not qualified:
                        issue("invalid_instruction_duration_range", "The requested duration range must have positive, ordered bounds.", requirement)
                else:
                    requirement["recognized_controls"].append({
                        "kind": "duration_range", "minimum_seconds": lower * multiplier,
                        "maximum_seconds": upper * multiplier, "mandatory": not qualified,
                        "text": duration_range[0], "origin": "explicit_user_instruction",
                    })
                    remainder = control_text[duration_range.end():].strip(" .!?")
                    if re.fullmatch(r"(?:(?:long\s+)?(?:short|video|clip|podcast)|(?:סרטון|קליפ|שורט|פודקאסט))?", remainder, re.I):
                        requirement["kind"] = "duration_range"
            duration = (None if duration_range else
                        next((match for pattern in _DURATIONS if (match := pattern.search(control_text))), None))
            if duration:
                seconds = _finite(duration["seconds"])
                if seconds is None:
                    requirement["reason"] = "The requested duration is outside the supported numeric range and remains unverified."
                    continue
                seconds *= 60 if duration["unit"].lower().startswith(("min", "דק")) else 1
                if not math.isfinite(seconds):
                    requirement["reason"] = "The requested duration is outside the supported numeric range and remains unverified."
                    continue
                if re.match(r"\s*(?:longer|shorter|more|less|of)\b", control_text[duration.end():], re.I):
                    qualified = True
                control = {"kind": "duration", "requested_seconds": seconds, "mandatory": not qualified,
                           "text": duration[0]}
                requirement["recognized_controls"].append(control)
                remainder = control_text[duration.end():].strip(" .!?")
                if re.fullmatch(r"(?:(?:long\s+)?(?:short|video|clip|podcast)|(?:סרטון|קליפ|שורט|פודקאסט))?", remainder, re.I):
                    requirement["kind"] = "duration"
                if not qualified and target is not None and abs(seconds - target) > .05:
                    # A maximum permits a shorter request. An exact target has
                    # two competing values, so no precedence is guessed.
                    duration_mode = contract["settings"]["duration_mode"]
                    if duration_mode == "target" or seconds > target + .05:
                        issue("instruction_duration_conflict", f"The instruction requests {seconds:g}s while duration settings request {target:g}s ({duration_mode}); choose one duration.", requirement)
            if not qualified and _CHRONOLOGY.fullmatch(control_text.rstrip(" .!?")):
                requirement["kind"] = "chronology"
                requirement["recognized_controls"].append({"kind": "chronology", "mandatory": True})
            if not qualified and goal in _CHRONOLOGICAL_GOALS and _REORDER.search(control_text):
                issue("instruction_source_order_conflict", "The instruction explicitly moves ending source before earlier source, but this Story mode requires chronological source order.", requirement)
            unsupported = _UNSUPPORTED.search(control_text)
            if unsupported:
                requirement["recognized_controls"].append({"kind": "unsupported_action", "mandatory": not qualified,
                                                           "text": unsupported[0]})
                if not qualified:
                    issue("unsupported_instruction_action", "This automatic editing pass cannot perform the requested media generation, music sourcing, speech translation or publishing action.", requirement)
        ranges = [control for row in contract["requirements"] for control in row["recognized_controls"]
                  if control["kind"] == "duration_range" and control["mandatory"]]
        exact = [control["requested_seconds"] for row in contract["requirements"] for control in row["recognized_controls"]
                 if control["kind"] == "duration" and control["mandatory"]]
        if exact and max(exact) - min(exact) > .05:
            issue("instruction_duration_conflict", "Explicit exact duration requirements disagree.")
        if ranges:
            lower = max(row["minimum_seconds"] for row in ranges)
            upper = min(row["maximum_seconds"] for row in ranges)
            if contract["settings"]["duration_mode"] == "max" and target is not None:
                upper = min(upper, target)
            if upper < lower or any(value < lower - .05 or value > upper + .05 for value in exact):
                issue("instruction_duration_range_conflict", "Explicit duration requirements have no common allowed interval.")
            contract["duration_range"] = {"minimum_seconds": lower, "maximum_seconds": upper,
                                          "origin": "explicit_user_instruction", "source_controls": copy.deepcopy(ranges)}
        if continuity and cuts_allowed:
            contract["selection_controls"]["source_continuity"] = "conflict"
            contract["settings"]["source_continuity"] = "conflict"
            requirement = next(row for row in contract["requirements"]
                               if any(control["kind"] == "source_continuity" for control in row["recognized_controls"]))
            issue("instruction_source_continuity_conflict",
                  "The instruction both prohibits internal source cuts and explicitly permits them; choose one cut policy.",
                  requirement)
    # Reviewed controls are explicit user choices, separate from the verbatim
    # request and optional style preferences. Never erase a conflicting clause.
    count = brief.get("output_count", 1)
    contract["settings"]["output_count"] = count
    if type(count) is not int or count != 1:
        issue("unsupported_output_count", "This generation creates one main edit. Multiple finished outputs are not supported in this pass.")
    policy = brief.get("source_continuity", "unspecified")
    if policy not in ("unspecified", "required", "cuts_allowed"):
        issue("invalid_source_continuity", "Choose continuous source, cuts allowed, or follow the written request.")
    else:
        controls = contract["selection_controls"]
        if policy == "required":
            if controls.get("related_source_cuts_allowed"):
                issue("instruction_source_continuity_conflict", "The written request permits cuts but the reviewed control forbids them. Edit one before generation.")
                controls["source_continuity"] = "conflict"
            elif controls["source_continuity"] != "conflict":
                controls.update(source_continuity="required", source_continuity_origin="explicit_review_control")
        elif policy == "cuts_allowed":
            if controls["source_continuity"] in {"required", "conflict"}:
                issue("instruction_source_continuity_conflict", "The written request forbids cuts but the reviewed control allows them. Edit one before generation.")
                controls["source_continuity"] = "conflict"
            controls["related_source_cuts_allowed"] = True
        contract["settings"]["source_continuity"] = controls["source_continuity"]
        contract["review_controls"] = {"output_count": count, "source_continuity": policy,
                                       "origin": "explicit_review_control" if "output_count" in brief or "source_continuity" in brief else "default"}
    # Deliberately narrow direct cardinality/aspect commands. Quotes, negation,
    # conditional instructions and unknown wording remain unverified.
    for _start, _end, text in _explicit_control_clauses(instruction):
        if _PASSAGE_UNCERTAIN.search(text):
            continue
        ambiguous_continuity = re.fullmatch(
            r"(?:please\s+)?(?:make|create|produce|deliver|edit)\s+(?:one|1|a\s+single)\s+"
            r"(?:continuous|uninterrupted)\s+(?:video|clip|short)[.!?]?"
            r"|(?:בבקשה\s+)?(?:צור|תיצור|הכן|ערוך|תעשה)\s+(?:לי\s+)?"
            r"(?:סרטון|קליפ|שורט)\s+(?:אחד\s+רציף|רציף\s+אחד)[.!?]?", text, re.I)
        if ambiguous_continuity and policy == "unspecified" and not explicit_source_continuity_requested(brief):
            issue("ambiguous_source_continuity", "Continuous output can mean one finished video or uncut source footage. Choose continuous source or cuts allowed explicitly before generation.")
        multiple = re.match(r"^(?:please\s+)?(?:make|create|produce|deliver|edit)\s+(?:me\s+)?(?:two|three|four|five|several|multiple|[2-9]\d*|1\d+)\s+(?:videos|shorts|clips|outputs)\b|^(?:בבקשה\s+)?(?:צור|תיצור|הכן|ערוך|תעשה)\s+(?:לי\s+)?(?:שני|שתי|שלושה|שלוש|כמה|[2-9]\d*|1\d+)\s+(?:סרטונים|קליפים|שורטים|תוצרים)\b", text, re.I)
        if multiple:
            issue("unsupported_output_count", "The written request asks for multiple outputs; this generation supports one main edit. Edit the request before proceeding.")
        aspect = re.fullmatch(r"(?:use\s+(?:an?\s+)?(?:aspect\s+ratio\s+)?|aspect\s+ratio\s*[:=]?\s*|יחס\s+(?:תמונה\s+)?[:=]?\s*)(9:16|16:9|1:1|4:5)[.!?]?", text, re.I)
        if aspect and brief.get("aspect") and aspect[1] != brief["aspect"]:
            issue("instruction_aspect_conflict", "The written aspect ratio and output format disagree. Choose one before generation.")
    if "output_count" in brief and goal == "youtube" and brief.get("aspect", "16:9") != "16:9":
        issue("unsupported_goal_aspect", "The current YouTube generation uses 16:9. Choose that format or another editing goal.")
    if "output_count" in brief and goal != "short" and any(
            control["kind"] in {"duration", "duration_range"} and control.get("mandatory")
            for row in contract["requirements"] for control in row["recognized_controls"]):
        issue("unsupported_mode_duration", "Exact or ranged highlight lengths are enforced in Short/Reel mode. Choose that mode or remove the length command for whole-recording cleanup.")
    if contract["issues"]:
        contract["verification_status"] = "not_fulfilled"
    elif contract["requirements"] or policy == "required":
        contract["verification_status"] = "unverified"
    return contract


def assert_instruction_contract(brief: dict[str, Any]) -> dict[str, Any]:
    contract = build_instruction_contract(brief)
    if contract["issues"]:
        first = contract["issues"][0]
        raise StoryBudgetError(first["reason"] + " No new draft was applied; the existing edit was kept.",
                               {"kind": "instruction_contract", "reason": first["code"], "outcome": "constraint_conflict",
                                "applied_to_timeline": False, "instruction_contract": contract})
    return contract


def effective_duration_bounds(brief: dict[str, Any], source_duration: float | None = None) -> dict[str, Any]:
    """One numeric contract from the verbatim request and configured settings.

    An explicit interval overrides the derived 90% target tolerance. A recognized
    exact request stays exact; a configured maximum still limits the interval.
    Explicit minima never shrink merely because the source is too short. This
    proves only numeric bounds, not instruction completeness or semantic fit.
    """
    contract = assert_instruction_contract(brief)
    target = contract["settings"]["target_duration"]
    if target is None or target <= 0:
        raise StoryBudgetError("The duration setting must be finite and positive.",
                               {"reason": "invalid_duration_setting", "outcome": "constraint_conflict",
                                "applied_to_timeline": False})
    mode = contract["settings"]["duration_mode"]
    interval = contract.get("duration_range")
    exact = [control["requested_seconds"] for row in contract["requirements"] for control in row["recognized_controls"]
             if control["kind"] == "duration" and control["mandatory"]]
    if exact:
        lower = upper = exact[0]
        origin = "explicit_user_exact"
    elif interval:
        lower, upper = interval["minimum_seconds"], interval["maximum_seconds"]
        origin = "explicit_user_range"
    else:
        source = _finite(source_duration)
        lower = .9 * min(target, max(0., source)) if source is not None and mode == "target" else .9 * target if mode == "target" else 0.
        upper = target
        origin = "derived_target" if mode == "target" else "configured_max" if mode == "max" else "configured_style"
    return {"minimum_seconds": float(lower), "maximum_seconds": float(upper), "origin": origin,
            "explicit": bool(exact or interval), "configured_target_seconds": target,
            "configured_duration_mode": mode, "instruction_fingerprint": contract["instruction_fingerprint"]}


def evaluate_instruction_contract(
    contract: dict[str, Any], segments: list[dict[str, Any]], decision: dict[str, Any], *,
    semantic_verified: bool = False, output_duration: float | None = None,
    source_ranges: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Add canonical evidence without upgrading unverified semantic requirements.

    Only final timeline duration/order supplied by the caller can fulfill those
    mechanical requirements. Story-role approval is independent of custom intent.
    """
    report = copy.deepcopy(contract)
    report.update(scope="timeline" if source_ranges is not None else "selected_source",
                  story_semantics_verified=semantic_verified is True,
                  semantic_requirement_verification="not_implemented")
    keep = set(decision.get("keep_ids") or [])
    remove = set(decision.get("remove_ids") or [])
    def selected_rows():
        return (row for row in segments if str(row.get("id")) not in remove and (not keep or str(row.get("id")) in keep))

    def reference(row: dict[str, Any]) -> dict[str, Any] | None:
        if "id" not in row or _finite(row.get("start")) is None or _finite(row.get("end")) is None:
            return None
        identifier = str(row["id"])
        if len(identifier) > 160:
            return None
        result = {"segment_id": identifier, "start": row["start"], "end": row["end"]}
        text = str(row.get("text") or "")
        if len(text) <= MAX_EVIDENCE_TEXT_CHARACTERS:
            result["text"] = text
        else:
            # Never truncate a quotation in a way that can hide its negation.
            result.update(text_omitted=True, source_text_characters=len(text))
        return result

    evidence = []
    for row in selected_rows():
        ref = reference(row)
        if ref is not None:
            evidence.append(ref)
        if len(evidence) == MAX_EVIDENCE_REFERENCES:
            break
    order_valid, chronological, previous_end = bool(source_ranges), True, -math.inf
    range_seconds = 0.0
    order_excerpt: list[dict[str, float]] = []
    order_hash = hashlib.sha256()
    for row in source_ranges or []:
        start, end = _finite(row.get("start")), _finite(row.get("end"))
        if start is None or end is None or end <= start:
            order_valid = False
            continue
        chronological = chronological and start + .000001 >= previous_end
        previous_end = end
        range_seconds += end - start
        order_hash.update(f"{start!r}:{end!r};".encode("ascii"))
        if len(order_excerpt) < MAX_EVIDENCE_REFERENCES:
            order_excerpt.append({"start": start, "end": end})
    for requirement in report["requirements"]:
        if requirement["status"] == "not_fulfilled":
            continue
        if "speaker" in requirement["facets"] and not any(row.get("speaker") or row.get("speaker_id") for row in segments):
            requirement["reason"] = "Speaker identity is unavailable; transcript text does not establish who spoke."
        # Exact quoted text can identify candidates for human review. Preserve
        # whole utterances, including negation; presence/absence proves no claim.
        phrases = [match[0][1:-1] for match in re.finditer(r'"[^"\n]+"|“[^”\n]+”', requirement["text"])]
        candidates = []
        if phrases:
            for row in selected_rows():
                if any(phrase.casefold() in str(row.get("text") or "").casefold() for phrase in phrases):
                    ref = reference(row)
                    if ref is not None:
                        candidates.append(ref)
                if len(candidates) == MAX_EVIDENCE_REFERENCES:
                    break
        if candidates:
            requirement["candidate_evidence"] = [{**row, "basis": "lexical_candidate_not_semantic_proof"} for row in candidates[:8]]
        if requirement["kind"] in {"duration", "duration_range"} and output_duration is not None and order_valid and evidence:
            control = next((row for row in requirement["recognized_controls"]
                            if row["kind"] in {"duration", "duration_range"} and row["mandatory"]), None)
            actual = _finite(output_duration)
            if control is not None and actual is not None:
                if abs(actual - range_seconds) > .05:
                    requirement["reason"] = "Timeline duration metadata and source passage duration disagree; duration remains unverified."
                    continue
                lower, upper = ((control["minimum_seconds"], control["maximum_seconds"])
                                if control["kind"] == "duration_range" else
                                (control["requested_seconds"], control["requested_seconds"]))
                fulfilled = lower - .05 <= actual <= upper + .05
                requirement.update(status="fulfilled" if fulfilled else "not_fulfilled", source_evidence=evidence,
                                   reason=f"The assembled timeline is {actual:g}s; the instruction permits {lower:g}–{upper:g}s.",
                                   verification_basis={"kind": "assembled_timeline_duration", "seconds": actual})
        if requirement["kind"] == "chronology" and order_valid and evidence:
            requirement.update(status="fulfilled" if chronological else "not_fulfilled", source_evidence=evidence,
                               reason="Source passage order was checked against the assembled timeline.",
                               verification_basis={"kind": "assembled_source_order", "checked_range_count": len(source_ranges),
                                                   "source_ranges_fingerprint": order_hash.hexdigest()[:32],
                                                   "source_ranges_excerpt": order_excerpt})
    statuses = {row["status"] for row in report["requirements"]}
    report["verification_status"] = ("not_fulfilled" if report["issues"] or "not_fulfilled" in statuses else
                                     "unverified" if "unverified" in statuses else "fulfilled" if statuses else "not_requested")
    return report

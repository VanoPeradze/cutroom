"""Generated, text-only regression sources. No private transcript or media.

Fixed clocks exercise short rows, gaps, offsets and unfinished boundaries.
They are test geometry, not listening or editorial qualification evidence.
"""
from __future__ import annotations

import copy
import hashlib
import json


EN_CLOCK = [
    (0.,4.88),(5.16,10.06),(10.06,19.27),(19.42,22.94),(24.01,30.17),
    (30.17,35.45),(36.45,40.35),(40.51,44.17),(44.17,47.95),(48.,54.08),
    (54.08,60.01),(60.51,61.25),(62.,67.91),(67.91,68.19),(68.98,71.92),
    (72.,73.44),(73.68,74.84),(75.22,76.88),(77.26,78.48),(78.64,81.24),
    (81.4,85.56),(86.35,88.63),(89.09,93.45),(93.45,95.85),(96.,102.41),
    (102.41,106.92),(106.92,109.24),(109.24,112.58),(112.58,116.01),
    (116.01,116.29),(116.65,119.77),(119.77,119.97),(120.,127.52),
    (127.52,132.79),(132.79,137.39),(137.39,142.39),(142.39,142.91),
    (144.88,151.16),(151.16,157.06),(157.06,163.29),(163.29,167.72),
    (168.,173.54),(174.24,177.78),(177.98,179.96),
]
EN_TEXT = [
    "We tested two ways to repair a loose chair joint.",
    "First we measured how far the chair moved under the same load.",
    "The initial trial used a dry joint, and it slipped when we repeated the measurement.",
    "A repair experiment compares methods under the same conditions.",
    "The control keeps the wood, load and measuring tool unchanged.",
    "Changing only the adhesive lets us interpret the difference.",
    "We wrote down each measurement before making another change.",
    "That record prevents a later impression from replacing the result.",
    "It does not establish that every chair",
    "will behave the same way. Next we cleaned the joint.",
    "Both samples rested for the same amount of time.",
    "The first test failed.",
    "It failed because the dry surfaces could still move independently.",
    "Because the joint",
    "can move, stress remains concentrated at the edge instead of spreading out.",
    "That explains the failure.",
    "We changed one part.",
    "The next sample used adhesive.",
    "The clamp stayed fixed.",
    "After the same wait we repeated the load.",
    "This time the displacement was smaller in each repeated measurement.",
    "We kept the raw readings.",
    "One unusual reading remained in the record rather than being silently removed.",
    "It was marked for review.",
    "The conclusion is limited to these samples and this load.",
    "A stronger result would require more wood types and a larger trial.",
    "We did not run those tests.",
    "So the repair may help in this setting without proving universal strength.",
    "The measurement supports that narrow statement.",
    "Nothing more.",
    "There is a separate finishing question.",
    "A finish can change appearance.",
    "The second workshop compared two finishes under the same light.",
    "That process can produce a",
    "A different result was then checked with a ruler.",
    "The maker kept the test pieces beside each other.",
    "For comparison.",
    "The result was documented before anyone was told which finish was used.",
    "Observers described the color and also recorded their uncertainty.",
    "A preference does not establish durability or resistance to water.",
    "Those claims need separate measurements and a defined test.",
    "The workshop therefore reported appearance as an observation, not a strength claim.",
    "More testing remains necessary before those other claims are supported.",
    "The next result depends on",
]
HE_CLOCK = [
    (767.45,773.17),(773.51,775.39),(775.55,777.25),(778.2,781.26),
    (781.82,785.44),(786.12,787.18),(787.4,789.18),(789.52,790.24),
    (791.22,793.46),(794.36,799.38),(799.94,802.08),(802.42,802.98),
    (804.3,808.11),(809.4,812.61),(812.91,814.23),(815.1,821.94),
    (822.19,824.23),(825.54,826.82),(827.,829.78),(829.94,830.88),(830.96,833.88),
]
HE_TEXT = [
    "רגע, נבדוק את החיבור.", "הנגר הביא כיסא לסדנה.", "החיבור זז תחת עומס.",
    "בדקנו שתי שיטות באותם תנאים.", "זו הייתה בדיקה מוגבלת. ואז תיאור שלא הושלם",
    "שלא הופיע במדידה הקודמת.", "לכן השארנו את הקריאה המקורית.", "לא תיקנו אותה בדיעבד.",
    "רק סימנו שיש כאן אי ודאות.", "בדוגמה השנייה השתמשנו בדבק ובאותו מהדק.",
    "ההמתנה הייתה באותו אורך.", "גם העומס נשאר זהה.", "החיבור זז פחות בשלוש מדידות חוזרות.",
    "זה תומך במסקנה מצומצמת על הדוגמה הזאת.", "זה אינו מוכיח שכל כיסא יתנהג כך.",
    "למסקנה רחבה נדרשים חומרים נוספים ומדידות נוספות.", "רשמנו את המגבלה בדוח.",
    "השארנו גם תוצאות חריגות.", "כך אפשר לבדוק את ההסבר מול הנתונים.",
    "זו מסקנה זמנית.", "הניסוי הבא יבחן עומסים אחרים.",
]


def source_fixture(language="en"):
    clock, texts = (EN_CLOCK, EN_TEXT) if language == "en" else (HE_CLOCK, HE_TEXT)
    segments = []
    for index, ((start, end), text) in enumerate(zip(clock, texts), 1):
        tokens = text.split()
        words = [{"start": round(start + (end-start)*i/len(tokens), 6),
                  "end": round(start + (end-start)*(i+1)/len(tokens), 6), "word": word}
                 for i, word in enumerate(tokens)]
        segments.append({"id": f"s{index:04d}", "start": start, "end": end, "text": text,
                         "normalized": text.lower(), "words": words, "avg_logprob": -.1,
                         "no_speech_prob": .01})
    return {"segments": segments, "brief": {"goal": "short", "language": language,
            "target_duration": 60., "duration_mode": "target", "instruction":
            "Make one video. Aim for 45-60 seconds. Preserve meaning." if language == "en"
            else "צור סרטון אחד. אורך 45-60 שניות. שמור על המשמעות."},
            "fixture_kind": "generated_text_only", "auditory_correctness_verified": False}


def source_bytes(language="en"):
    return (json.dumps(source_fixture(language), ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode("utf-8")


def source_sha256(language="en"):
    return hashlib.sha256(source_bytes(language)).hexdigest()


def understanding_reply(payload):
    """Well-formed synthetic planning replies with payload-owned references."""
    from cutroom import intelligence as story
    system = payload["messages"][0]["content"]
    data = json.loads(payload["messages"][-1]["content"])
    if "first pass" in system:
        return {"chapters": [{"id": chapter["id"], "title": "Workshop trial", "summary": "Synthetic test summary.",
                "role": "development", "key_points": ["Only the recorded trial is supported."],
                "key_beat_ids": [chapter["beats"][0]["id"]], "depends_on": [], "unresolved_questions": []}
                for chapter in data["chapters"]]}
    if "global story analyst" in system:
        chapters = data["chapters"]
        return {"premise": "A limited workshop trial.", "audience_takeaway": "Keep the measured limit.",
                "story_arc": [{"chapter_id": c["id"], "function": "development", "why_it_matters": "Original context."} for c in chapters],
                "must_keep_chapter_ids": [], "optional_chapter_ids": [], "dependency_pairs": []}
    if "Story Producer" in system:
        return {"narrative": "One synthetic account, still requiring source and semantic review.",
                "slots": [{"purpose": story.SINGLE_PASSAGE_PURPOSE,
                           "chapter_ids": [row["chapter_id"] for row in data["outline"]["story_arc"]],
                           "required_context_chapter_ids": [], "desired_seconds": 60., "reason": "Synthetic planning fixture."}]}
    raise AssertionError("Fixture received an unexpected model stage")


def source_context(language="en"):
    from cutroom import intelligence as story
    source = source_fixture(language)
    rows = story.enrich_segments(copy.deepcopy(source["segments"]), language)
    units = story.build_story_beats(rows, language, target_seconds=60.)
    chapters = story.build_story_chapters(units)
    plan = {"narrative": "Synthetic limited trial.", "slots": [{"purpose": story.SINGLE_PASSAGE_PURPOSE,
            "chapter_ids": [c["id"] for c in chapters], "required_context_chapter_ids": [],
            "desired_seconds": 60., "reason": "Synthetic planning fixture."}]}
    return source, rows, units, chapters, plan

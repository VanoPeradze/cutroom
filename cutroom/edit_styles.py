from __future__ import annotations

import copy
from typing import Any, Mapping


class UnknownEditStyle(ValueError):
    pass


_BASE_AUDIO = {
    "preset": "clean",
    "silence_action": "shorten",
    "silence_min_seconds": 0.75,
    "silence_keep_seconds": 0.30,
    "max_remove_ratio": 0.28,
    "quiet_action": "boost",
    "quiet_gain_db": 3.0,
    "loud_action": "lower",
    "loud_gain_db": -3.0,
    "normalize": True,
    "target_lufs": -16.0,
}


def _selection_policy(
    *,
    moment_unit: str,
    hook: str,
    chronology: str,
    pre_roll_seconds: float,
    post_roll_seconds: float,
    energy: float,
    speech: float,
    visual_change: float,
    continuity: float,
    protect_action_span: bool = False,
    story_structure: tuple[str, ...] = (),
    max_moments: int | None = None,
) -> dict[str, Any]:
    """Return a machine-readable editorial policy shared by every execution path."""
    return {
        "moment_unit": moment_unit,
        "hook": hook,
        "chronology": chronology,
        "pre_roll_seconds": pre_roll_seconds,
        "post_roll_seconds": post_roll_seconds,
        "weights": {
            "energy": energy,
            "speech": speech,
            "visual_change": visual_change,
            "continuity": continuity,
        },
        "protect_action_span": protect_action_span,
        "story_structure": list(story_structure),
        "max_moments": max_moments,
    }


def _framing_policy(*, default_layout: str, second_source_layout: str = "pip") -> dict[str, Any]:
    """Keep camera detection advisory and prevent one source being duplicated as a camera."""
    return {
        "default_layout": default_layout,
        "second_source_layout": second_source_layout,
        "camera_detection": "suggest_only",
        "embedded_camera_requires_confirmation": True,
        "allow_single_source_duplication": False,
    }


EDIT_STYLES: tuple[dict[str, Any], ...] = (
    {
        "id": "smart",
        "category": "general",
        "name": {"he": "CUTROOM חכם", "en": "CUTROOM Smart"},
        "description": {
            "he": "בחירה מאוזנת שמתאימה לרוב הסרטונים.",
            "en": "A balanced starting point for most videos.",
        },
        "badge": {"he": "מומלץ", "en": "Recommended"},
        "resource_tier": "balanced",
        "features": ["context", "clean_audio", "auto_reframe"],
        "defaults": {
            "goal": "short",
            "aspect": "9:16",
            "pace": "balanced",
            "target_duration": 60,
            "layout": "auto",
            "quality": "balanced",
            "resolution": "1080",
            "auto_reframe": True,
            "captions": False,
            "burn_captions": True,
            "performance_mode": "auto",
            "audio_cleanup": _BASE_AUDIO,
        },
        "selection_policy": _selection_policy(
            moment_unit="complete_moment",
            hook="clear_promise",
            chronology="story_coherent",
            pre_roll_seconds=3.0,
            post_roll_seconds=2.0,
            energy=0.20,
            speech=0.30,
            visual_change=0.15,
            continuity=0.35,
        ),
        "framing_policy": _framing_policy(default_layout="auto"),
        "guidance": (
            "Create a coherent, natural edit. Preserve the context required to understand each moment, "
            "start with a clear promise or result, remove repetition and dead time, and finish a complete idea."
        ),
    },
    {
        "id": "stream_highlights",
        "category": "streamer",
        "name": {"he": "היילייטים מהסטרים", "en": "Stream Highlights"},
        "description": {
            "he": "רגעים חזקים ומהירים עם תגובות, הישגים והפתעות.",
            "en": "Fast standout moments, reactions, wins and surprises.",
        },
        "badge": {"he": "מהיר", "en": "Fast"},
        "resource_tier": "lite",
        "features": ["high_energy", "reactions", "vertical", "captions"],
        "defaults": {
            "goal": "short",
            "aspect": "9:16",
            "pace": "dynamic",
            "target_duration": 60,
            "layout": "A",
            "quality": "fast",
            "resolution": "720",
            "auto_reframe": True,
            "captions": True,
            "burn_captions": True,
            "performance_mode": "auto",
            "audio_cleanup": {
                **_BASE_AUDIO,
                "preset": "tight",
                "silence_min_seconds": 0.45,
                "silence_keep_seconds": 0.16,
                "max_remove_ratio": 0.42,
                "quiet_gain_db": 4.0,
                "loud_gain_db": -4.0,
            },
        },
        "selection_policy": _selection_policy(
            moment_unit="standout_moment",
            hook="peak_preview",
            chronology="within_moment",
            pre_roll_seconds=3.0,
            post_roll_seconds=2.5,
            energy=0.35,
            speech=0.20,
            visual_change=0.25,
            continuity=0.20,
            protect_action_span=True,
            story_structure=("brief setup", "decisive action", "result and immediate reaction"),
            max_moments=3,
        ),
        "framing_policy": _framing_policy(default_layout="A"),
        "guidance": (
            "Edit this as streamer highlights. Prioritize high-energy reactions, clear wins or failures, "
            "surprises and moments that work quickly. Keep the minimum setup needed before each payoff; "
            "avoid disconnected quotes and routine low-energy gameplay."
        ),
    },
    {
        "id": "competitive_clutch",
        "category": "streamer",
        "name": {"he": "קלאץ׳ תחרותי", "en": "Competitive Clutch"},
        "description": {
            "he": "שומר קרב שלם — הכנה קצרה, מהלך מכריע והתגובה שאחריו.",
            "en": "Keeps a complete fight: brief setup, decisive play and the reaction after it.",
        },
        "badge": {"he": "FPS", "en": "FPS"},
        "resource_tier": "lite",
        "features": ["competitive", "gameplay", "action_continuity", "vertical"],
        "defaults": {
            "goal": "short",
            "aspect": "9:16",
            "pace": "dynamic",
            "target_duration": 60,
            "layout": "A",
            "quality": "fast",
            "resolution": "720",
            "auto_reframe": False,
            "captions": True,
            "burn_captions": True,
            "performance_mode": "auto",
            "audio_cleanup": {
                **_BASE_AUDIO,
                "preset": "tight",
                "silence_min_seconds": 0.45,
                "silence_keep_seconds": 0.16,
                "max_remove_ratio": 0.35,
                "quiet_gain_db": 4.0,
                "loud_gain_db": -4.0,
                "target_lufs": -15.0,
            },
        },
        "selection_policy": _selection_policy(
            moment_unit="engagement",
            hook="peak_preview",
            chronology="strict_within_engagement",
            pre_roll_seconds=6.0,
            post_roll_seconds=3.0,
            energy=0.35,
            speech=0.10,
            visual_change=0.25,
            continuity=0.30,
            protect_action_span=True,
            story_structure=("stakes and setup", "one continuous engagement", "result and immediate reaction"),
            max_moments=1,
        ),
        "framing_policy": _framing_policy(default_layout="A"),
        "guidance": (
            "Edit this as a competitive clutch. Select one complete engagement with enough setup to read "
            "the stakes, keep combat continuous, and retain the result plus the immediate reaction. Avoid "
            "menus, queues and routine gameplay; never interrupt or reorder action inside the engagement."
        ),
    },
    {
        "id": "reaction_burst",
        "category": "streamer",
        "name": {"he": "תגובה בשיא", "en": "Reaction Burst"},
        "description": {
            "he": "בונה חשיפה קצרה ושומר את רגע השיא והתגובה המלאה.",
            "en": "Builds a short reveal and preserves the peak plus the complete reaction.",
        },
        "badge": {"he": "אנרגיה", "en": "Energy"},
        "resource_tier": "balanced",
        "features": ["reaction", "high_energy", "complete_payoff", "captions"],
        "defaults": {
            "goal": "short",
            "aspect": "9:16",
            "pace": "dynamic",
            "target_duration": 45,
            "layout": "A",
            "quality": "fast",
            "resolution": "720",
            "auto_reframe": False,
            "captions": True,
            "burn_captions": True,
            "performance_mode": "balanced",
            "audio_cleanup": {
                **_BASE_AUDIO,
                "preset": "tight",
                "silence_min_seconds": 0.45,
                "silence_keep_seconds": 0.16,
                "max_remove_ratio": 0.42,
                "quiet_gain_db": 4.0,
                "loud_gain_db": -4.0,
                "target_lufs": -15.0,
            },
        },
        "selection_policy": _selection_policy(
            moment_unit="reveal_and_reaction",
            hook="peak_preview",
            chronology="setup_then_payoff",
            pre_roll_seconds=4.0,
            post_roll_seconds=3.0,
            energy=0.38,
            speech=0.28,
            visual_change=0.22,
            continuity=0.12,
            protect_action_span=True,
            story_structure=("context for the reveal", "reveal", "complete reaction"),
            max_moments=1,
        ),
        "framing_policy": _framing_policy(default_layout="A", second_source_layout="pip"),
        "guidance": (
            "Edit this as a high-energy reaction. A very short peak preview may hook the viewer, but the "
            "main sequence must include the reveal, enough setup to understand it, and the full immediate "
            "reaction. Prefer genuine energy changes and avoid isolated shouting without a payoff."
        ),
    },
    {
        "id": "funny_moments",
        "category": "streamer",
        "name": {"he": "רגעים מצחיקים", "en": "Funny Moments"},
        "description": {
            "he": "בונה setup קצר ושומר את התגובה והפאנץ׳ בשלמותם.",
            "en": "Keeps the setup, reaction and punchline together.",
        },
        "badge": {"he": "בידורי", "en": "Comedy"},
        "resource_tier": "balanced",
        "features": ["comedy", "reaction", "complete_payoff", "captions"],
        "defaults": {
            "goal": "short",
            "aspect": "9:16",
            "pace": "dynamic",
            "target_duration": 90,
            "layout": "A",
            "quality": "fast",
            "resolution": "720",
            "auto_reframe": True,
            "captions": True,
            "burn_captions": True,
            "performance_mode": "balanced",
            "audio_cleanup": {
                **_BASE_AUDIO,
                "preset": "tight",
                "silence_min_seconds": 0.50,
                "silence_keep_seconds": 0.18,
                "max_remove_ratio": 0.38,
            },
        },
        "selection_policy": _selection_policy(
            moment_unit="setup_payoff_reaction",
            hook="payoff_tease",
            chronology="setup_then_payoff",
            pre_roll_seconds=6.0,
            post_roll_seconds=4.0,
            energy=0.25,
            speech=0.30,
            visual_change=0.15,
            continuity=0.30,
            protect_action_span=True,
            story_structure=("setup", "escalation", "punchline and full reaction"),
            max_moments=3,
        ),
        "framing_policy": _framing_policy(default_layout="A"),
        "guidance": (
            "Edit this as a funny streamer moment. Preserve the setup that makes the joke understandable, "
            "the full reaction and the payoff. Favor banter, mistakes, surprise and escalating moments. "
            "Do not cut so tightly that timing or context is lost."
        ),
    },
    {
        "id": "stream_commentary",
        "category": "streamer",
        "name": {"he": "פרשנות חזקה", "en": "Strong Commentary"},
        "description": {
            "he": "מעדיף דעות, הסברים ותגובות שאפשר להבין גם כקטע עצמאי.",
            "en": "Prioritizes opinions, explanations and reactions that stand on their own.",
        },
        "badge": {"he": "דיבור", "en": "Commentary"},
        "resource_tier": "lite",
        "features": ["commentary", "opinions", "complete_ideas", "vertical"],
        "defaults": {
            "goal": "short",
            "aspect": "9:16",
            "pace": "dynamic",
            "target_duration": 60,
            "layout": "A",
            "quality": "fast",
            "resolution": "720",
            "auto_reframe": True,
            "captions": True,
            "burn_captions": True,
            "performance_mode": "auto",
            "audio_cleanup": {
                **_BASE_AUDIO,
                "preset": "clean",
                "silence_min_seconds": 0.60,
                "silence_keep_seconds": 0.22,
                "max_remove_ratio": 0.34,
            },
        },
        "selection_policy": _selection_policy(
            moment_unit="complete_thought",
            hook="clear_claim",
            chronology="premise_then_conclusion",
            pre_roll_seconds=2.0,
            post_roll_seconds=2.0,
            energy=0.10,
            speech=0.55,
            visual_change=0.05,
            continuity=0.30,
            story_structure=("question or clear premise", "explanation and supporting example", "answer or conclusion"),
            max_moments=1,
        ),
        "framing_policy": _framing_policy(default_layout="A", second_source_layout="pip"),
        "guidance": (
            "Edit this as strong streamer commentary. Prioritize clear opinions, explanations, useful insights "
            "and reactions that can stand on their own. Preserve the premise before a conclusion and remove "
            "routine chatter, repeated wording and long stretches without a complete idea."
        ),
    },
    {
        "id": "stream_story",
        "category": "streamer",
        "name": {"he": "סיפור מהסטרים", "en": "Stream Story Recap"},
        "description": {
            "he": "תקציר עם התחלה, התפתחות ותוצאה — גם מתוך סטרים ארוך.",
            "en": "A beginning-to-payoff recap selected from a long stream.",
        },
        "badge": {"he": "Storyline", "en": "Storyline"},
        "resource_tier": "balanced",
        "features": ["story_arc", "context", "long_source", "payoff"],
        "defaults": {
            "goal": "short",
            "aspect": "9:16",
            "pace": "balanced",
            "target_duration": 180,
            "layout": "A",
            "quality": "balanced",
            "resolution": "1080",
            "auto_reframe": True,
            "captions": True,
            "burn_captions": True,
            "performance_mode": "balanced",
            "audio_cleanup": _BASE_AUDIO,
        },
        "selection_policy": _selection_policy(
            moment_unit="story_beat",
            hook="payoff_tease",
            chronology="story_arc",
            pre_roll_seconds=4.0,
            post_roll_seconds=3.0,
            energy=0.10,
            speech=0.35,
            visual_change=0.10,
            continuity=0.45,
            story_structure=("premise", "essential setup", "development and evidence", "actual result"),
        ),
        "framing_policy": _framing_policy(default_layout="A"),
        "guidance": (
            "Build a complete streamer story recap from anywhere in the recording. Establish the premise, "
            "retain essential setup, show meaningful escalation or proof, and end on the actual result or "
            "conclusion. Coherence is more important than the number of highlights."
        ),
    },
    {
        "id": "chill_story",
        "category": "streamer",
        "name": {"he": "סיפור רגוע", "en": "Chill Story"},
        "description": {
            "he": "שומר אנקדוטה שלמה, נשימות וקצב דיבור טבעי בלי עריכת יתר.",
            "en": "Keeps a complete anecdote, breathing room and natural speech without over-editing.",
        },
        "badge": {"he": "טבעי", "en": "Natural"},
        "resource_tier": "balanced",
        "features": ["story", "natural_pacing", "complete_ideas", "captions"],
        "defaults": {
            "goal": "short",
            "aspect": "9:16",
            "pace": "gentle",
            "target_duration": 180,
            "layout": "A",
            "quality": "balanced",
            "resolution": "1080",
            "auto_reframe": False,
            "captions": True,
            "burn_captions": True,
            "performance_mode": "balanced",
            "audio_cleanup": {
                **_BASE_AUDIO,
                "preset": "natural",
                "silence_min_seconds": 1.20,
                "silence_keep_seconds": 0.48,
                "max_remove_ratio": 0.16,
                "quiet_gain_db": 2.0,
                "loud_gain_db": -2.0,
                "normalize": False,
            },
        },
        "selection_policy": _selection_policy(
            moment_unit="complete_anecdote",
            hook="natural_open",
            chronology="strict",
            pre_roll_seconds=4.0,
            post_roll_seconds=4.0,
            energy=0.05,
            speech=0.40,
            visual_change=0.05,
            continuity=0.50,
            story_structure=("context", "one complete anecdote", "reflection and natural ending"),
            max_moments=1,
        ),
        "framing_policy": _framing_policy(default_layout="A"),
        "guidance": (
            "Edit this as a relaxed story. Preserve one complete anecdote in chronological order, including "
            "the context, reflection and natural pauses that make it feel human. Remove only clear repetition "
            "and dead air; avoid aggressive jumps, meme pacing and unnecessary visual switching."
        ),
    },
    {
        "id": "clean_vod",
        "category": "streamer",
        "name": {"he": "VOD נקי", "en": "Clean VOD"},
        "description": {
            "he": "שומר את הסטרים המלא ומנקה בעיקר שקט במסלול החסכוני ביותר.",
            "en": "Preserves the full stream and mainly cleans silence with the lightest workflow.",
        },
        "badge": {"he": "חסכוני", "en": "Low resource"},
        "resource_tier": "lite",
        "features": ["full_length", "audio_first", "low_resource", "widescreen"],
        "defaults": {
            "goal": "youtube",
            "aspect": "16:9",
            "pace": "gentle",
            "target_duration": 600,
            "layout": "A",
            "quality": "fast",
            "resolution": "720",
            "auto_reframe": False,
            "captions": False,
            "burn_captions": False,
            "performance_mode": "lite",
            "audio_cleanup": {
                **_BASE_AUDIO,
                "preset": "natural",
                "silence_min_seconds": 1.20,
                "silence_keep_seconds": 0.48,
                "max_remove_ratio": 0.16,
                "quiet_gain_db": 2.0,
                "loud_gain_db": -2.0,
                "normalize": False,
            },
        },
        "selection_policy": _selection_policy(
            moment_unit="source_sequence",
            hook="none",
            chronology="strict",
            pre_roll_seconds=0.0,
            post_roll_seconds=0.0,
            energy=0.0,
            speech=0.0,
            visual_change=0.0,
            continuity=1.0,
            protect_action_span=True,
        ),
        "framing_policy": _framing_policy(default_layout="A", second_source_layout="A"),
        "guidance": (
            "Preserve the original VOD structure. Remove only clearly measured dead air and unsafe audio "
            "extremes; do not reorder or semantically shorten the recording."
        ),
    },
)


_STYLE_BY_ID = {style["id"]: style for style in EDIT_STYLES}


def get_edit_style(style_id: Any, *, strict: bool = False) -> dict[str, Any]:
    normalized = str(style_id or "smart").strip().lower()
    style = _STYLE_BY_ID.get(normalized)
    if style is None:
        if strict:
            raise UnknownEditStyle(normalized)
        style = _STYLE_BY_ID["smart"]
    return copy.deepcopy(style)


def public_edit_styles() -> list[dict[str, Any]]:
    return [
        {
            key: copy.deepcopy(style[key])
            for key in (
                "id",
                "category",
                "name",
                "description",
                "badge",
                "resource_tier",
                "features",
                "defaults",
                "selection_policy",
                "framing_policy",
            )
        }
        for style in EDIT_STYLES
    ]


def enrich_brief_with_style(brief: Mapping[str, Any]) -> dict[str, Any]:
    output = copy.deepcopy(dict(brief))
    style = get_edit_style(output.get("edit_style"))
    output["edit_style"] = style["id"]
    guidance = style["guidance"]
    structure = style["selection_policy"].get("story_structure") or []
    if structure:
        guidance += " Required progression: " + " -> ".join(structure) + "."
        guidance += (
            " Select complete source passages with the required context. A shorter complete moment is better "
            "than filling the duration with unrelated clips. Do not invent missing action, dialogue or outcomes."
        )
    max_moments = style["selection_policy"].get("max_moments")
    if max_moments:
        guidance += f" Keep at most {max_moments} distinct complete moment(s); the duration is a ceiling, not a quota."
    output["style_profile"] = {
        "id": style["id"],
        "features": list(style["features"]),
        "selection_policy": copy.deepcopy(style["selection_policy"]),
        "framing_policy": copy.deepcopy(style["framing_policy"]),
        "guidance": guidance,
    }
    return output

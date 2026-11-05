from __future__ import annotations

import copy
import re
from typing import Any, Mapping

from .story_budget import StoryPlanningError
from .instruction_contract import single_source_passage_requested, explicit_source_continuity_requested


class UnknownEditStyle(ValueError):
    pass


STORY_INTENT_VERSION = "explicit-story-intent-2026-10-20-v2"
_STRUCTURE_DIRECTIVE = re.compile(
    r"^(?:please\s+)?(?:(?:use|follow|require)\s+(?:this\s+|the\s+)?(?:story\s+|narrative\s+)?(?:structure|progression|roles)"
    r"|(?:required\s+)?(?:story\s+|narrative\s+)?(?:structure|roles))\s*:\s*(?P<roles>.+?)\s*[.!]?\s*$"
    r"|^(?:השתמש|השתמשי)\s+במבנה(?:\s+הבא)?\s*:\s*(?P<he_roles>.+?)\s*[.!]?\s*$"
    r"|^(?:מבנה(?:\s+נדרש)?|תפקידי\s+סיפור\s+נדרשים)\s*:\s*(?P<he_label_roles>.+?)\s*[.!]?\s*$", re.I,
)
_SINGLE_ROLE_DIRECTIVE = re.compile(
    r"^(?:please\s+)?(?:require|include|keep|must include)\s+(?:an?\s+|the\s+)?"
    r"(?P<role>punchline|setup|premise|context|evidence|explanation|payoff|result|reaction|conclusion)\s*[.!]?\s*$"
    r"|^(?:כלול|כללי|שמור|שמרי)\s+(?:את\s+)?(?P<he_role>פאנץ[׳']?|פואנטה|הקשר|הסבר|תוצאה|תגובה|מסקנה)\s*[.!]?\s*$", re.I,
)
_UNCERTAIN_ROLE_SCOPE = re.compile(
    r"\b(?:no|not|never|don't|exclude|omit|if|unless|when|or|would|could|might|hypothetical|hypothetically|example|imagine|suppose|without|optional|optionally|prefer|preferred|preferably|maybe)\b"
    r"|\b(?:אל|לא|אם|או|בלי|ללא|למשל|דוגמה|נניח|אולי|אפשר)\b", re.I,
)
_ROLE_HINT = re.compile(
    r"\b(?:structure|story roles|narrative|punchline|setup|premise|context|evidence|explanation|payoff|result|reaction|conclusion)\b"
    r"|מבנה|פאנץ|פואנטה|הקשר|הסבר|תוצאה|תגובה|מסקנה", re.I)
_SHARED_ROLE_SCOPE = re.compile(
    r"(?im)^\s*(?:optional|optionally|example|hypothetical|suppose|if|unless|when|prefer|אולי|למשל|דוגמה|נניח|אם)\b[^\n.!?]*[:;\n]"
)
_POSTFIX_ROLE_SCOPE = re.compile(r"^\s*;?\s*(?:(?:this|that|it)\s+is|(?:these|both|all)\s+are)\s+optional\b", re.I)
_EXPLICIT_ROLE_LABELS = {
    "hook", "setup", "premise", "context", "evidence", "explanation", "payoff", "result", "reaction",
    "conclusion", "punchline", "development", "answer", "ending", "essential setup",
    "development and evidence", "actual result", "punchline and full reaction",
    "\u05e4\u05d0\u05e0\u05e5", "\u05e4\u05d0\u05e0\u05e5\u05f3", "\u05e4\u05d0\u05e0\u05e5'",
    "\u05e4\u05d5\u05d0\u05e0\u05d8\u05d4", "\u05d4\u05e7\u05e9\u05e8", "\u05d4\u05e1\u05d1\u05e8",
    "\u05ea\u05d5\u05e6\u05d0\u05d4", "\u05ea\u05d2\u05d5\u05d1\u05d4", "\u05de\u05e1\u05e7\u05e0\u05d4",
}


def _explicit_story_intent(instruction: Any) -> dict[str, Any]:
    """Recognize a small explicit role grammar; never infer roles from a style.

    The original request remains authoritative. Unrecognized, negated, quoted or
    hypothetical structure requests stay visible and unverified, not positive
    role requirements. This does not verify arbitrary instruction semantics.
    """
    intent: dict[str, Any] = {"version": STORY_INTENT_VERSION, "required_roles": [], "ordered_role_groups": [],
                              "role_requirements": [], "order_requirements": [], "unverified_structure_requests": []}
    if not isinstance(instruction, str) or not instruction.strip() or len(instruction) > 8000:
        return intent
    # Mask quoted dialogue across lines before considering individual clauses.
    masked = re.sub(r'''"[^"]*"|“[^”]*”|‘[^’]*’|(?<!\w)'[\s\S]*?'(?!\w)''',
                    lambda match: " " * len(match[0]), instruction)
    unmatched_quote = (instruction.count('"') % 2 == 1 or instruction.count('“') != instruction.count('”')
                       or bool(re.search(r"(?<!\w)'", masked))
                       or '‘' in masked)
    scope_starts = [match.start() for match in _SHARED_ROLE_SCOPE.finditer(masked)
                    if not re.match(r"\s*(?:optional|optionally|prefer)\s+\S", match[0], re.I)
                    or _ROLE_HINT.search(match[0])]
    for match in re.finditer(r":\s*(?:\n|;)", masked):
        prefix = masked[masked.rfind("\n", 0, match.start()) + 1:match.start()]
        if _ROLE_HINT.search(prefix):
            scope_starts.append(match.start())
    # Only a bounded single-line directive is understood mechanically. Split
    # trailing prose into its own clause instead of swallowing it as a role.
    whole_structure = _STRUCTURE_DIRECTIVE.fullmatch(masked.strip())
    if whole_structure and re.search(r"[;\n]|[.!?]\s+", masked.strip().rstrip('.!?')):
        whole_structure = None
    spans = [(0, len(instruction))] if whole_structure else [match.span() for match in re.finditer(r"[^\n;]+", instruction)]
    for start, end in spans:
        clauses = [(start, end)] if whole_structure else [
            (start + clause.start(), start + clause.end())
            for clause in re.finditer(r".+?(?:[.!?](?=\s+[A-Za-zא-ת]|$)|$)", instruction[start:end])]
        for left, right in clauses:
            text = instruction[left:right].strip()
            control = masked[left:right].strip()
            uncertain = (unmatched_quote or (any(position <= left for position in scope_starts) and not whole_structure)
                         or control.endswith('?') or bool(_UNCERTAIN_ROLE_SCOPE.search(control))
                         or bool(_POSTFIX_ROLE_SCOPE.match(masked[right:])))
            structure = _STRUCTURE_DIRECTIVE.fullmatch(control) if not uncertain else None
            single = _SINGLE_ROLE_DIRECTIVE.fullmatch(control) if not uncertain else None
            role_text = next((value for value in structure.groupdict().values() if value is not None), "") if structure else ""
            roles = re.split(r"\s*(?:->|→|,)\s*", role_text) if structure else [next(value for value in single.groupdict().values() if value is not None)] if single else []
            roles = [role.strip().rstrip(".!?") for role in roles]
            if roles and (any(role.casefold() not in _EXPLICIT_ROLE_LABELS for role in roles)
                          or len(roles) != len({role.casefold() for role in roles}) or len(roles) > 64):
                roles = []
                uncertain = True
            if len(set(intent["required_roles"]) | set(roles)) > 64:
                roles = []
                uncertain = True
            if not roles:
                if _ROLE_HINT.search(text):
                    intent["unverified_structure_requests"].append({"text": text, "instruction_start": left,
                        "instruction_end": right, "status": "unverified",
                        "reason": "Narrative structure scope or wording is outside the supported explicit grammar; the original request still requires review."})
                continue
            for role in roles:
                if role.casefold() in {existing.casefold() for existing in intent["required_roles"]}:
                    continue
                intent["required_roles"].append(role)
                intent["role_requirements"].append({"purpose": role, "origin": "user", "authority": "required",
                    "instruction_start": left, "instruction_end": right, "instruction_text": instruction[left:right]})
            if structure and len(roles) > 1 and re.search(r"->|\u2192|\b(?:structure|progression)\s*:|\u05de\u05d1\u05e0\u05d4", control, re.I):
                canonical = {role.casefold(): role for role in intent["required_roles"]}
                group = [canonical[role.casefold()] for role in roles]
                if group not in intent["ordered_role_groups"]:
                    intent["ordered_role_groups"].append(group)
                    intent["order_requirements"].append({"roles": group, "origin": "user", "authority": "required",
                        "instruction_start": left, "instruction_end": right, "instruction_text": instruction[left:right]})
    _validate_story_role_orders(intent["required_roles"], intent["ordered_role_groups"])
    return intent


def required_story_roles(brief: Mapping[str, Any]) -> list[str]:
    """Only explicit user instruction can add required narrative template roles."""
    return _explicit_story_intent(brief.get("instruction"))["required_roles"]


def required_story_role_orders(brief: Mapping[str, Any]) -> list[list[str]]:
    return _explicit_story_intent(brief.get("instruction"))["ordered_role_groups"]


def _validate_story_role_orders(roles: list[str], groups: Any) -> list[list[str]]:
    if (not isinstance(groups, list) or len(groups) > 64 or any(
            not isinstance(group, list) or not 2 <= len(group) <= 64
            or any(not isinstance(role, str) or role not in roles for role in group)
            or len(group) != len(set(group)) for group in groups)):
        raise StoryPlanningError("The explicit story order is invalid; the existing edit was kept.",
            {"outcome": "constraint_conflict", "reason": "invalid_story_intent_contract", "applied_to_timeline": False})
    pending = {role: set() for role in roles}
    for group in groups:
        for before, after in zip(group, group[1:]):
            pending[after].add(before)
    while pending:
        ready = {role for role, predecessors in pending.items() if not predecessors}
        if not ready:
            raise StoryPlanningError("The requested story orders contradict each other; the existing edit was kept.",
                {"outcome": "constraint_conflict", "reason": "contradictory_story_role_order", "applied_to_timeline": False})
        pending = {role: predecessors - ready for role, predecessors in pending.items() if role not in ready}
    return copy.deepcopy(groups)


def required_story_role_orders_from_policy(policy: Mapping[str, Any]) -> list[list[str]]:
    return _validate_story_role_orders(required_story_roles_from_policy(policy), policy.get("required_story_role_orders", []))


def required_story_roles_from_policy(policy: Mapping[str, Any]) -> list[str]:
    """A versioned enriched policy carries explicit roles into Director guards."""
    if not any(key in policy for key in ("required_story_roles", "required_role_origin", "story_intent_version")):
        # Old style metadata is advisory, including saved unversioned briefs.
        return []
    roles = policy.get("required_story_roles")
    if (policy.get("story_intent_version") != STORY_INTENT_VERSION or policy.get("required_role_origin") != "user"
            or "required_story_role_orders" not in policy
            or not isinstance(roles, list) or len(roles) > 64
            or any(not isinstance(role, str) or not role.strip() or len(role) > 80 for role in roles)
            or len(roles) != len({role.casefold() for role in roles})):
        raise StoryPlanningError("The explicit story-role contract is invalid; the existing edit was kept.",
                                 {"outcome": "constraint_conflict", "reason": "invalid_story_intent_contract", "applied_to_timeline": False})
    _validate_story_role_orders(roles, policy["required_story_role_orders"])
    return list(roles)


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
    # Missing intent belongs to an older project: preserve its preset contract.
    target_mode = output.get("duration_mode") == "target" and output.get("goal", "short") == "short"
    policy = copy.deepcopy(style["selection_policy"])
    preferred_structure = policy.pop("story_structure", [])
    story_intent = _explicit_story_intent(output.get("instruction"))
    policy.update(preferred_structure=list(preferred_structure),
                  required_story_roles=list(story_intent["required_roles"]),
                  required_story_role_orders=copy.deepcopy(story_intent["ordered_role_groups"]),
                  required_role_origin="user", story_intent_version=STORY_INTENT_VERSION)
    policy["duration_mode"] = "target" if target_mode else "style"
    policy["preferred_max_moments"] = policy.get("max_moments")
    policy["max_moments"] = None
    policy["preserve_source_continuity"] = explicit_source_continuity_requested(output)
    guidance = style["guidance"]
    if preferred_structure:
        guidance += " Optional presentation progression, only when supported by source: " + " -> ".join(preferred_structure) + "."
        guidance += (
            " This style preference is not a required narrative role. Omit unsupported template roles rather than "
            "inventing action, dialogue, jokes or outcomes. Preserve complete source passages and their context."
        )
    if target_mode and single_source_passage_requested(output):
        guidance += (
            " The user requests one coherent self-contained idea near the target duration. "
            "Preserve complete source utterances and their context. Meaning-preserving cuts among related utterances are allowed unless explicitly forbidden. "
            "Do not assemble independent moments to fill time or invent template roles. Explicit user roles and their order still apply."
        )
    elif target_mode and not policy["preserve_source_continuity"]:
        guidance += (
            " Duration intent overrides the preset's single-moment count: assemble distinct relevant complete "
            "passages toward the requested approximate length, in source chronology. Preserve each passage's "
            "setup and payoff. Do not repeat footage or add irrelevant material to fill time; explain a shortfall."
        )
    max_moments = policy.get("preferred_max_moments")
    if policy["preserve_source_continuity"]:
        guidance += (" The original instruction explicitly requires continuous source footage without internal cuts. "
                     "Keep intervening source time and pauses; report duration conflicts instead of overriding this instruction.")
    if max_moments:
        guidance += (f" The style favors {max_moments} complete moment(s) as a presentation preference, not a maximum. "
                     "User instructions and source-supported complete passages take precedence; never discard required context to match the preset count.")
    output["style_profile"] = {
        "id": style["id"],
        "features": list(style["features"]),
        "selection_policy": policy,
        "framing_policy": copy.deepcopy(style["framing_policy"]),
        "guidance": guidance,
        "preferred_structure": list(preferred_structure),
    }
    output["story_contract"] = {**story_intent, "preferred_structure": [
        {"purpose": purpose, "origin": "style", "style_id": style["id"], "authority": "preference"}
        for purpose in preferred_structure]}
    return output

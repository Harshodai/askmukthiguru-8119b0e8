"""Config-driven teacher and shared-corpus registry.

Runtime routing, speaker allowlists, and ingestion attribution must not maintain
parallel hardcoded teacher lists. backend/config/gurus.yaml is authoritative.
If it cannot be loaded, teacher-specific attribution fails closed.
"""

from __future__ import annotations

import logging
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)
_CONFIG = Path(__file__).resolve().parents[1] / "config" / "gurus.yaml"


@lru_cache(maxsize=1)
def _registry_document() -> dict[str, Any]:
    try:
        data = yaml.safe_load(_CONFIG.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict) or not isinstance(data.get("gurus"), list):
            raise ValueError("gurus.yaml must contain a 'gurus' list")
        return data
    except (OSError, yaml.YAMLError, ValueError) as exc:
        logger.error(
            "guru_registry unavailable; registered-teacher attribution is disabled (%s)",
            type(exc).__name__,
        )
        return {}


@dataclass(frozen=True)
class Guru:
    id: str
    label: str
    pattern: re.Pattern
    attribution_tag: str
    rights_policy: str = "channel_owner_confirmed"
    attribution_policy: str = "direct_verbatim_quote"
    sources: tuple[dict[str, Any], ...] = ()
    voice_refs: tuple[dict[str, Any], ...] = ()
    allowed_surfaces: tuple[str, ...] = ("first_person_clip", "practice_guide", "wisdom_tip")
    aliases: tuple[str, ...] = ()


@lru_cache(maxsize=1)
def get_gurus() -> tuple[Guru, ...]:
    data = _registry_document()
    raw = data.get("gurus") or []
    gurus: list[Guru] = []
    for entry in raw:
        if not isinstance(entry, dict) or not entry.get("id") or not entry.get("label"):
            logger.warning("Ignoring invalid teacher entry in gurus.yaml")
            continue
        aliases = entry.get("aliases") or []
        if not isinstance(aliases, list) or any(not isinstance(alias, str) for alias in aliases):
            logger.warning("Ignoring invalid aliases for a teacher entry in gurus.yaml")
            continue
        try:
            pat = "|".join(f"(?:{alias})" for alias in aliases) or re.escape(str(entry["label"]))
            sources = tuple(dict(s) for s in (entry.get("sources") or []) if isinstance(s, dict))
            voice_refs = tuple(
                dict(v) for v in (entry.get("voice_refs") or []) if isinstance(v, dict)
            )
            allowed_surfaces = tuple(
                str(s).strip()
                for s in (
                    entry.get("allowed_surfaces")
                    or ["first_person_clip", "practice_guide", "wisdom_tip"]
                )
            )
            gurus.append(
                Guru(
                    id=str(entry["id"]).strip().lower(),
                    label=str(entry["label"]).strip(),
                    pattern=re.compile(rf"\b(?:{pat})\b", re.I),
                    attribution_tag=str(entry.get("attribution_tag") or f"teacher:{entry['id']}"),
                    rights_policy=str(entry.get("rights_policy") or "channel_owner_confirmed"),
                    attribution_policy=str(
                        entry.get("attribution_policy") or "direct_verbatim_quote"
                    ),
                    sources=sources,
                    voice_refs=voice_refs,
                    allowed_surfaces=allowed_surfaces,
                    aliases=tuple(str(a) for a in aliases),
                )
            )
        except re.error:
            logger.exception("Ignoring invalid alias regex for a teacher entry in gurus.yaml")
    return tuple(gurus)


def allowed_speaker_labels() -> frozenset[str]:
    return frozenset(g.label for g in get_gurus())


def label_for(guru_id: str | None) -> str | None:
    gid = (guru_id or "").strip().lower()
    return next((g.label for g in get_gurus() if g.id == gid or g.label.lower() == gid), None)


def attribution_tag_for(guru_id: str) -> str | None:
    gid = (guru_id or "").strip().lower()
    return next((g.attribution_tag for g in get_gurus() if g.id == gid), None)


def voice_teacher_labels() -> dict[str, str]:
    """Teacher IDs and shared-corpus IDs to display labels, derived from this registry."""
    teachers = {guru.id: guru.label for guru in get_gurus()}
    primary, shared_ids = shared_attribution()
    if shared_ids:
        shared_label = " and ".join(teachers[item] for item in shared_ids if item in teachers)
        if shared_label:
            teachers["_".join(shared_ids)] = shared_label
            if primary:
                teachers[primary] = shared_label
    for organization in _registry_document().get("organizations") or []:
        if not isinstance(organization, dict) or not organization.get("id"):
            continue
        org_id = str(organization["id"]).strip().lower()
        related = organization.get("attributed_teacher_ids") or []
        if isinstance(related, list):
            names = [
                teachers[str(item).lower()] for item in related if str(item).lower() in teachers
            ]
        else:
            names = []
        teachers[org_id] = " and ".join(dict.fromkeys(names)) or str(
            organization.get("label") or org_id
        )
    return teachers


def neutral_voice_id() -> str:
    """Configured shared teacher scope used when no single speaker is established."""
    primary, shared_ids = shared_attribution()
    if primary:
        return primary
    return "_".join(shared_ids) if shared_ids else "shared"


def requested_gurus(query: str) -> list[str]:
    """Ids of configured teachers named in text, in registry order."""
    text = unicodedata.normalize("NFKC", query or "")
    return [g.id for g in get_gurus() if g.pattern.search(text)]


# Unregistered external spiritual teachers, traditions, and non-corpus doctrines.
# Queries asking specifically about their teachings must never be answered with
# misattributed quotes from Sri Preethaji or Sri Krishnaji.
_UNREGISTERED_TEACHER_OR_TRADITION_PATTERNS = [
    r"\bthich\s+nhat\s+hanh\b",
    r"\bsadhguru\b|\bjaggi\s+vasudev\b|\bisha\s+(?:kriya|foundation|yoga)\b",
    r"\beckhart\s+tolle\b",
    r"\b(?:sri\s+sri\s+)?ravi\s+shankar\b|\bart\s+of\s+living\b|\bsudarshan\s+kriya\b",
    r"\bosho\b|\bbhagwan\s+(?:shree\s+)?rajneesh\b",
    r"\bramana\s+maharshi\b",
    r"\bnisargadatta(?:\s+maharaj)?\b",
    r"\b(?:jiddu\s+krishnamurti|j\.?\s*krishnamurti)\b",
    r"\badi\s+shankaracharya\b|\bshankaracharya\b|\badvaita\s+vedanta\b",
    r"\b(?:gautama\s+)?buddha\b|\bpali\s+canon\b|\bfour\s+noble\s+truths\b|\beightfold\s+path\b",
    r"\blord'?s\s+prayer\b",
    r"\b(?:ten\s+)?sefirot\b|\bkabbalah\b|\bzohar\b",
    r"\bmarcus\s+aurelius\b|\bmeditations\s+of\s+marcus\b",
    r"\bparamahansa\s+yogananda\b|\byogananda\b|\bself[\s-]realization\s+fellowship\b",
    r"\b(?:swami\s+)?vivekananda\b|\bramakrishna(?:\s+paramahamsa)?\b",
    r"\bswami\s+sivananda\b|\bneem\s+karoli\s+baba\b|\banandamayi\s+ma\b",
    r"\bmooji\b|\bpapaji\b|\bh\.?\s*w\.?\s*l\.?\s*poonja\b",
    r"\bmaharishi\s+mahesh\s+yogi\b|\btranscendental\s+meditation\b",
    r"\balan\s+watts\b|\bdeepak\s+chopra\b|\bbyron\s+katie\b|\bgurdjieff\b|\bouspensky\b|\bram\s+dass\b",
    r"\b(?:the\s+)?dalai\s+lama\b|\bzen\s+master\b",
]

_UNREGISTERED_TEACHER_RE = re.compile(
    "|".join(_UNREGISTERED_TEACHER_OR_TRADITION_PATTERNS),
    re.IGNORECASE,
)


def resolve_guru_id(value: str | None) -> str | None:
    """Resolve a configured teacher ID, label, or registered alias to its ID.

    Canonical IDs come from gurus.yaml. Unknown values deliberately return
    None so callers cannot treat an unregistered teacher filter as no filter.
    """
    candidate = unicodedata.normalize("NFKC", value or "").strip().lower()
    if not candidate:
        return None
    if candidate in {
        "preethaji_krishnaji",
        "krishnaji_preethaji",
        "preethaji-krishnaji",
        "krishnaji-preethaji",
    }:
        primary, _ = shared_attribution()
        return primary or "preethaji_krishnaji"
    for guru in get_gurus():
        slug_values = {
            guru.id.lower(),
            re.sub(r"[^a-z0-9]+", "-", guru.id.lower()).strip("-"),
            re.sub(r"[^a-z0-9]+", "-", guru.label.lower()).strip("-"),
            guru.label.lower(),
        }
        if candidate in slug_values:
            return guru.id
    normalized_alias = re.sub(r"[-_]+", " ", candidate)
    requested = requested_gurus(normalized_alias)
    if len(requested) == 1:
        return requested[0]
    for organization in _registry_document().get("organizations") or []:
        if not isinstance(organization, dict):
            continue
        org_id = str(organization.get("id") or "").strip().lower()
        org_label = str(organization.get("label") or "").strip().lower()
        org_aliases = organization.get("aliases") or []
        if candidate == org_id or candidate == org_label:
            return org_id or None
        if isinstance(org_aliases, list):
            try:
                if any(re.search(str(alias), normalized_alias, re.I) for alias in org_aliases):
                    return org_id or None
            except re.error:
                continue
    return None


def canonical_guru_id(value: str | None) -> str | None:
    """Resolve any raw teacher/guru identifier across stores to its canonical ID (DATA-13, GURU-013).

    Handles store vocabulary drift across chat payloads, v8/v10 schemas, and OKF:
      - 'sri-krishnaji', 'sri_krishnaji', 'krishnaji' -> 'krishnaji'
      - 'sri-preethaji', 'sri_preethaji', 'preethaji' -> 'preethaji'
      - 'preethaji_krishnaji', 'both', 'shared' -> 'preethaji_krishnaji'
      - 'ekam', 'oneworld academy' -> 'ekam'
    """
    if not value:
        return None
    candidate = unicodedata.normalize("NFKC", value).strip().lower()
    if is_shared_guru_scope(candidate) or candidate in {
        "preethaji_krishnaji",
        "krishnaji_preethaji",
        "preethaji-krishnaji",
        "krishnaji-preethaji",
    }:
        primary, _ = shared_attribution()
        return primary or "preethaji_krishnaji"
    return resolve_guru_id(candidate)


# Syntactic authority-targeting patterns that ask what a specific teacher/thinker states or teaches.
# Enables zero-shot detection of external spiritual authorities without requiring a closed list.
_TARGET_AUTHORITY_PATTERNS = [
    # 1. Direct syntactic questions: What does/did/has/would X teach/say/explain/state/write/think/guide/tell us
    re.compile(
        r"\b(?:what\s+(?:does|did|has|would))\s+([A-Za-z\s.\'\-]+?)\s+(?:teach|say|state|explain|write|think|guide|tell\s+us)\b",
        re.I,
    ),
    # 2. How does/did/would X explain/define/approach/describe/view/guide/teach/address
    re.compile(
        r"\b(?:how\s+(?:does|did|would))\s+([A-Za-z\s.\'\-]+?)\s+(?:explain|define|approach|describe|view|guide|teach|address)\b",
        re.I,
    ),
    # 3. Attributive framing: According to X / In the words of X / As taught by X
    re.compile(
        r"\b(?:according\s+to|in\s+the\s+words\s+of|as\s+taught\s+by)\s+([A-Za-z\s.\'\-]+?)(?:,|\?|\.|\s+about|\s+on|\s+in|$)",
        re.I,
    ),
    # 4. Inquiries on specific methods/perspectives: What is X's / explain X's method/teachings/perspective/advice/view
    re.compile(
        r"\b(?:what\s+is|explain|what\s+are\s+(?:the\s+)?(?:main\s+)?(?:ideas?|views?|teachings?|steps?|arguments?)\s+(?:in|of))\s+([A-Za-z\s.\'\-]+?)(?:\'s|\x27s)\s+(?:meditations?|teachings?|perspective|argument|view|ideas?|steps?|method|philosophy|practice|writings?|work|book|canon|approach|take|advice|quote)\b",
        re.I,
    ),
    # 5. Possessive authority framing: X's teachings / view / perspective / advice on/about
    re.compile(
        r"\b([A-Za-z\s.\'\-]+?)(?:\'s|\x27s)\s+(?:teachings?|perspective|argument|view|method|philosophy|approach|advice|take|quote)\s+(?:on|about|regarding)\b",
        re.I,
    ),
    # 6. Concise topic framing: <Entity> on <topic> (e.g. 'Alan Watts on ego', 'Thich Nhat Hanh on walking meditation')
    re.compile(
        r"^([A-Za-z\s.\'\-]+?)\s+on\s+([A-Za-z\s.\'\-]+)$",
        re.I,
    ),
    # 7. Conversational inquiry: tell me about X's teachings / view / perspective on Y
    re.compile(
        r"\b(?:tell\s+me\s+about|what\s+can\s+you\s+tell\s+me\s+about)\s+([A-Za-z\s.\'\-]+?)(?:\'s|\x27s)?\s+(?:teachings?|perspective|view|philosophy|insights?)\b",
        re.I,
    ),
    # 8. Tradition / doctrinal school framing: In <Tradition>, how/what / what does the <Tradition> say/teach
    re.compile(
        r"\b(?:what\s+does\s+(?:the\s+)?([A-Za-z\s.\'\-]+?)\s+(?:tradition|philosophy|school)\s+(?:say|teach)|in\s+(?:the\s+)?([A-Za-z\s.\'\-]+?)\s+(?:tradition|philosophy)\b)",
        re.I,
    ),
]

_CLEAN_PREFIX_RE = re.compile(
    r"^(?:the\s+|an?\s+|master\s+|venerable\s+|swami\s+|father\s+|his\s+holiness\s+)",
    re.I,
)


def extract_target_authority(query: str) -> dict[str, Any] | None:
    """Intelligently extract the teacher or authority entity targeted by the query.

    Returns a dict with:
      - 'target': raw string of targeted authority
      - 'is_registered': True if target maps to a registered guru in gurus.yaml
      - 'guru_id': canonical guru ID if registered, else None
      - 'source': detection method ('syntactic_authority' or 'tradition_or_teacher_lexicon')
    or None if the query does not target a specific teacher or doctrine.
    """
    text = unicodedata.normalize("NFKC", query or "").strip()
    if not text:
        return None

    for pat in _TARGET_AUTHORITY_PATTERNS:
        m = pat.search(text)
        if m:
            raw_target = m.group(1).strip()
            clean_target = _CLEAN_PREFIX_RE.sub("", raw_target).strip()
            if len(clean_target) >= 2:
                gid = resolve_guru_id(clean_target) or canonical_guru_id(clean_target)
                if not gid:
                    # Check if compound targets multiple registered gurus (e.g. "Krishnaji and Preethaji")
                    parts = [p.strip() for p in re.split(r"\s+(?:and|&|\+|or)\s+", clean_target, flags=re.I) if p.strip()]
                    if len(parts) >= 2:
                        part_gids = [
                            resolve_guru_id(_CLEAN_PREFIX_RE.sub("", p).strip())
                            or canonical_guru_id(_CLEAN_PREFIX_RE.sub("", p).strip())
                            for p in parts
                        ]
                        if all(part_gids):
                            return {
                                "target": clean_target,
                                "is_registered": True,
                                "guru_id": None,
                                "source": "syntactic_authority",
                            }
                return {
                    "target": clean_target,
                    "is_registered": bool(gid),
                    "guru_id": gid,
                    "source": "syntactic_authority",
                }

    m_trad = _UNREGISTERED_TEACHER_RE.search(text)
    if m_trad:
        return {
            "target": m_trad.group(0),
            "is_registered": False,
            "guru_id": None,
            "source": "tradition_or_teacher_lexicon",
        }

    return None


def requested_unregistered_teacher_or_tradition(
    query: str, allow_comparative: bool = False
) -> str | None:
    """Return the name/pattern of an unregistered teacher or external tradition named in query, if any.

    If allow_comparative is True, inquiries comparing an in-domain registered guru with an
    external authority do not return the external authority as a hard block.
    """
    if allow_comparative and requested_gurus(query):
        return None
    auth = extract_target_authority(query)
    if auth and not auth["is_registered"]:
        return str(auth["target"])
    return None


def is_comparative_authority_query(query: str) -> tuple[bool, list[str], list[str]]:
    """Determine if a query compares registered in-domain teachers with external authorities.

    Returns:
        tuple[bool, list[str], list[str]]: (is_comparative, in_domain_guru_ids, external_authorities)
    """
    in_domain = requested_gurus(query)
    auth = extract_target_authority(query)
    ext_list: list[str] = []
    if auth and not auth.get("is_registered") and auth.get("target"):
        ext_list.append(str(auth["target"]))
    else:
        m_trad = _UNREGISTERED_TEACHER_RE.search(query)
        if m_trad:
            ext_list.append(m_trad.group(0))

    is_comp = bool(in_domain and ext_list)
    return is_comp, in_domain, ext_list


def format_external_teacher_boundary(target_entity: str, topic: str | None = None) -> str:
    """Generate an honest, respectful domain boundary response for external teachers and traditions."""
    topic_clause = f" on {topic.strip()}" if topic and topic.strip() else ""
    teachers_label = " and ".join(g.label for g in get_gurus() if g.label) or "our spiritual teachers"
    return (
        f"I am dedicated exclusively to sharing the sacred teachings of {teachers_label}. "
        f"While {target_entity} offers valued insights in their tradition, I do not have verified "
        f"recordings of their teachings in this sanctuary. Would you like to explore what "
        f"{teachers_label} teach{topic_clause}? 🙏"
    )


def shared_attribution() -> tuple[str | None, list[str]]:
    """Configured primary ID and allowed related IDs for the shared corpus."""
    data = _registry_document()
    known = {guru.id for guru in get_gurus()}
    ids = data.get("shared_attribution_ids") or []
    if not isinstance(ids, list) or not ids or any(str(item).lower() not in known for item in ids):
        return None, []
    primary = str(data.get("shared_primary_teacher_id") or "").strip().lower()
    if not primary:
        return None, [str(item).lower() for item in ids]
    return primary, [str(item).lower() for item in ids]


def match_organization(context: str) -> dict[str, Any] | None:
    """Resolve a registered organization/channel alias in source metadata only."""
    for organization in _registry_document().get("organizations") or []:
        if not isinstance(organization, dict) or not organization.get("id"):
            continue
        aliases = organization.get("aliases") or []
        if not isinstance(aliases, list):
            continue
        try:
            pattern = re.compile("|".join(f"(?:{alias})" for alias in aliases), re.I)
        except re.error:
            logger.warning("Ignoring invalid organization alias pattern")
            continue
        if pattern.search(unicodedata.normalize("NFKC", context or "")):
            return organization
    return None


def is_shared_guru_scope(value: str | None) -> bool:
    candidate = (value or "").strip().lower()
    if candidate in {"both", "all", "shared"}:
        return True
    primary, _ = shared_attribution()
    if primary and candidate == primary:
        return True
    return False


def get_rights_policy_for(guru_id: str | None) -> str | None:
    gid = (guru_id or "").strip().lower()
    return next((g.rights_policy for g in get_gurus() if g.id == gid), None)


def get_attribution_policy_for(guru_id: str | None) -> str | None:
    gid = (guru_id or "").strip().lower()
    return next((g.attribution_policy for g in get_gurus() if g.id == gid), None)


def get_allowed_surfaces_for(guru_id: str | None) -> tuple[str, ...]:
    gid = (guru_id or "").strip().lower()
    return next((g.allowed_surfaces for g in get_gurus() if g.id == gid), ())


def get_impersonation_patterns() -> list[str]:
    """Dynamically generate impersonation refusal patterns for all registered teachers."""
    names: list[str] = []
    for g in get_gurus():
        names.append(re.escape(g.id))
        names.append(re.escape(g.label))
        for a in g.aliases:
            names.append(a)
    names_re = "|".join(dict.fromkeys(names))
    return [
        rf"\bpretend\s+(?:you\s+are|to\s+be)\s+(?:sri\s+)?(?:{names_re})\b",
        rf"\bspeak\s+as\s+(?:if\s+you\s+were\s+)?(?:sri\s+)?(?:{names_re})\b",
        rf"\b(speak|talk|answer|reply|respond|write|chat)\s+(to\s+me\s+)?(in\s+the\s+first\s+person\s+)?as\s+"
        rf"(if\s+you\s+(were|are)\s+)?(sri\s+|lord\s+|amma\s+)?(god|the\s+divine|bhagavan|bhagwan|krishna|amma|the\s+founders?|{names_re})\b",
        rf"\b(be|become|play)\s+(sri\s+)?({names_re}|god|bhagavan|bhagwan)\s+(for\s+me|and|to\s+me|tonight|now)\b",
    ]


def validate_guru_registry_schema(doc: dict[str, Any] | None = None) -> list[str]:
    """Validate gurus.yaml document against required schema (T8-01).

    Returns list of validation error messages (empty if valid).
    """
    data = doc if doc is not None else _registry_document()
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["Document must be a YAML mapping"]

    gurus = data.get("gurus")
    if not isinstance(gurus, list) or not gurus:
        return ["Document must contain a non-empty 'gurus' list"]

    required_keys = {
        "id",
        "label",
        "attribution_tag",
        "aliases",
        "rights_policy",
        "attribution_policy",
    }
    for idx, entry in enumerate(gurus):
        if not isinstance(entry, dict):
            errors.append(f"guru[{idx}] is not a mapping")
            continue
        missing = required_keys - set(entry.keys())
        if missing:
            errors.append(
                f"guru[{idx}] (id={entry.get('id')}) missing required keys: {sorted(missing)}"
            )
        if not isinstance(entry.get("aliases"), list) or not entry["aliases"]:
            errors.append(f"guru[{idx}] aliases must be a non-empty list")
        if not isinstance(entry.get("allowed_surfaces"), list) or not entry["allowed_surfaces"]:
            errors.append(f"guru[{idx}] allowed_surfaces must be a non-empty list")

    return errors


if __name__ == "__main__":
    assert requested_gurus("What does Sri Preethaji say?") == ["preethaji"]
    assert requested_gurus("Preethaji and Krishnaji on love") == ["preethaji", "krishnaji"]
    assert resolve_guru_id("sri-preethaji") == "preethaji"
    print("guru_registry ok", sorted(allowed_speaker_labels()))

"""Read-only narration contracts and fail-closed checks for Codex outputs."""
from __future__ import annotations

import re
from collections import Counter
from typing import Any

PROFILE = "senior_listening_v3"
CHECKS = (
    "cast_introduction", "relationships", "chronology", "object_tracking",
    "causality", "title_payoff", "repetition", "spoken_language", "factual_grounding",
)

CATEGORY_RULES = {
    "2": "옛날이야기: Warm oral storytelling. Introduce the protagonist and relationship before names. Track every clue, tool and disguise from discovery to payoff. A presumed-dead person's return needs a seeded survival explanation. Resolve accusations through evidence, not a sudden crowd confession. Period-appropriate words, explained naturally; no mandatory stock transitions or repeated moral endings.",
    "3": "경제: Calm, respectful plain-language explanation, not disaster prophecy. Define terms such as LTV on first use. Maintain a numerical ledger of principal, rate, period, units and assumptions; arithmetic must agree throughout. Distinguish a dated verified fact from a hypothetical scenario. Every real-world numeric/legal/banking claim needs supplied relevant evidence with source URL and date. A popular YouTube title is not proof. Omit unsupported assertions; do not invent current figures, mandatory repayments or universal investment prescriptions. Explain one mechanism once, then a concrete implication.",
    "4": "탈북사연: Restrained, dignified testimony-style FICTION unless supplied verified testimony. Lock narrator identity and viewpoint, sibling gender/age and 언니/누나/형/오빠 usage. Track objects across the border and all custody changes. Explain survival, travel and delayed contact plausibly; never use trauma as a substitute for causality or portray invented events as a real person's testimony. Avoid graphic sensationalism and repetitive suffering summaries.",
    "5": "한국사연: Realistic spoken family drama. Track exactly who knows what, who paid whom and when. A person cannot both be unaware of support and knowingly conceal that same support without an explained change in knowledge. Establish how parcels and documents reached the scene. Reconcile hospital, debt and family timelines. Show apology through one concrete changed action; do not extend the ending with successive speeches about forgiveness.",
    "6": "해외감동: Natural Korean human-interest narration. Introduce unfamiliar names with roles; use consistent names and locations. Explain who wrote a letter, when, how it survived and why it was hidden. Repayment or reunion must follow a plausible chain of events. Treat unverified stories as fiction; no invented claim of a true foreign news event. Use concrete kindness instead of many abstract metaphors about warmth.",
    "7": "무협: Restrained martial storytelling with clear spatial action. Explain unfamiliar sect ranks and 사형 (senior fellow disciple) when first used. Track sect loyalties, kinship, weapons, injuries and travel. Introduce arrivals, captures and escapes on the page before a character acts. Seed survival and revealed identities. Let honor appear through choices, not repetitive proclamations.",
    "8": "노후금융: Respectful, reassuring practical narration without infantilizing older adults. Resolve the financial incident promised in the title: why funds disappeared, what was checked, and what remains unknown. A benefactor's payment does not explain a missing retirement fund. Separate fictional illustration from factual guidance. Support financial, legal and procedural claims with supplied source URL and date; omit unsupported rules or guaranteed outcomes. Explain jargon and all amounts, rates and periods clearly. Preserve the older protagonist's agency.",
    "9": "황혼19금: Dignified late-life romance with mutual consent, autonomy and restrained intimacy. Introduce every coworker and former partner before using their name. Establish the original separation, missed appointment and present reunion consistently. Employment dismissal/reinstatement needs an explicit cause. Avoid humiliation of age, automatic forgiveness, coercion framed as romance, and sudden financial or romantic rescue. End on a concrete choice and changed daily life.",
    "12": "English Folktales: Write idiomatic spoken ENGLISH, not Korean or translated template text. Introduce names and relationships, explain regional folklore terms, seed magic and survival rules, track objects and resolve the title's mystery. Warm adult storytelling without infantilization or repeated morals.",
    "13": "日本昔話: Write idiomatic spoken JAPANESE. Keep readings, names, kinship and honorifics consistent. Explain period terms through context, seed supernatural rules and survival, track objects and resolve the title's mystery. Warm adult oral storytelling without translationese or repetitive moral endings.",
}


def contract(payload: dict[str, Any]) -> str:
    category_id = str(payload.get("category_id") or "")
    if category_id not in CATEGORY_RULES:
        name = str(payload.get("category_name") or payload.get("category") or "").lower()
        aliases = {"옛날이야기": "2", "경제": "3", "탈북사연": "4", "한국사연": "5", "해외감동": "6", "무협": "7", "노후금융": "8", "황혼19금": "9", "english folktales": "12", "日本昔話": "13"}
        category_id = aliases.get(name, category_id)
    category = CATEGORY_RULES.get(category_id,
        "Use the requested category and language; clear adult oral narration with motivated events and a resolved title promise.")
    return f"""[Mandatory senior listening contract: {PROFILE}]
{category}
Write for adults listening without watching the screen. Do not assume age implies poor comprehension.
Introduce the protagonist's role and immediate situation before loading names or mysteries.
Maintain a continuity ledger in narrative_blueprint: cast (role, relationship, age/gender where relevant, first introduction), timeline, object custody, character knowledge, planted clues and their resolutions.
The opening's 5-second VISUAL cuts must still form connected spoken narration; they are not 12 unrelated teasers. Do not introduce more names than the listener can connect to roles.
Every reveal must follow established evidence; explain new arrivals, deaths/survival, custody changes and motivations.
Prefer concrete actions and natural idioms. Avoid malformed metaphors such as '두 손으로 입을 삼켰다'. Vary rhythm for meaning, not random verb replacements to evade an ending counter.
Resolve the event promised by the title. End after the consequence and a short afterglow; do not pad duration with paraphrases, repeated rhetorical questions or extra reconciliation scenes.
Never output placeholder English, scene labels, headings, camera cues, blank sections or synthetic filler. Respect the requested language. If evidence/content is insufficient, return revise, never pretend completion.
For factual content, narrative_blueprint must include a claim ledger with claim, source URL, source date, relevant evidence, units and assumptions. Mark invented scenarios as hypothetical. If no adequate supplied evidence exists, omit the claim or fail review.
An independent reviewer must return script_quality_report with profile='{PROFILE}', verdict='pass' or 'revise', numeric score (0-100), critical_issues (array), and checks (object).
checks must contain every key: {', '.join(CHECKS)}. Each value is {{'pass': boolean, 'evidence': 'specific script quote/scene references and reasoning'}}. factual_grounding may pass as not applicable only for clearly fictional content, with explanation.
Pass requires score >=85, no critical issues, and every check passing with evidence. Flag unresolved inconsistencies even when the prose is beautiful. Do not give a pass just because the writer claimed one.
"""


def text_issues(sections: list[Any], payload: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    texts = []
    for index, section in enumerate(sections, 1):
        if not isinstance(section, dict) or not isinstance(section.get("text"), str) or not section["text"].strip():
            issues.append(f"section {index}: missing narration")
            continue
        if section.get("scene_order") != index:
            issues.append(f"section {index}: invalid scene order")
        texts.append(section["text"].strip())
    script = "\n\n".join(texts)
    if not texts:
        issues.append("empty script")
    for phrase in ("At first, nobody knew how far this event would go",
                   "One small clue remained, and it quietly changed the hearts",
                   "As time passed, the hidden story became clear",
                   "lorem ipsum", "insert narration here"):
        if phrase.casefold() in script.casefold():
            issues.append("placeholder text: " + phrase)
    if re.search(r"(?im)^\s*(?:intro|scene|장면)\s*\d+\s*[.:：]", script):
        issues.append("scene labels in narration")
    language = str(payload.get("language") or {"12": "en", "13": "ja"}.get(str(payload.get("category_id")), "ko")).lower()
    if language.startswith("ko") and script:
        hangul = len(re.findall(r"[가-힣]", script))
        latin = len(re.findall(r"[A-Za-z]", script))
        if hangul < 10 or latin > hangul:
            issues.append("Korean narration missing or dominated by English")
    sentences = [re.sub(r"\s+", " ", s).strip() for s in re.split(r"(?<=[.!?。！？])\s+", script)]
    for sentence, count in Counter(sentences).items():
        if len(sentence) >= 20 and count >= 3:
            issues.append(f"sentence repeated {count} times: {sentence[:100]}")
    for paragraph, count in Counter(texts).items():
        if len(paragraph) >= 40 and count >= 2:
            issues.append(f"duplicate narration section ({count} copies): {paragraph[:80]}")
    return issues


def review_issues(report: Any) -> list[str]:
    if not isinstance(report, dict):
        return ["missing independent script review"]
    issues = []
    if report.get("profile") != PROFILE:
        issues.append("missing/current senior review profile required")
    if report.get("verdict") != "pass":
        issues.append("review verdict is not pass")
    score = report.get("score")
    if type(score) not in (int, float) or not 85 <= score <= 100:
        issues.append("review score must be 85-100")
    if report.get("critical_issues") != []:
        issues.append("critical issues unresolved or missing")
    checks = report.get("checks")
    checks = checks if isinstance(checks, dict) else {}
    for key in CHECKS:
        item = checks.get(key)
        if not isinstance(item, dict) or item.get("pass") is not True or not isinstance(item.get("evidence"), str) or len(item["evidence"].strip()) < 12:
            issues.append(f"review check failed/missing evidence: {key}")
    return issues

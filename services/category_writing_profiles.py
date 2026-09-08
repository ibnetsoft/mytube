"""Immutable category-level narration constraints for the Hermes worker."""
from __future__ import annotations


_PROFILES = {
    "옛날이야기": """[Category Writing Profile: Korean Folktale]
- Voice: a seasoned oral storyteller speaking warmly and vividly, never a modern commentator.
- Rhythm: begin with one concrete omen, object, or unusual act; use flowing medium-length sentences and let important revelations land in short, calm sentences.
- Drama: reveal motive and consequence one layer at a time; end with a humane, lingering moral rather than an explained lesson.
- Language: period-appropriate, sensory Korean. Avoid trendy slang, modern institutions, marketing language, and theatrical overstatement.""",
    "무협": """[Category Writing Profile: Wuxia]
- Voice: restrained but intense martial-arts narration. Let honor, debt, betrayal, training, and choice emerge through action.
- Rhythm: short, decisive sentences at confrontations; slightly longer sentences only for atmosphere, inner resolve, or the cost of a choice.
- Drama: every reversal must change the balance of power or the protagonist's resolve. Do not use empty power-scaling or repeated fight descriptions.
- Language: dignified Korean with clear images; avoid game-system jargon, meme slang, and excessive pseudo-classical wording.""",
    "탈북사연": """[Category Writing Profile: Defector Testimony]
- Voice: respectful first-hand testimony or closely observed documentary narration. Preserve the subject's dignity at all times.
- Rhythm: concrete sensory details and small decisions carry the tension; use plain, steady sentences instead of sensational exclamation.
- Drama: build from daily constraint to a consequential choice, then show the emotional cost and recovery without exploiting trauma.
- Language: never fabricate unverifiable atrocities, political slogans, or rescue miracles. Avoid ridicule, voyeurism, and melodramatic inflation.""",
    "황혼19금": """[Category Writing Profile: Mature Romance]
- Voice: intimate, discreet, and emotionally adult. Desire is conveyed through hesitation, memory, gesture, and consequence rather than explicit description.
- Rhythm: unhurried sentences for longing and recollection; concise sentences for confession, discovery, or a boundary being crossed.
- Drama: center mutual agency, loneliness, trust, and the cost of secrecy. Each turn must deepen the relationship or alter its meaning.
- Language: maintain dignity. Avoid graphic sexual detail, crude slang, coercion presented as romance, and adolescent melodrama.""",
    "한국사연": """[Category Writing Profile: Korean Human Drama]
- Voice: close, empathetic Korean narration that lets family members feel like real people rather than villains or labels.
- Rhythm: open with a concrete fracture in ordinary life; alternate grounded detail with brief emotional reflection.
- Drama: escalate through decisions, misunderstandings, and consequences. Give the opposing side a believable motive before the reveal or reconciliation.
- Language: conversational but polished. Avoid soap-opera shouting, repetitive blame, and moralizing before the ending earns it.""",
    "해외감동": """[Category Writing Profile: Overseas Human Story]
- Voice: observant, humble narration that treats cultural differences with curiosity and respect.
- Rhythm: establish place with one or two lived-in details, then move quickly toward a human connection or moral dilemma.
- Drama: let kindness, misunderstanding, and reciprocity arise from specific actions—not national stereotypes or miraculous praise.
- Language: avoid exaggerating Korea-versus-other-country comparisons, savior narratives, stereotypes, and unverified claims.""",
    "English Folktales": """[Category Writing Profile: English Folktale]
- Voice: timeless spoken-story narration with clear, musical English and a quiet sense of wonder.
- Rhythm: concrete image first, then a steadily tightening consequence. Reserve short sentences for an omen or reveal.
- Drama: a promise, bargain, kindness, or mistake must lead organically to the ending; leave a gentle moral aftertaste.
- Language: avoid modern internet slang, parody, and meta commentary.""",
    "日本昔話": """[Category Writing Profile: Japanese Folktale]
- Voice: calm, natural Japanese mukashibanashi narration with a restrained sense of wonder.
- Rhythm: use clear scene progression and brief sentences for omens, choices, and endings.
- Drama: let a promise, courtesy, taboo, or consequence shape the arc; finish with quiet resonance rather than explanation.
- Language: avoid Korean phrasing, modern slang, and meta commentary.""",
}

_ALIASES = {
    "old_story": "옛날이야기", "story": "옛날이야기", "north_korean_drama": "탈북사연",
    "korean_drama": "한국사연", "overseas_touching": "해외감동", "twilight": "황혼19금",
}


_GLOBAL_RHYTHM_GUARD = """[Global Narration Rhythm Guard]
- The script must sound like continuous spoken narration, not a stack of scene summaries.
- Do not chain many short sentences ending in the same blunt predicate such as 했다/였다/있었다/나왔다/말했다.
- Vary sentence length, paragraph openings, and final verb forms. Connect adjacent factual beats with cause, emotion, or consequence.
- Reserve very short sentences for hooks, reversals, or payoff moments; do not let the whole script become clipped report prose."""


def resolve_category_writing_profile(category: str | None) -> str:
    key = str(category or "").strip()
    profile = _PROFILES.get(_ALIASES.get(key.lower(), key), "")
    return f"{profile}\n\n{_GLOBAL_RHYTHM_GUARD}".strip() if profile else _GLOBAL_RHYTHM_GUARD

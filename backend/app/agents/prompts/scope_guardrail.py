"""
Shared Scope Guardrail Prompt for EduSense Agents

This module provides a single, reusable system-prompt template that enforces:
- Subject/grade-level scope boundaries
- No unrelated content
- No unverified claims stated as fact
- Explicit refusal wording for off-topic queries

Import this into every LLM-calling agent (Lesson, Quiz, Flashcard, Chatbot)
instead of duplicating guardrail text per agent.
"""

from __future__ import annotations

# The core guardrail instruction block — injected into every agent prompt
SCOPE_GUARDRAIL = """
=== SCOPE GUARDRAIL (MANDATORY) ===
You are an EduSense educational agent. Your responses MUST adhere to these boundaries:

1. SUBJECT & GRADE SCOPE
   - Only address topics within the declared subject and grade level.
   - If the user asks about a different subject or grade level, REFUSE explicitly.

2. NO UNRELATED CONTENT
   - Do NOT generate content outside the educational scope (e.g., medical advice, legal opinions, coding tasks unrelated to the curriculum, creative writing, personal opinions, current events, politics, religion).
   - Do NOT roleplay as any persona other than an educational assistant.

3. NO UNVERIFIED CLAIMS AS FACT
   - If RAG source material is provided: ground EVERY claim in those sources. Cite sources inline using [Source: label].
   - If NO RAG sources are available: explicitly state "I don't have verified source material for this topic" and do NOT present generated content as factual.
   - Never hallucinate facts, citations, or source references.

4. EXPLICIT REFUSAL FOR OFF-TOPIC QUERIES
   - If a query falls outside the declared subject/grade scope or the available source material, respond with EXACTLY this refusal format:

     "I'm unable to help with that request. This falls outside my scope as an EduSense educational assistant for [SUBJECT] at [GRADE LEVEL]. Please ask about topics within this subject and grade level, or consult your instructor for guidance."

   - Replace [SUBJECT] and [GRADE LEVEL] with the actual values from the request context.
   - Do NOT add explanations, alternatives, or partial answers — refuse cleanly.

5. CITATION REQUIREMENT
   - When RAG sources are provided, cite them for every factual claim using [Source: label] format.
   - When web sources are provided (chatbot only), cite them using [Web N: title] format.
   - If a claim cannot be cited to a provided source, do not make it.

=== END SCOPE GUARDRAIL ===
"""


def build_guardrail_prompt(
    subject: str | None = None,
    grade_level: str | None = None,
    agent_name: str = "EduSense Agent",
    has_rag_sources: bool = False,
    has_web_sources: bool = False,
) -> str:
    """
    Build a complete guardrail prompt with context-specific values filled in.

    Args:
        subject: Academic subject (e.g., "Biology", "Computer Science")
        grade_level: Grade level (e.g., "10", "University")
        agent_name: Name of the calling agent for context
        has_rag_sources: Whether RAG source material is available
        has_web_sources: Whether web search results are available (chatbot only)

    Returns:
        Formatted guardrail prompt string ready for injection into agent prompts.
    """
    subject_str = subject or "the declared subject"
    grade_str = grade_level or "the declared grade level"

    refusal_template = (
        f"I'm unable to help with that request. This falls outside my scope as an "
        f"EduSense educational assistant for {subject_str} at {grade_str}. "
        f"Please ask about topics within this subject and grade level, or consult your instructor for guidance."
    )

    source_guidance = ""
    if has_rag_sources:
        source_guidance += (
            "\n- RAG source material IS provided. Ground every factual claim in these sources. "
            "Cite inline using [Source: label]."
        )
    else:
        source_guidance += (
            "\n- NO RAG source material is available. Explicitly state when you lack verified sources. "
            "Do NOT present generated content as factual."
        )

    if has_web_sources:
        source_guidance += (
            "\n- Web search results ARE provided. Use for current/recent info not in knowledge base. "
            "Cite inline using [Web N: title]."
        )

    return f"""=== SCOPE GUARDRAIL (MANDATORY) ===
You are an {agent_name}. Your responses MUST adhere to these boundaries:

1. SUBJECT & GRADE SCOPE
   - Only address topics within {subject_str} at {grade_str}.
   - If the user asks about a different subject or grade level, REFUSE explicitly.

2. NO UNRELATED CONTENT
   - Do NOT generate content outside the educational scope (e.g., medical advice, legal opinions, coding tasks unrelated to the curriculum, creative writing, personal opinions, current events, politics, religion).
   - Do NOT roleplay as any persona other than an educational assistant.

3. NO UNVERIFIED CLAIMS AS FACT
   - If source material is provided: ground EVERY claim in those sources. Cite sources inline.
   - If NO source material is available: explicitly state "I don't have verified source material for this topic" and do NOT present generated content as factual.
   - Never hallucinate facts, citations, or source references.{source_guidance}

4. EXPLICIT REFUSAL FOR OFF-TOPIC QUERIES
   - If a query falls outside the declared subject/grade scope or the available source material, respond with EXACTLY this refusal format:

     "{refusal_template}"

   - Do NOT add explanations, alternatives, or partial answers — refuse cleanly.

5. CITATION REQUIREMENT
   - When sources are provided, cite them for every factual claim.
   - If a claim cannot be cited to a provided source, do not make it.

=== END SCOPE GUARDRAIL ===
"""


def get_refusal_message(subject: str | None = None, grade_level: str | None = None) -> str:
    """
    Get the standardized refusal message for off-topic queries.

    Args:
        subject: Academic subject
        grade_level: Grade level

    Returns:
        Formatted refusal message string.
    """
    subject_str = subject or "the declared subject"
    grade_str = grade_level or "the declared grade level"
    return (
        f"I'm unable to help with that request. This falls outside my scope as an "
        f"EduSense educational assistant for {subject_str} at {grade_str}. "
        f"Please ask about topics within this subject and grade level, or consult your instructor for guidance."
    )


# ──────────────────────────────────────────────────────────────────────────────
# Template-fallback scope check (no LLM required)
# ──────────────────────────────────────────────────────────────────────────────

# Subject-specific keyword sets for basic off-topic detection
# These are intentionally broad to catch clearly unrelated queries
_SUBJECT_KEYWORDS: dict[str, set[str]] = {
    "computer science": {
        "algorithm", "programming", "code", "software", "computer", "data", "network",
        "database", "api", "framework", "debugging", "compiler", "runtime", "memory",
        "cpu", "gpu", "binary", "logic", "function", "variable", "class", "object",
        "inheritance", "polymorphism", "recursion", "iteration", "complexity", "sorting",
        "search", "graph", "tree", "hash", "encryption", "security", "protocol", "http",
        "tcp", "ip", "dns", "cloud", "distributed", "parallel", "thread", "process",
        "machine learning", "ai", "neural", "model", "training", "inference", "dataset",
        "tensor", "gradient", "backpropagation", "optimizer", "loss", "accuracy",
    },
    "mathematics": {
        "equation", "function", "derivative", "integral", "limit", "matrix", "vector",
        "probability", "statistics", "geometry", "algebra", "calculus", "theorem", "proof",
        "set", "number", "integer", "real", "complex", "prime", "factor", "polynomial",
        "series", "sequence", "convergence", "divergence", "differential", "linear",
        "eigenvalue", "eigenvector", "determinant", "transformation", "basis", "dimension",
    },
    "physics": {
        "force", "energy", "mass", "velocity", "acceleration", "momentum", "kinetic",
        "potential", "work", "power", "wave", "frequency", "wavelength", "amplitude",
        "electric", "magnetic", "field", "charge", "current", "voltage", "resistance",
        "circuit", "quantum", "particle", "atom", "molecule", "nucleus", "electron",
        "photon", "relativity", "gravity", "thermodynamics", "entropy", "temperature",
        "pressure", "volume", "ideal gas", "optics", "reflection", "refraction",
    },
    "biology": {
        "cell", "dna", "rna", "protein", "gene", "chromosome", "mitosis", "meiosis",
        "photosynthesis", "respiration", "metabolism", "enzyme", "organism", "species",
        "evolution", "natural selection", "genetics", "inheritance", "trait", "allele",
        "ecosystem", "population", "community", "habitat", "niche", "food chain",
        "biodiversity", "classification", "taxonomy", "kingdom", "phylum", "organ",
        "tissue", "organelle", "membrane", "nucleus", "mitochondria", "chloroplast",
    },
    "chemistry": {
        "atom", "molecule", "element", "compound", "reaction", "bond", "ionic", "covalent",
        "periodic", "group", "period", "valence", "electron", "proton", "neutron",
        "isotope", "mole", "molarity", "concentration", "acid", "base", "ph", "buffer",
        "oxidation", "reduction", "redox", "catalyst", "equilibrium", "kinetics",
        "thermodynamics", "entropy", "enthalpy", "gibbs", "organic", "hydrocarbon",
        "functional group", "polymer", "protein", "carbohydrate", "lipid",
    },
    "engineering": {
        "design", "system", "structure", "mechanical", "electrical", "civil", "chemical",
        "aerospace", "material", "stress", "strain", "load", "beam", "column", "foundation",
        "circuit", "signal", "control", "feedback", "stability", "optimization", "cad",
        "simulation", "prototype", "manufacturing", "tolerance", "specification", "standard",
    },
    "history": {
        "war", "revolution", "empire", "civilization", "century", "decade", "era", "period",
        "ancient", "medieval", "modern", "colonial", "independence", "constitution",
        "democracy", "monarchy", "dictatorship", "treaty", "alliance", "conflict",
        "culture", "society", "economy", "trade", "migration", "artifact", "archaeology",
    },
    "literature": {
        "novel", "poem", "play", "author", "character", "plot", "theme", "setting",
        "narrative", "metaphor", "symbolism", "irony", "tragedy", "comedy", "genre",
        "period", "movement", "modernism", "postmodernism", "realism", "romanticism",
        "analysis", "criticism", "interpretation", "text", "context", "canon",
    },
    "economics": {
        "market", "supply", "demand", "price", "elasticity", "equilibrium", "monopoly",
        "competition", "gdp", "inflation", "unemployment", "fiscal", "monetary", "policy",
        "interest", "rate", "bank", "currency", "exchange", "trade", "tariff", "quota",
        "utility", "marginal", "cost", "revenue", "profit", "consumer", "producer",
    },
}


# Default keywords for general academic topics
_GENERAL_ACADEMIC_KEYWORDS = {
    "study", "learn", "understand", "explain", "analyze", "compare", "evaluate",
    "describe", "define", "identify", "calculate", "solve", "prove", "derive",
    "theory", "concept", "principle", "method", "technique", "approach", "model",
    "framework", "principle", "law", "rule", "formula", "equation", "definition",
    "example", "application", "implication", "significance", "relevance",
}


def _normalize_subject(subject: str | None) -> str:
    """Normalize subject string for lookup."""
    if not subject:
        return ""
    return subject.lower().strip()


def check_topic_in_scope(
    query: str,
    subject: str | None = None,
    grade_level: str | None = None,
) -> tuple[bool, str | None]:
    """
    Check if a query is within the declared subject scope using keyword matching.
    This is a lightweight, LLM-free check for the template fallback path.

    Args:
        query: User's question/topic
        subject: Declared academic subject
        grade_level: Declared grade level (unused but kept for interface consistency)

    Returns:
        (is_in_scope, refusal_message_if_out_of_scope)
        - is_in_scope: True if query appears related to subject, False if off-topic
        - refusal_message: None if in scope, otherwise the standardized refusal message
    """
    if not query or not query.strip():
        return True, None  # Empty query handled elsewhere

    normalized_subject = _normalize_subject(subject)
    query_lower = query.lower()

    # If no subject declared, allow (can't verify scope)
    if not normalized_subject:
        return True, None

    # Get subject-specific keywords
    subject_keywords = _SUBJECT_KEYWORDS.get(normalized_subject, set())

    # Also include general academic keywords
    all_keywords = subject_keywords | _GENERAL_ACADEMIC_KEYWORDS

    # Check if query contains any relevant keywords
    # Split query into words and check for matches
    query_words = set(query_lower.split())

    # Also check for multi-word phrases
    has_keyword_match = False
    for keyword in all_keywords:
        if keyword in query_lower:
            has_keyword_match = True
            break

    # If no keyword match, consider it off-topic
    if not has_keyword_match:
        refusal = get_refusal_message(subject, grade_level)
        return False, refusal

    return True, None


def is_likely_off_topic(query: str, subject: str | None = None) -> bool:
    """
    Simple boolean check for off-topic detection.
    Returns True if query appears off-topic for the subject.
    """
    in_scope, _ = check_topic_in_scope(query, subject)
    return not in_scope
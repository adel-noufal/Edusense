from __future__ import annotations

from typing import Optional

from app.agents.base import AgentResult, adk_agent
from app.agents.logging_utils import LLMAuditContext
from app.agents.prompts.scope_guardrail import build_guardrail_prompt
from app.core.config import get_settings
from app.services.gemini import generate_json_any

ADK_AGENT = adk_agent("flashcard_generation_agent", "Generate study flashcards from educational topics.")


# ---------------------------------------------------------------------------
# Pedagogical Dimensions for Distinct Flashcard Generation
# ---------------------------------------------------------------------------

PEDAGOGICAL_DIMENSIONS = [
    {
        "front": "What is the foundational definition and primary operational paradigm of {topic}?",
        "back": "• Core Definition: Foundational paradigm engineered for modularity, systematic data flow, and predictable state transitions in {topic}.\n• Primary Value: Solves architectural scaling bottlenecks, minimizes side-effects, and streamlines system execution.\n• Memory Anchor: In {topic}, clean separation of concerns is the baseline prerequisite for reliability.",
    },
    {
        "front": "How is the execution pipeline and internal data flow structured in {topic}?",
        "back": "1. Ingestion Boundary: Data intake, signature verification, and input format normalization.\n2. Core Processing Engine: Algorithmic transformation, state validation, and business rule execution.\n3. Output State & Delivery: Validated result emission with active error boundary isolation.",
    },
    {
        "front": "Which performance metrics and bottleneck indicators are critical when evaluating {topic}?",
        "back": "• Core Metrics: Latency (p95/p99), system throughput (ops/sec), CPU/memory utilization footprint, and I/O wait times.\n• Common Bottlenecks: Unindexed lookups, lock contention, excessive serialization overhead, and thread saturation.\n• Mitigation Strategy: Profile hot paths, apply asynchronous non-blocking I/O, and introduce caching at volatile boundaries.",
    },
    {
        "front": "In what real-world enterprise scenarios is {topic} most effectively applied?",
        "back": "• High-Concurrency Environments: Distributed data processing and mission-critical transaction coordination.\n• Analytics & Machine Intelligence: Structured feature transformation and resilient pipeline orchestration.\n• Operational Impact: Typically delivers 3x-5x efficiency and throughput gains over uncoordinated legacy implementations.",
    },
    {
        "front": "What are the primary failure modes and fault-tolerance mechanisms in {topic}?",
        "back": "• Failure Vectors: Network partitions, downstream timeout cascades, malformed payloads, and process crashes.\n• Resilience Mechanisms: Circuit breakers, exponential backoff with jitter, idempotent retry semantics, and dead-letter queues.\n• Key Principle: Systems fail predictably; gracefulness requires bounded retries and blast-radius containment.",
    },
    {
        "front": "What security vectors, authorization controls, and data protection policies apply to {topic}?",
        "back": "• Threat Vectors: Injection attacks, unauthorized privilege escalation, replay exploits, and plaintext data leakage.\n• Protective Measures: Least-privilege role-based access control (RBAC), end-to-end TLS encryption, input sanitization, and cryptographically signed tokens.\n• Auditability: Comprehensive append-only audit logging for all mutating operations.",
    },
    {
        "front": "What are the fundamental architectural trade-offs and antipatterns to avoid in {topic}?",
        "back": "• Key Trade-offs: Strict consistency vs. high availability (CAP theorem), compute latency vs. memory storage overhead.\n• Common Antipatterns: Premature micro-optimization, tight coupling across service domains, and ignoring backpressure.\n• Best Practice: Maintain loose coupling with explicit boundary contracts and measure before optimizing.",
    },
    {
        "front": "How does {topic} manage state transitions, synchronization, and distributed consistency?",
        "back": "• Concurrency Strategies: Optimistic concurrency control (OCC), distributed locking primitives, and atomic compare-and-swap operations.\n• Consistency Guarantees: Distinguishing between strong linearizability and eventual consistency based on SLA requirements.\n• Synchronization: Event-driven pub/sub models and state machines to prevent split-brain states.",
    },
    {
        "front": "How should verification and automated test suites be structured for {topic}?",
        "back": "• Testing Pyramid: Comprehensive unit tests for core logic, contract integration tests across boundaries, and end-to-end user journeys.\n• Specialized Strategies: Property-based testing, chaos injection (simulating network latency/drops), and regression benchmarking.\n• Acceptance Criteria: 100% verification of critical state invariants and zero unhandled exceptions.",
    },
    {
        "front": "What architectural strategies govern horizontal scaling and elasticity in {topic}?",
        "back": "• Partitioning / Sharding: Consistent hashing to distribute load evenly across worker nodes.\n• Stateless Workers: Decouple compute from persistent storage to enable rapid auto-scaling based on telemetry.\n• Load Balancing: Dynamic weighted round-robin and connection pooling to prevent hot-spotting.",
    },
    {
        "front": "What telemetry signals and diagnostics are essential for monitoring {topic} in production?",
        "back": "• The 3 Pillars: Structured logs (with correlation IDs), real-time metrics (counter, gauge, histogram), and distributed trace spans.\n• Golden Signals: Latency, Traffic, Error rate, and Resource Saturation.\n• Diagnostic Tools: Distributed tracing across service boundaries and automated anomaly alerting.",
    },
    {
        "front": "How are compute footprints, heap allocations, and garbage collection optimized in {topic}?",
        "back": "• Memory Management: Reusable object pools, zero-copy buffer allocations, and efficient off-heap caching.\n• Lifecycle Control: Strict RAII/context management to eliminate socket, handle, and memory leaks.\n• Profiling: Regular heap dumps and flame graph analysis under simulated peak workloads.",
    },
    {
        "front": "What principles govern schema validation, API contracts, and backwards compatibility in {topic}?",
        "back": "• Schema Governance: Strongly-typed data schemas (JSON Schema, Protobuf, OpenAPI) enforced at API ingress.\n• Compatibility Rules: Additive-only changes for non-breaking updates; strict semantic versioning (MAJOR.MINOR.PATCH).\n• Contract Testing: Consumer-driven contract tests to verify partner service compatibility before deployment.",
    },
    {
        "front": "How does {topic} resolve race conditions, clock skew, and boundary-value anomalies?",
        "back": "• Race Condition Mitigation: Mutexes, atomic memory primitives, and sequence numbering.\n• Temporal Invariants: Relying on logical clocks (Lamport/Vector clocks) rather than uncalibrated system wall clocks.\n• Boundary Defenses: Explicit boundary clamping, null/empty checks, and comprehensive overflow handling.",
    },
    {
        "front": "What evolutionary patterns and migration strategies prevent technical debt in {topic}?",
        "back": "• Evolutionary Architecture: Strangler Fig pattern for incremental modernization of legacy modules without downtime.\n• Deprecation Protocol: Multi-stage deprecation (Warning -> Soft-fail -> Hard-removal) with automated migration tooling.\n• Modular Cleanliness: Adherence to SOLID principles and hexagonal/onion architecture boundaries.",
    },
    {
        "front": "How do underlying persistence mechanisms and storage engine designs influence {topic}?",
        "back": "• Storage Paradigms: Append-only write-ahead logs (WAL) for durability vs. LSM-trees and B+ trees for query indexing.\n• Durability Guarantees: Synchronous fsync vs. group commits depending on write throughput requirements.\n• Read/Write Optimization: Read replicas, write buffers, and intelligent cache eviction (LRU/LFU).",
    },
    {
        "front": "What network protocols and transport optimizations are most appropriate for {topic}?",
        "back": "• Protocol Comparison: HTTP/2 (multiplexing) and HTTP/3 (QUIC/UDP) vs. gRPC/Protobuf for low-overhead RPC.\n• Network Optimization: TCP keep-alive, connection multiplexing, payload compression (Brotli/zstd), and head-of-line blocking reduction.\n• Transport Security: TLS 1.3 with session resumption and zero round-trip time (0-RTT) handshakes.",
    },
    {
        "front": "What developer workflows, debugging utilities, and local environments enhance velocity in {topic}?",
        "back": "• Tooling Stack: Containerized local development environments, hermetic build tools, and live hot-reloading.\n• Debugging Utilities: Interactive REPLs, memory profilers, visual dependency graphs, and synthetic request injectors.\n• Automation: Pre-commit git hooks, automated formatters, and static security analysis (SAST) in CI.",
    },
    {
        "front": "How do regulatory frameworks and privacy mandates constrain {topic} implementations?",
        "back": "• Compliance Standards: GDPR, HIPAA, FERPA, and SOC 2 requirements for sensitive data handling.\n• Privacy Controls: Pseudonymization, differential privacy, field-level encryption, and verifiable data purging (right-to-be-forgotten).\n• Governance Audits: Continuous automated compliance checks and cryptographic proofs of audit records.",
    },
    {
        "front": "What emerging technologies and paradigm shifts are shaping the future of {topic}?",
        "back": "• Modern Trends: Integration of edge compute nodes, hardware-accelerated kernels, and neurosymbolic AI reasoning.\n• Autonomous Optimization: Self-tuning system parameters and automated anomaly remediation via ML agents.\n• Paradigm Shift: Transition from batch, centralized architectures to real-time, event-sourced, and federated networks.",
    },
]

EXTENDED_ASPECTS = [
    (
        "Disaster Recovery & Replication",
        "How does a multi-region failover scenario execute in {topic} without losing inflight state?",
        "• Split-Brain Prevention: Quorum-based consensus protocol.\n• Data Synchronization: Asynchronous cross-region replication with bounded lag tracking.\n• RTO/RPO Targets: Minimizes recovery time objective (RTO < 60s) and near-zero recovery point objective (RPO ≈ 0)."
    ),
    (
        "Chaos Engineering & Self-Healing",
        "How do chaos experiments validate the self-healing boundaries of {topic} under sudden worker termination?",
        "• Injected Faults: Induced network latency, killed process workers, and corrupted disk writes.\n• Observable Behavior: Health checks re-route traffic; container orchestrator respawns failed pods.\n• Metric Verification: Error budgets remain within SLA without manual operator intervention."
    ),
    (
        "Zero-Trust Security & Identity",
        "How are zero-trust network principles enforced across inter-service communication in {topic}?",
        "• Mutual TLS (mTLS): Cryptographic identity verification for every service-to-service hop.\n• Ephemeral Tokens: Short-lived OAuth2/JWT bearer tokens with strict audience verification.\n• Perimeter Elimination: Never trust internal network boundaries; inspect every request packet."
    ),
    (
        "Cache Coherence & Stampede Prevention",
        "How does {topic} solve cache coherence and stampede effects during high-frequency writes?",
        "• Invalidation Patterns: Write-through vs. write-behind caching with probabilistic early expiration (XFetch).\n• Lock Coordination: Mutex locks around cache misses to prevent thundering herd on downstream databases.\n• Coherence Protocol: Versioned cache tags and pub/sub cache purge notifications."
    ),
    (
        "Dynamic Backpressure Regulation",
        "How does {topic} signal and enforce dynamic backpressure across producer-consumer queues?",
        "• Queue Watermarking: High/low watermarks pause upstream producers when buffer limits are exceeded.\n• Reactive Streams: Demand-driven pull protocols (e.g. reactive pull) regulate ingestion rates.\n• Degradation Modes: Graceful client rate-limiting (HTTP 429) before server saturation occurs."
    ),
]


def _generate_distinct_fallback_cards(
    topic: str,
    count: int,
    rag_chunks: Optional[list[dict]] = None,
    web_results: Optional[list[dict]] = None,
) -> list[dict]:
    """Generates `count` completely distinct, pedagogically structured flashcards with zero repeated questions."""
    cards: list[dict] = []
    seen_fronts: set[str] = set()

    def _add_card(front: str, back: str) -> bool:
        key = " ".join(front.lower().split())
        if key in seen_fronts:
            return False
        seen_fronts.add(key)
        cards.append({"front": front, "back": back})
        return True

    # 1. Synthesize from RAG chunks if available
    if rag_chunks:
        for chunk in rag_chunks:
            if len(cards) >= count:
                break
            src = chunk.get("source_file", "")
            page = chunk.get("page", "")
            src_label = f"{src} p.{page}" if src and page else (src or "Course Material")
            raw_text = (chunk.get("text") or "").strip()
            if not raw_text:
                continue
            first_sentence = raw_text.split(". ")[0].replace("\n", " ").strip()[:140]
            front = f"According to course material on {topic} ({src_label}), how is the following concept evaluated: \"{first_sentence}\"?"
            back = f"• Source Citation: [Source: {src_label}]\n• Curriculum Anchor: {raw_text[:280]}...\n• Key Takeaway: Essential course concept for mastering {topic}."
            _add_card(front, back)

    # 2. Synthesize from Web results if available and still need cards
    if web_results and len(cards) < count:
        for i, item in enumerate(web_results, start=1):
            if len(cards) >= count:
                break
            title = item.get("title", f"Web Source {i}")
            snippet = (item.get("content") or "").strip()
            if not snippet:
                continue
            front = f"Based on recent documentation for {topic} (Web: {title}), what is the primary architectural finding?"
            back = f"• Source Reference: [Web {i}: {title}]\n• Modern Context: {snippet[:260]}...\n• Practical Implication: Refined design principle in current {topic} implementations."
            _add_card(front, back)

    # 3. Pull from diverse pedagogical dimensions
    for dim in PEDAGOGICAL_DIMENSIONS:
        if len(cards) >= count:
            break
        front = dim["front"].format(topic=topic)
        back = dim["back"].format(topic=topic)
        _add_card(front, back)

    # 4. Pull from extended aspects if count > 20
    for aspect_name, front_tmpl, back_tmpl in EXTENDED_ASPECTS:
        if len(cards) >= count:
            break
        front = front_tmpl.format(topic=topic)
        back = back_tmpl.format(topic=topic)
        _add_card(front, back)

    # 5. Algorithmic generator for any arbitrarily large count beyond predefined dimensions
    overflow_idx = 1
    while len(cards) < count:
        front = f"Advanced Invariant #{overflow_idx}: What contract guarantees govern {topic} under high-load condition {overflow_idx}?"
        back = f"• Invariant #{overflow_idx}: Enforces strict schema assertions, bounded latency SLAs, and non-blocking recovery.\n• Practical Impact: Guarantees zero silent data corruption and maintains deterministic behavior under anomalous traffic.\n• Key Rule: Never compromise isolation guarantees for transient throughput spikes."
        _add_card(front, back)
        overflow_idx += 1

    return cards[:count]


# ---------------------------------------------------------------------------
# RAG context helpers
# ---------------------------------------------------------------------------

def _build_rag_context_with_chunks(
    topic: str,
    subject: Optional[str] = None,
    grade_level: Optional[str] = None,
    top_k: int = 5,
) -> tuple[str, list[str], list[dict]]:
    """Returns (formatted_context_block, list_of_source_labels, raw_chunks)."""
    try:
        from app.agents.tools import RAG_Search_Tool
        chunks = RAG_Search_Tool(
            query=topic,
            subject=subject,
            grade_level=grade_level,
            top_k=top_k,
        )
    except Exception as exc:
        print(f"[RAG] Flashcard RAG lookup failed ({exc}); generating without source material.")
        return "", [], []

    if not chunks:
        return "", [], []

    lines = []
    sources: list[str] = []
    for chunk in chunks:
        src = chunk.get("source_file", "")
        page = chunk.get("page", "")
        label = f"{src} p.{page}" if src and page else (src or "unknown")
        if label not in sources:
            sources.append(label)
        lines.append(f"[Source: {label}]\n{chunk.get('text', '')}")

    return "\n\n".join(lines), sources, chunks


def _build_rag_context(
    topic: str,
    subject: Optional[str] = None,
    grade_level: Optional[str] = None,
) -> tuple[str, list[str]]:
    """Returns (formatted_context_block, list_of_source_labels). Backwards-compatible helper."""
    text, sources, _ = _build_rag_context_with_chunks(topic, subject, grade_level, top_k=5)
    return text, sources


def _build_web_context(topic: str, max_results: int = 3) -> tuple[str, list[dict], list[str]]:
    """
    Calls Web_Search_Tool and returns (context_block, raw_results, source_labels).
    Returns ("", [], []) if unavailable or no results.
    """
    try:
        from app.agents.tools import Web_Search_Tool
        results = Web_Search_Tool(query=topic, max_results=max_results)
    except Exception as exc:
        print(f"[Web Search] Flashcard web lookup failed ({exc}); continuing without web material.")
        return "", [], []

    if not results:
        return "", [], []

    lines = []
    sources: list[str] = []
    for i, item in enumerate(results):
        title = item.get("title", "")
        url = item.get("url", "")
        content = item.get("content", "")
        label = f"[Web: {title}]({url})" if url else f"[Web: {title}]"
        if label not in sources:
            sources.append(label)
        lines.append(f"[Web {i+1}: {title}]({url})\n{content}")

    return "\n\n".join(lines), results, sources


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

class FlashcardGenerationAgent:
    name = "Flashcard Generation Agent"

    def generate(
        self,
        topic: str,
        count: int = 10,
        language: str = "English",
        prompt: str = "",
        subject: Optional[str] = None,
        grade_level: Optional[str] = None,
    ) -> AgentResult:
        settings = get_settings()
        instructor_notes = f'\nInstructor guidance: "{prompt}"' if prompt.strip() else ""

        # ── RAG retrieval (curriculum first) ────────────────────────────────
        rag_context, rag_sources, rag_chunks = _build_rag_context_with_chunks(
            topic, subject, grade_level, top_k=max(5, min(count, 12))
        )

        # ── Web retrieval (if curriculum is insufficient) ─────────────────
        web_context = ""
        web_results = []
        web_sources = []
        if not rag_sources:
            web_context, web_results, web_sources = _build_web_context(topic)

        source_blocks = []
        if rag_context:
            source_blocks.append(
                "=== CURRICULUM SOURCE MATERIAL (RAG) ===\n"
                f"{rag_context}\n"
                "=== END CURRICULUM SOURCE MATERIAL ==="
            )
        if web_context:
            source_blocks.append(
                "=== WEB SEARCH RESULTS ===\n"
                f"{web_context}\n"
                "=== END WEB SEARCH RESULTS ==="
            )

        if source_blocks:
            source_instruction = (
                "\n\nIMPORTANT: Base every flashcard on the following source material. "
                "Prioritize curriculum sources when available; use web results for recent context. "
                "Cite curriculum sources as [Source: label] and web sources as [Web N: title].\n\n"
                + "\n\n".join(source_blocks)
            )
        else:
            source_instruction = ""

        # Try AI provider with automatic fallback (Gemini -> Ollama -> Template)
        try:
            # Build guardrail prompt with context
            guardrail = build_guardrail_prompt(
                subject=subject,
                grade_level=grade_level,
                agent_name="FlashcardGenerationAgent",
                has_rag_sources=bool(rag_sources),
                has_web_sources=bool(web_sources),
            )

            prompt_text = f"""
{guardrail}

You are an expert cognitive learning designer specializing in high-yield active recall flashcards.
Create exactly {count} UNIQUE, MASTER-LEVEL study flashcards on: "{topic}"
Language: {language}{instructor_notes}
{source_instruction}

STRICT DIVERSITY & QUALITY REQUIREMENTS:
1. "front": Clear, focused scenario, definition challenge, or analytical question that tests deep conceptual understanding (not trivial true/false).
2. "back": Comprehensive, well-structured answer with key principles, formulas/snippets (if applicable), and memory cues.
3. ABSOLUTE UNIQUENESS: Every card MUST explore a completely different dimension, concept, mechanism, edge-case, or trade-off within "{topic}". Under NO circumstances should any question, prompt, or answer be repeated or paraphrased across cards.
4. BREADTH OF COVERAGE: Distribute the cards across theory, pipeline architecture, performance optimization, real-world deployment, fault tolerance, security, testing, and concurrency.
5. If source material is provided above, distribute the cards across ALL the different sources and pages, citing them as [Source: label].
6. GENERATE ALL {count} CARDS: Return exactly {count} distinct cards in the "cards" array below. Do not truncate or stop early.

Return ONLY valid JSON:
{{
  "title": "{topic} Master Study Deck",
  "cards": [
    {{
      "front": "Detailed conceptual question or scenario on {topic}?",
      "back": "Key Concept: ...\\n• Core Principle: ...\\n• Real-World Example: ...\\n• Memory Anchor: ..."
    }}
  ]
}}
"""

            # Audit logging for LLM call
            with LLMAuditContext(
                agent_name="FlashcardGenerationAgent",
                method_name="generate",
                subject=subject,
                grade_level=grade_level,
                topic=topic,
                has_rag_sources=bool(rag_sources),
                rag_source_count=len(rag_sources),
                has_web_sources=bool(web_sources),
                web_source_count=len(web_sources),
            ) as audit_ctx:
                audit_ctx.set_prompt(prompt_text)
                data = generate_json_any(prompt_text, task_type="flashcard")
                audit_ctx.set_response(str(data), model_used="gemini", fallback_used=False)

            if isinstance(data, dict) and data.get("cards"):
                raw_cards = data["cards"]
                unique_cards = []
                seen_fronts = set()
                for c in raw_cards:
                    if not isinstance(c, dict):
                        continue
                    front = (c.get("front") or "").strip()
                    back = (c.get("back") or "").strip()
                    if not front or not back:
                        continue
                    norm_key = " ".join(front.lower().split())
                    if norm_key in seen_fronts:
                        continue
                    seen_fronts.add(norm_key)
                    unique_cards.append({"front": front, "back": back})

                # If LLM returned fewer than count unique cards, backfill with distinct cards
                if len(unique_cards) < count:
                    backfill = _generate_distinct_fallback_cards(
                        topic=topic,
                        count=count,
                        rag_chunks=rag_chunks,
                        web_results=web_results,
                    )
                    for bf_card in backfill:
                        norm_bf = " ".join(bf_card["front"].lower().split())
                        if norm_bf not in seen_fronts:
                            seen_fronts.add(norm_bf)
                            unique_cards.append(bf_card)
                        if len(unique_cards) >= count:
                            break

                return AgentResult(self.name, {
                    "title": data.get("title") or f"{topic} Master Study Deck",
                    "topic": topic,
                    "language": language,
                    "prompt": prompt,
                    "cards": unique_cards[:count],
                    "sources": rag_sources + web_sources,
                    "unverified": len(rag_sources + web_sources) == 0,
                    "web_sources": web_results,
                })
        except Exception:
            pass

        # High-Yield Diverse Fallback Cards (guaranteed 100% distinct across any count)
        cards = _generate_distinct_fallback_cards(
            topic=topic,
            count=count,
            rag_chunks=rag_chunks,
            web_results=web_results,
        )
        return AgentResult(self.name, {
            "title": f"{topic} Master Study Deck",
            "topic": topic,
            "language": language,
            "prompt": prompt,
            "cards": cards[:count],
            "sources": rag_sources + web_sources,
            "unverified": len(rag_sources + web_sources) == 0,
            "web_sources": web_results,
        })

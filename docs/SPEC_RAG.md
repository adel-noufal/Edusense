# SPEC — Knowledge Base as a real local RAG (issue U8)

Status: specification written 2026-11-23. Implementation: **NOT DONE** (see
`docs/ISSUES.md` U8). This document is the contract the implementation and its
tests are measured against.

## 1. Goal and non-goals

**Goal.** The Knowledge Base answers questions about *the documents the instructor
uploaded*, offline by default, with page-level citations, and never invents an
answer the library does not support.

**Non-goals.** The AI Chatbot is a separate web assistant (`POST /api/ai/chat`)
and has no access to the library. The KB never generates quizzes, flashcards or
lessons unless the instructor clicks an explicit button.

## 2. Data model (canonical, stored once)

```
Document      { id, filename, sha256, pages, language, uploaded_at, status: pending|indexing|ready|failed,
                error, chunk_count, ingest_version }
Chunk         { id, document_id, page, section_path, heading, figure_ref,
                text, token_count, char_start, char_end, chunk_index }
Embedding     { chunk_id, model_name, model_version, dim, vector }   # collection v2, side by side
Answer        { id, question, rewritten_query, engine: local|cloud_boost, retrieved: [chunk_id],
                citations: [{document_id, page, section}], answer_markdown, language,
                sufficient_context: bool, latency_ms, model }
```

Rules:

- Nothing derived is recomputed at render time: a stored `Answer` is re-rendered,
  never re-generated when the page is reopened.
- `Document.status` drives the library badge, so a half-indexed PDF is visibly
  `indexing` instead of silently answering from partial chunks.

## 3. Ingestion

1. **Parse** page by page (`pypdf` for text plus structure heuristics; table text
   kept as rows; figure captions starting with `Figure (n)` / `Fig. n` captured
   as `figure_ref`).
2. **Segment** by heading hierarchy into `section_path` (`1.2 > Statistical tests
   for drift`), then chunk the section into 300–500 token windows with 60-token
   overlap, never crossing a heading boundary.
3. **Store** `chunk_index`, `char_start/char_end` so the UI can highlight the
   exact passage, and `page` so a citation can open the right page.
4. **Index status** per document: `pending → indexing → ready`, with `failed` and
   the parser error kept on the record.

Backwards compatibility: the existing collection stays untouched. A new
collection `kb_chunks_v2` is built beside it; switching is a config flag. Old
data is never deleted (user rule).

## 4. Embeddings

- **Local only by default.** Candidate models: the model currently in use, plus
  `bge-m3` and `multilingual-e5-base` (multilingual, Arabic-capable).
- **Decision rule:** run the evaluation set (§8) with each model; adopt a new
  model only if hit@5 improves by ≥ 5 points *and* Arabic retrieval does not
  regress. The comparison table is committed to `docs/rag_eval.json`.
- Embeddings run on the CPU host; a document of ≤ 300 chunks must index in
  under 10 minutes, otherwise batching is adjusted (never silently truncated).

## 5. Retrieval

1. **Exact-passage mode (must work).** If the user message contains a quoted span
   of ≥ 12 words, do a lexical (BM25) search for that span first. If a chunk
   contains it (normalised whitespace, ≥ 80 % of the span matched), answer *that
   passage*: explain it, cite `[file p.N]`, and include the neighbouring chunk for
   context. This is the case that produced the useless reply in U8.
2. **Hybrid.** BM25 + vector search, merged with reciprocal-rank fusion, then a
   local cross-encoder reranker (`bge-reranker-base`, offline) keeps the top 5.
3. **Structured queries.** `page 40`, `figure 17`, `chapter 3`, `section 2.4`
   are parsed into filters and answered from the matching chunks.
4. **Follow-up rewriting.** A short local rewrite of the user message using the
   last 6 turns, so "and the second one?" resolves to the previous subject.
5. **Threshold.** If the best reranked score is below the calibrated cutoff, the
   answer says what was found and what is missing instead of guessing.

## 6. Generation

- **Default engine: Local** (Ollama). `qwen2.5` for Arabic or mixed input,
  `llama3.1` for English. Timeouts follow the existing 300 s local floor.
- **Cloud boost** is off by default; turning it on shows a warning that document
  snippets leave the machine, and the engine is stored with the answer.
- **Grounded prompt:** answer only from the retrieved context; quote the key
  phrases verbatim; cite `[file p.N]`; state insufficiency explicitly; answer in
  the question's language; never claim earlier interactions; output Markdown.
- Rendered as Markdown (headings, lists, tables, fenced code) — never raw `**`.

## 7. UI

- Library: per-document status, chunk count, pages, index time.
- Answer: Markdown; citation chips (file + page) open the source page with the
  passage highlighted; collapsible *Show retrieved context*; UTC timestamps
  rendered in the browser timezone (U2).
- **No unrequested generation:** loading the page, the library, or typing makes
  **zero** LLM calls. A test counts the calls and asserts 0.
- Suggestion chips are derived deterministically from the document's own
  headings (`Explain: <heading>`) or absent. No hardcoded topic chips.
- No pre-filled engine text; the control reads `Local (default)` / `Cloud boost`.

## 8. Evaluation (`docs/rag_eval.json`)

20 questions about `ECU-ITAI-3-04.pdf`: 5 pasted-passage, 4 page-specific, 3
figure-specific, 3 list-all ("list every statistical test for drift"), 3
definition, 2 chapter-structure, plus 5 questions **not** in the book.

| Metric | Target |
|---|---|
| hit@5 on answerable questions | ≥ 85 % |
| Faithfulness (judge on a different provider than the answerer + citation check) | ≥ 90 % of claims supported |
| Refusal on the 5 negatives | ≥ 90 % |
| Citation correctness (file + page exists and supports the sentence) | 100 % of shown citations |

The runner prints the metric table, the comparison of embedding models, and 5
full answers verbatim. Iterate chunking → fusion weights → reranker → prompt
until the targets hold, then stop; if a target cannot be met on this host, the
blocker and the measured number are reported instead.

## 9. Acceptance criteria

1. Pasting the U8 passage yields an explanation of *that passage* with page
   citations, quoting its key phrases.
2. Page/figure/list questions answer from the right chunk.
3. Arabic question about an Arabic document answers in Arabic.
4. Opening the KB performs 0 LLM calls.
5. Markdown, tables, code, citation chips render; no `**` visible.
6. All numbers in §8 printed and met, or explicitly reported as not met.

## 10. Risks

- **CPU-only host:** local embeddings and the reranker are slow; index time may
  exceed the rule in §4 and the eval needs minutes, not seconds.
- **PDF structure:** scans without a text layer produce empty chunks — the
  document must then be marked `failed` with a clear message, not indexed empty.
- **Arabic tokenisation** in BM25 is weaker than English; this is why the
  embedding comparison includes Arabic before adoption.
- **Judge independence:** using the same provider for answer and judgement makes
  faithfulness meaningless; the judge must be a different provider or Ollama.

## 11. Free resources

Local embeddings, the reranker, Chroma, pypdf and Ollama are free and already
installed or installable offline. No paid API is needed for the default path.

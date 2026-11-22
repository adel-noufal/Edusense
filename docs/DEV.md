# Developer notes — demo accounts (DEMO ONLY)

> **These accounts exist only for local development and demos.** They are seeded when
> `EDUSENSE_DISABLE_DEFAULT_ACCOUNTS` is unset/false. Set it to `true` before deploying
> anywhere reachable by other people, and create real accounts instead.

| Role | Email | Password |
| --- | --- | --- |
| Instructor | `instructor@edusense.local` | `Password123` |
| Student | `student@edusense.local` | `Password123` |

## Local workflow

```bat
cd backend
.venv\Scripts\python.exe -m app.tools.doctor
.venv\Scripts\python.exe -m pytest -q -m "not live_provider"
.venv\Scripts\python.exe scripts\llm_diagnostic.py            :: masked keys + routing chains
.venv\Scripts\python.exe scripts\llm_diagnostic.py --test-all :: live probe
```

```bat
:: Encoding gate (also part of verify.bat and CI)
backend\.venv\Scripts\python.exe scripts\mojibake_scan.py
```

## Notes on the Knowledge Base

The Chroma collection `edusense_knowledge` was built with `sentence_transformer`
(`all-MiniLM-L6-v2`, 384 dimensions). `vector_store.init_collection()` now opens an existing
collection **with its persisted embedding function** and raises a readable error instead of
silently switching to ONNX. If the venv is rebuilt, reinstall from `requirements.txt` rather
than mixing versions; re-indexing is only needed if you intentionally change the embedding
model.

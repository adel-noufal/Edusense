import asyncio

from app.agents.orchestrator import AgentOrchestrator
from app.services import rag_qa


def test_named_document_question_uses_document_chunks_and_cites_source(monkeypatch):
    source_name = "ECU-ITAI-3-04.pdf"
    stored_chunks = [
        {
            "id": f"chunk-{index}",
            "text": f"Document section {index} explains artificial intelligence topic {index}.",
            "metadata": {
                "source_file": source_name,
                "page": index + 1,
                "chunk_index": index,
            },
            "distance": None,
        }
        for index in range(10)
    ]
    monkeypatch.setattr(rag_qa, "get_indexed_sources", lambda: [{
        "source_id": source_name,
        "source_file": source_name,
        "chunk_count": len(stored_chunks),
    }])
    monkeypatch.setattr(rag_qa, "RAG_Search_Tool", lambda **kwargs: [])
    monkeypatch.setattr(rag_qa.vector_store, "get_by_source", lambda source_id: stored_chunks)
    query_calls = []
    prompts = []

    def scoped_query(**kwargs):
        query_calls.append(kwargs)
        return []

    def answer_document(prompt, **kwargs):
        prompts.append(prompt)
        return (
            "The PDF introduces artificial intelligence and its applications. [Source: ECU-ITAI-3-04.pdf p.1]",
            "test",
            False,
        )

    monkeypatch.setattr(rag_qa.vector_store, "query", scoped_query)
    monkeypatch.setattr(rag_qa, "_call_llm", answer_document)

    result = rag_qa.answer_question(
        f"From this PDF, what is it talking about? {source_name}",
        top_k=3,
    )

    assert result["chunks_used"] == 3
    assert result["sources"][0]["source_file"] == source_name
    assert source_name in result["answer"]
    assert "refuse" not in result["answer"].lower()
    assert "Document section 0" in prompts[0]
    assert "Document section 9" in prompts[0]
    assert query_calls[0]["metadata_filter"] == {"source_file": source_name}
    assert "what is it talking about" in query_calls[0]["query_text"].lower()


def test_general_knowledge_question_answers_in_online_general_mode(monkeypatch):
    orchestrator = AgentOrchestrator()
    monkeypatch.setattr(orchestrator, "_is_online", lambda: True)
    monkeypatch.setattr(
        orchestrator,
        "_build_rag_context",
        lambda *args, **kwargs: asyncio.sleep(0, result=("", [], 0)),
    )
    monkeypatch.setattr(
        orchestrator,
        "_build_web_context",
        lambda *args, **kwargs: asyncio.sleep(0, result=("", [], 0)),
    )
    prompts = []

    def generate(prompt, **kwargs):
        prompts.append(prompt)
        return "Artificial intelligence is the field of creating systems that perform tasks requiring human-like intelligence."

    monkeypatch.setattr(orchestrator.llm, "generate", generate)

    result = asyncio.run(orchestrator._run_async("What is AI?"))

    assert result.mode == "online_general_llm"
    assert "Artificial intelligence" in result.answer
    assert "don't have verified source material" not in prompts[0].lower()
    assert "answer general-knowledge questions from your own knowledge" in prompts[0].lower()


def test_chatbot_selected_source_restricts_rag_to_that_document(monkeypatch):
    orchestrator = AgentOrchestrator()
    calls = []
    selected_chunk = {
        "text": "Selected PDF content",
        "metadata": {"source_file": "selected.pdf", "page": 2},
        "distance": 0.1,
    }

    async def scoped_lookup(func, timeout, *args, **kwargs):
        calls.append(kwargs)
        return [selected_chunk]

    monkeypatch.setattr("app.agents.orchestrator._run_with_timeout", scoped_lookup)

    context, sources, count = asyncio.run(
        orchestrator._build_rag_context(
            "Explain this topic",
            subject=None,
            grade_level=None,
            source_id="selected.pdf",
        )
    )

    assert calls == [{"query_text": "Explain this topic", "top_k": 5, "metadata_filter": {"source_file": "selected.pdf"}}]
    assert "Selected PDF content" in context
    assert sources == ["selected.pdf p.2"]
    assert count == 1


def test_rebuild_video_updates_narration_duration_and_player(monkeypatch, tmp_path):
    from app.services import video

    monkeypatch.setattr(video, "STATIC_DIR", tmp_path)

    def write_audio(text, output_path, lang):
        output_path.write_bytes(f"new audio: {text}".encode("utf-8").ljust(128, b"!"))
        return True

    monkeypatch.setattr(video, "_gtts_scene", write_audio)
    monkeypatch.setattr(video, "_probe_audio_duration", lambda _: 13.4)
    monkeypatch.setattr(video, "_try_ffmpeg", lambda *args, **kwargs: None)

    result = video.rebuild_video_from_scenes(
        project_id=9123,
        title="Edited Lesson",
        language="English",
        scenes=[{
            "title": "Revised scene",
            "narration": "A clearly revised narration for the saved video.",
            "content": "A clearly revised narration for the saved video.",
            "duration_seconds": 8,
        }],
    )

    project_dir = tmp_path / "video-9123"
    player = (project_dir / "player.html").read_text(encoding="utf-8")
    saved_scenes = (project_dir / "scenes.json").read_text(encoding="utf-8")
    # Scene length is the measured narration (13.4 s) plus the short slide pause.
    assert result["scenes"][0]["duration_seconds"] == 15
    assert "A clearly revised narration for the saved video." in player
    assert 'data-dur="15000"' in player
    assert "A clearly revised narration for the saved video." in saved_scenes
    assert (project_dir / "segment-0-audio.mp3").read_bytes().startswith(b"new audio:")

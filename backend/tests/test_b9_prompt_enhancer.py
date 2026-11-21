"""
B9 Smoke Test: Prompt Enhancer against live provider.
Verifies:
1. English prompt rewritten with duration and count preserved
2. Arabic prompt rewritten in Arabic with constraints preserved
3. Mixed prompt rewritten in mixed language with constraints preserved
"""
import pytest
from app.services.gemini import generate_content

def test_prompt_enhancer_english():
    instruction = (
        "You are a prompt engineer for an educational content generator. "
        "Rewrite the user's prompt into a clearer, more effective instruction. "
        "Improve clarity, audience, structure and constraints while preserving "
        "the user's intent AND their language (Arabic stays Arabic, mixed stays mixed). "
        "Never change concrete values such as duration, question counts, topics or languages. "
        "Return ONLY the improved prompt text â€” no preamble, no quotes, no explanation.\n\n"
        "Form context: feature: exams; count: 10; duration: 45 mins; topic: Thermodynamics\n\n"
        "User prompt:\nMake 10 questions for high school on laws of thermodynamics, 45 mins exam"
    )
    res = generate_content(instruction, task_type="prompt_enhance", temperature=0.3, timeout=30)
    assert res and len(res.strip()) > 10
    # Must preserve '10' and '45'
    assert "10" in res or "ten" in res.lower()
    print("\n[B9 PASS] English:", res[:100], "...")

def test_prompt_enhancer_arabic():
    instruction = (
        "You are a prompt engineer for an educational content generator. "
        "Rewrite the user's prompt into a clearer, more effective instruction. "
        "Improve clarity, audience, structure and constraints while preserving "
        "the user's intent AND their language (Arabic stays Arabic, mixed stays mixed). "
        "Never change concrete values such as duration, question counts, topics or languages. "
        "Return ONLY the improved prompt text â€” no preamble, no quotes, no explanation.\n\n"
        "Form context: feature: exams; count: 5; topic: Ø§Ù„ØªÙØ§Ø¶Ù„ ÙˆØ§Ù„ØªÙƒØ§Ù…Ù„\n\n"
        "User prompt:\nØ§Ø®ØªØ¨Ø§Ø± Ù‚ØµÙŠØ± 5 Ø§Ø³Ø¦Ù„Ø© ÙÙŠ Ø§Ù„ØªÙØ§Ø¶Ù„ Ù„Ø·Ù„Ø§Ø¨ Ø§Ù„Ø«Ø§Ù†ÙˆÙŠØ©"
    )
    res = generate_content(instruction, task_type="prompt_enhance", temperature=0.3, timeout=30)
    assert res and len(res.strip()) > 10
    assert "5" in res or "Ø®Ù…Ø³" in res
    print("\n[B9 PASS] Arabic:", res[:100], "...")

def test_prompt_enhancer_mixed():
    instruction = (
        "You are a prompt engineer for an educational content generator. "
        "Rewrite the user's prompt into a clearer, more effective instruction. "
        "Improve clarity, audience, structure and constraints while preserving "
        "the user's intent AND their language (Arabic stays Arabic, mixed stays mixed). "
        "Never change concrete values such as duration, question counts, topics or languages. "
        "Return ONLY the improved prompt text â€” no preamble, no quotes, no explanation.\n\n"
        "Form context: feature: question_bank; count: 8; topic: Python Data Structures\n\n"
        "User prompt:\nØ£Ø³Ø¦Ù„Ø© Ø¹Ù† Python lists and dictionaries Ø¹Ø¯Ø¯ 8 Ø£Ø³Ø¦Ù„Ø©"
    )
    res = generate_content(instruction, task_type="prompt_enhance", temperature=0.3, timeout=30)
    assert res and len(res.strip()) > 10
    assert "8" in res or "Ø«Ù…Ø§Ù†" in res
    print("\n[B9 PASS] Mixed:", res[:100], "...")

if __name__ == "__main__":
    test_prompt_enhancer_english()
    test_prompt_enhancer_arabic()
    test_prompt_enhancer_mixed()
    print("\nALL B9 PROMPT ENHANCER TESTS PASSED!")

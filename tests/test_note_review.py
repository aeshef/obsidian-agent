from knowledge_bot.app.handlers.review import generate_note_review


def test_generate_note_review_ocr_sample():
    routed = {"type": "мысль", "title": "Test", "tags": ["domain/life"]}
    summary = {
        "derived": {
            "ocr_text": "Это достаточно длинный OCR текст для ревью заметки с нормальным содержанием.",
        }
    }
    text = generate_note_review(routed, summary)
    assert "📋 Тип: мысль" in text
    assert "OCR (семпл)" in text
    assert "Failed" not in text

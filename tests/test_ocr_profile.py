from pathlib import Path
from unittest.mock import MagicMock, patch

from knowledge_bot.services.extract.ocr import _should_run_easyocr, extract_from_image


def test_should_run_easyocr_skips_when_tesseract_enough(tmp_path: Path):
    img = tmp_path / "t.jpg"
    img.write_bytes(b"\xff\xd8\xff")  # not valid jpeg but size check uses PIL open - mock
    with patch("knowledge_bot.services.extract.ocr.PIL") as pil:
        pil.Image.open.return_value.size = (320, 180)
        assert not _should_run_easyocr(img, "x" * 50)


def test_extract_from_image_thumbnail_skips_easyocr(tmp_path: Path):
    img = tmp_path / "thumb.jpg"
    with patch("knowledge_bot.services.extract.ocr.PIL") as pil:
        mock_img = MagicMock()
        mock_img.size = (320, 180)
        mock_img.mode = "RGB"
        pil.Image.open.return_value = mock_img
        pil.Image.LANCZOS = 1
        with patch("knowledge_bot.services.extract.ocr._ocr_tesseract", return_value="hello") as tess:
            with patch("knowledge_bot.services.extract.ocr._ocr_easyocr") as easy:
                out = extract_from_image(img, profile="thumbnail")
                assert out == "hello"
                tess.assert_called_once()
                easy.assert_not_called()

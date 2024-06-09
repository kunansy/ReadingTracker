from pathlib import Path

import pytest

from tracker.notes import speech_recognizer


@pytest.mark.parametrize(
    ("results", "expected"),
    [
        (
            {"alternative": [{"transcript": "Hello World", "confidence": 0.42}]},
            {"transcript": "Hello world", "confidence": 42.0},
        ),
        (
            {
                "alternative": [
                    {"transcript": "Hello World", "confidence": 0.42},
                    {"transcript": "Hello World2", "confidence": 0.52},
                    {"transcript": "Hello World3", "confidence": 0.3},
                ],
            },
            {"transcript": "Hello world2", "confidence": 52.0},
        ),
    ],
)
def test_get_best_result(results, expected):
    assert speech_recognizer.get_best_result(results).model_dump() == expected


def test_get_best_result_no_results():
    with pytest.raises(ValueError) as e:
        speech_recognizer.get_best_result({"error": "not found"})

    assert str(e.value) == "No results found"


def test_recognize():
    src = Path("tests/test_transcript_src.wav").read_bytes()
    dst = Path("tests/test_transcript.wav").read_bytes()

    file = speech_recognizer.get_file_content(src)
    path = speech_recognizer.dump(file)
    speech_recognizer.fix_file_format(path)

    assert path.read_bytes() == dst

    audio = speech_recognizer.read_file(path)

    result = speech_recognizer.recognize(audio)
    best = speech_recognizer.get_best_result(result)

    assert best.model_dump() == {
        "transcript": "Этот файл записывается для теста и будет сохранён в test",
        "confidence": 88.91,
    }


def test_remove():
    src = Path("tests/test_transcript_src.wav").read_bytes()
    dst = Path("tests/test_remove.wav")

    with dst.open("wb") as f:
        f.write(src)

    assert dst.exists()
    speech_recognizer.remove(dst)
    assert not dst.exists()

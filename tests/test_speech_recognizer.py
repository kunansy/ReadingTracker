from tracker.notes import speech_recognizer

import pytest


@pytest.mark.parametrize(
    "results, expected", (
        ({"alternative": [{"transcript": "Hello World", "confidence": 0.42}]},
         {"transcript": "Hello world", "confidence": 42.0}),
        ({"alternative": [{"transcript": "Hello World", "confidence": 0.42}, {"transcript": "Hello World2", "confidence": 0.52}, {"transcript": "Hello World3", "confidence": 0.3}]},
         {"transcript": "Hello world2", "confidence": 52.0}),
    )
)
def test_get_best_result(results, expected):
    assert speech_recognizer.get_best_result(results).model_dump() == expected


def test_get_best_result_no_results():
    with pytest.raises(ValueError) as e:
        speech_recognizer.get_best_result({"error": "not found"})

    assert str(e.value) == "No results found"

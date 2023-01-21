import pytest
from tracker.notes import schemas


@pytest.mark.parametrize(
    "string,expected", (
        ('Hg ff "dd"', "Hg ff «dd»"),
        ('Hg "ff" dd', "Hg «ff» dd"),
        ('"Hg" ff dd', "«Hg» ff dd"),
        ('"Hg ff dd"', "«Hg ff dd»"),
        ('"Hg" ff "dd"', "«Hg» ff «dd»"),
        # quotes inside quotes not processed
        ('"Hg "ff" dd"', "«Hg »ff« dd»"),
        ('""', "«»"),
        ('', ""),
    )
)
def test_replace_quotes(string, expected):
    assert schemas._replace_quotes(string) == expected


@pytest.mark.parametrize(
    "string", (
        'Hg ff dd"',
        'Hg "ff dd',
        '"Hg ff dd',
        'Hg" ff "dd"',
        'Hg" "ff" "dd"',
        '"""',
    )
)
def test_replace_quotes_error(string):
    with pytest.raises(AssertionError):
        assert schemas._replace_quotes(string)

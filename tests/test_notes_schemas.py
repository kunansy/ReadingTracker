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
        ('', ''),
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


@pytest.mark.parametrize(
    "string,expected", (
        ('Hg', 'Hg.'),
        ('Hg!', 'Hg!'),
        ('Hg?', 'Hg?'),
        ('Hg:', 'Hg:.'),
        ('(Hg)', '(Hg).'),
        ('Hg...', 'Hg...'),
        ('', ''),
    )
)
def test_add_dot(string, expected):
    assert schemas._add_dot(string) == expected


@pytest.mark.parametrize(
    "string,expected", (
        ('Hg', 'Hg'),
        ('hg!', 'Hg!'),
        ('a', 'A'),
        ('A', 'A'),
        ('', ''),
    )
)
def test_up_first_letter(string, expected):
    assert schemas._up_first_letter(string) == expected

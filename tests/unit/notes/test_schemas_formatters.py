import pytest

from tracker.notes import schemas


@pytest.mark.parametrize(
    ("string", "expected"),
    [
        ('Hg ff "dd"', "Hg ff «dd»"),
        ('Hg "ff" dd', "Hg «ff» dd"),
        ('"Hg" ff dd', "«Hg» ff dd"),
        ('"Hg ff dd"', "«Hg ff dd»"),
        ('"Hg" ff "dd"', "«Hg» ff «dd»"),
        ('"Hg "ff" dd"', "«Hg »ff« dd»"),
        ('""', "«»"),
        ('""""', "«»«»"),
        ("", ""),
        ("no quotes at all", "no quotes at all"),
        ('"Привет", сказал он', "«Привет», сказал он"),
        ("'single' quotes stay", "'single' quotes stay"),
    ],
    ids=[
        "at-end",
        "in-middle",
        "at-start",
        "whole-string",
        "two-pairs",
        "nested-are-paired-in-order",
        "empty-pair",
        "two-empty-pairs",
        "empty-string",
        "zero-quotes",
        "cyrillic",
        "single-quotes-ignored",
    ],
)
def test_replace_quotes_pairs_double_quotes(string, expected):
    assert schemas._replace_quotes(string) == expected


@pytest.mark.parametrize(
    "string",
    ['Hg ff dd"', 'Hg "ff dd', '"Hg ff dd', 'Hg" ff "dd"', 'Hg" "ff" "dd"', '"""', '"'],
)
def test_replace_quotes_rejects_unbalanced_quotes(string):
    with pytest.raises(AssertionError, match="Quotes are not balanced"):
        schemas._replace_quotes(string)


@pytest.mark.parametrize(
    ("string", "expected"),
    [
        ("", ""),
        (".", "."),
        ("?", "?"),
        ("!", "!"),
        ("text.", "text."),
        ("text?", "text?"),
        ("text!", "text!"),
        ("text", "text."),
        ("text,", "text,."),
        ("text…", "text…."),
        ("text. ", "text. ."),
        ("текст", "текст."),
    ],
    ids=[
        "empty",
        "only-dot",
        "only-question",
        "only-exclamation",
        "ends-with-dot",
        "ends-with-question",
        "ends-with-exclamation",
        "plain",
        "comma",
        "ellipsis-char",
        "trailing-space",
        "cyrillic",
    ],
)
def test_add_dot(string, expected):
    assert schemas.add_dot(string) == expected


@pytest.mark.parametrize(
    ("string", "expected"),
    [
        ("", ""),
        ("Hg", "Hg"),
        ("hg!", "Hg!"),
        ("a", "A"),
        ("A", "A"),
        ("1a", "1a"),
        ("привет", "Привет"),
        ("Привет", "Привет"),
        (" a", " a"),
        ("«a»", "«a»"),
        ("ß", "SS"),
    ],
    ids=[
        "empty",
        "upper",
        "lower",
        "single-lower",
        "single-upper",
        "digit",
        "cyrillic-lower",
        "cyrillic-upper",
        "leading-space",
        "leading-quote",
        "multi-char-uppercase",
    ],
)
def test_up_first_letter(string, expected):
    assert schemas._up_first_letter(string) == expected


@pytest.mark.parametrize(
    ("string", "expected"),
    [
        ("some -- text", "some — text"),
        ("some – text", "some — text"),  # noqa: RUF001
        ("some <-> text", "some ↔ text"),
        ("some -> text", "some → text"),
        ("some <- text", "some ← text"),
        ("a->b", "a->b"),
        ("a --b", "a --b"),
        ("a -> b -> c", "a → b → c"),
        ("some --- text", "some --- text"),
        ("", ""),
    ],
    ids=[
        "double-hyphen",
        "en-dash",
        "both-arrows",
        "right-arrow",
        "left-arrow",
        "no-spaces",
        "space-on-one-side",
        "repeated",
        "triple-hyphen",
        "empty",
    ],
)
def test_replace_punctuation_between_spaces(string, expected):
    assert schemas._replace_punctuation(string) == expected


@pytest.mark.parametrize(
    ("symbols", "expected"),
    [
        (["->", "<-", "--", "–", "<->"], " → ← — — ↔ "),  # noqa: RUF001
        (["<->", "–", "--", "<-", "->"], " ↔ — — ← → "),  # noqa: RUF001
    ],
)
def test_replace_punctuation_any_order(symbols, expected):
    string = " ".join(symbols)

    assert schemas._replace_punctuation(f" {string} ") == expected


@pytest.mark.parametrize(
    ("string", "expected"),
    [
        ("-- some -- text", "-- some — text"),
        ("<-> some <-> text", "<-> some ↔ text"),
        ("-> some -> text", "-> some → text"),
        ("<- some <- text", "<- some ← text"),
        ("some text ->", "some text ->"),
        ("a -> -> b", "a → -> b"),
    ],
    ids=[
        "hyphens-at-start",
        "both-at-start",
        "right-arrow-at-start",
        "left-arrow-at-start",
        "at-end",
        "adjacent",
    ],
)
def test_replace_punctuation_skips_string_edges_and_adjacent_tokens_current_behaviour(
    string,
    expected,
):
    assert schemas._replace_punctuation(string) == expected


@pytest.mark.parametrize(
    ("string", "expected"),
    [
        ("\\inf some text", "∞ some text"),
        ("some \\inf text", "some ∞ text"),
        ("some text \\inf", "some text ∞"),
        ("\\inf some \\inf text \\inf", "∞ some ∞ text ∞"),
        ("\\inf", "∞"),
        ("\\infinity", "∞inity"),
        ("inf", "inf"),
        ("", ""),
    ],
)
def test_replace_inf(string, expected):
    assert schemas._replace_inf(string) == expected


@pytest.mark.parametrize(
    ("string", "expected"),
    [
        ("some^42 text", "some<sup>42</sup> text"),
        ("some^-1042 text", "some<sup>-1042</sup> text"),
        ("some^text text", "some<sup>text</sup> text"),
        ("x^2 + y^3 = z", "x<sup>2</sup> + y<sup>3</sup> = z"),
        ("x^2\ny", "x<sup>2</sup>\ny"),
        ("x^2^3 y", "x<sup>2^3</sup> y"),
        ("some ^ text", "some ^ text"),
        ("some ^text", "some ^text"),
        ("^ some ^text ^", "^ some ^text ^"),
        ("", ""),
    ],
)
def test_replace_up_index(string, expected):
    assert schemas._replace_up_index(string) == expected


@pytest.mark.parametrize("string", ["x^2", "area is m^2"])
def test_replace_up_index_at_end_of_content_is_not_converted_current_behaviour(string):
    assert schemas._replace_up_index(string) == string


@pytest.mark.parametrize(
    ("string", "expected"),
    [
        ("some &gt; text", "some > text"),
        ("some text &gt;", "some text >"),
        ("&gt; some text", "> some text"),
        ("&gt; some text &gt;", "> some text >"),
        ("&gt;some text&gt;", ">some text>"),
        ("&GT; &gt", "&GT; &gt"),
        ("", ""),
    ],
)
def test_dereplace_gt(string, expected):
    assert schemas._dereplace_gt(string) == expected


@pytest.mark.parametrize(
    ("string", "expected"),
    [
        ("some &lt; text", "some < text"),
        ("some text &lt;", "some text <"),
        ("&lt; some text", "< some text"),
        ("&lt; some text &lt;", "< some text <"),
        ("&lt;some text&lt;", "<some text<"),
        ("&LT; &lt", "&LT; &lt"),
        ("", ""),
    ],
)
def test_dereplace_lt(string, expected):
    assert schemas._dereplace_lt(string) == expected


@pytest.mark.parametrize(
    ("string", "expected"),
    [
        ("`some` \n **text** &gt;*to* test &lt;", "`some` \n **text** >*to* test <"),
        ("`some` \n **text** >*to* test <", "`some` \n **text** >*to* test <"),
        ("&lt;b&gt;bold&lt;/b&gt;", "<b>bold</b>"),
        ("&amp;lt;", "&amp;lt;"),
        ("", ""),
    ],
)
def test_demark_note(string, expected):
    assert schemas.demark_note(string) == expected


def test_notes_formatters_run_in_declared_order():
    assert schemas.NOTES_FORMATTERS == (
        schemas._replace_quotes,
        schemas._up_first_letter,
        schemas._replace_punctuation,
        schemas._replace_up_index,
        schemas._replace_inf,
    )
    assert schemas.NOTES_DEMARKERS == (schemas._dereplace_lt, schemas._dereplace_gt)


def test_all_formatters_compose_on_one_string():
    content = 'he said "x^2 -> \\inf" -- ok'

    for formatter in schemas.NOTES_FORMATTERS:
        content = formatter(content)

    assert content == "He said «x<sup>2</sup> → ∞» — ok"


@pytest.mark.parametrize(
    ("string", "link_id"),
    [
        (
            "valid uuid4 [[fde197da-0c98-451e-a3aa-eb86116ab964]]",
            "fde197da-0c98-451e-a3aa-eb86116ab964",
        ),
        (
            "valid нулевой uuid [[00000000-0000-0000-0000-000000000000]]",
            "00000000-0000-0000-0000-000000000000",
        ),
        (
            "valid uuid6 [[1eed93d0-4ee8-6fb2-93f6-a18e7cec9d61]]",
            "1eed93d0-4ee8-6fb2-93f6-a18e7cec9d61",
        ),
        (
            "[[fde197da-0c98-451e-a3aa-eb86116ab964]] some text",
            "fde197da-0c98-451e-a3aa-eb86116ab964",
        ),
        (
            "some text [[fde197da-0c98-451e-a3aa-eb86116ab964]] some text",
            "fde197da-0c98-451e-a3aa-eb86116ab964",
        ),
        (
            "upper [[FDE197DA-0C98-451E-A3AA-EB86116AB964]]",
            "FDE197DA-0C98-451E-A3AA-EB86116AB964",
        ),
    ],
)
def test_link_pattern_finds_uuid(string, link_id):
    assert schemas.LINK_PATTERN.search(string).group(1) == link_id


def test_link_pattern_finds_every_link():
    string = (
        "[[fde197da-0c98-451e-a3aa-eb86116ab964]] and "
        "[[1eed93d0-4ee8-6fb2-93f6-a18e7cec9d61]]"
    )

    assert schemas.LINK_PATTERN.findall(string) == [
        "fde197da-0c98-451e-a3aa-eb86116ab964",
        "1eed93d0-4ee8-6fb2-93f6-a18e7cec9d61",
    ]


@pytest.mark.parametrize(
    "string",
    [
        "some text [[invalid-uuid]]",
        "текст [[плохой юид]]",
        "[fde197da-0c98-451e-a3aa-eb86116ab964]",
        "[[fde197da0c98451ea3aaeb86116ab964]]",
        "[[fde197da-0c98-451e-a3aa-eb86116ab96]]",
        "[[fde197da-0c98-451e-a3aa-eb86116ab9644]]",
        "[[gde197da-0c98-451e-a3aa-eb86116ab964]]",
        "[[ fde197da-0c98-451e-a3aa-eb86116ab964 ]]",
        "[[]]",
        "",
    ],
    ids=[
        "not-uuid",
        "cyrillic",
        "single-brackets",
        "no-hyphens",
        "one-char-short",
        "one-char-long",
        "non-hex",
        "padded",
        "empty-brackets",
        "empty",
    ],
)
def test_link_pattern_rejects_non_uuid(string):
    assert schemas.LINK_PATTERN.search(string) is None


@pytest.mark.parametrize(
    "tag",
    ["a", "a_b", "tag1", "1", "тег", "Tag", "_"],
)
def test_tag_pattern_accepts_word_characters(tag):
    assert schemas.TAG_PATTERN.match(tag).group(1) == tag


@pytest.mark.parametrize(
    "tag",
    ["", "a-b", "a b", " a", "a ", "#a", "a.b", "a,b"],
    ids=["empty", "hyphen", "space", "leading-space", "trailing-space", "hash", "dot", "comma"],
)
def test_tag_pattern_rejects_other_characters(tag):
    assert schemas.TAG_PATTERN.match(tag) is None


def test_tag_pattern_accepts_trailing_newline_current_behaviour():
    assert schemas.TAG_PATTERN.match("a\n") is not None

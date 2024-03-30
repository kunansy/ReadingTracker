import pytest

from tracker.notes import schemas
from tracker.notes.db import Note as NoteDb


@pytest.mark.parametrize(
    "string,expected",
    (
        ('Hg ff "dd"', "Hg ff «dd»"),
        ('Hg "ff" dd', "Hg «ff» dd"),
        ('"Hg" ff dd', "«Hg» ff dd"),
        ('"Hg ff dd"', "«Hg ff dd»"),
        ('"Hg" ff "dd"', "«Hg» ff «dd»"),
        # quotes inside quotes not processed
        ('"Hg "ff" dd"', "«Hg »ff« dd»"),
        ('""', "«»"),
        ("", ""),
    ),
)
def test_replace_quotes(string, expected):
    assert schemas._replace_quotes(string) == expected


@pytest.mark.parametrize(
    "string",
    (
        'Hg ff dd"',
        'Hg "ff dd',
        '"Hg ff dd',
        'Hg" ff "dd"',
        'Hg" "ff" "dd"',
        '"""',
    ),
)
def test_replace_quotes_error(string):
    with pytest.raises(AssertionError):
        assert schemas._replace_quotes(string)


@pytest.mark.parametrize(
    "string,expected",
    (
        ("Hg", "Hg."),
        ("Hg!", "Hg!"),
        ("Hg?", "Hg?"),
        ("Hg:", "Hg:."),
        ("(Hg)", "(Hg)."),
        ("Hg...", "Hg..."),
        ("", ""),
    ),
)
def test_add_dot(string, expected):
    assert schemas.add_dot(string) == expected


@pytest.mark.parametrize(
    "string,expected",
    (
        ("Hg", "Hg"),
        ("hg!", "Hg!"),
        ("a", "A"),
        ("A", "A"),
        ("", ""),
    ),
)
def test_up_first_letter(string, expected):
    assert schemas._up_first_letter(string) == expected


@pytest.mark.parametrize(
    "string,expected",
    (
        ("<span class=\"font-weight-bold\">some text</span>", "**some text**"),
        ("<span class=font-weight-bold>some text</span>", "**some text**"),
        ("<span class=font-weight-bold>some text634852^^&**#$Q( aa</span>", "**some text634852^^&**#$Q( aa**"),
    ),
)
def test_demark_bold(string, expected):
    # '<span class="?{BOLD_MARKER}"?>(.*?)</span>
    assert schemas._demark_bold(string) == expected


@pytest.mark.parametrize(
    "string,expected",
    (
        ("<span class=\"font-italic\">some text</span>", "*some text*"),
        ("<span class=font-italic>some text</span>", "*some text*"),
        ("<span class=font-italic>some text634852^^&**#$Q( aa</span>", "*some text634852^^&**#$Q( aa*"),
    ),
)
def test_demark_italic(string, expected):
    assert schemas._demark_italic(string) == expected


@pytest.mark.parametrize(
    "string,expected",
    (
        ("<span class=\"font-code\">some text</span>", "`some text`"),
        ("<span class=font-code>some text</span>", "`some text`"),
        ("<span class=font-code>some text634852^^&**#$Q( aa</span>", "`some text634852^^&**#$Q( aa`"),
    ),
)
def test_demark_code(string, expected):
    assert schemas._demark_code(string) == expected


@pytest.mark.parametrize(
    "string,expected",
    (
        ("some &gt; text", "some > text"),
        ("some text &gt;", "some text >"),
        ("&gt; some text", "> some text"),
        ("&gt; some text &gt;", "> some text >"),
        ("&gt;some text&gt;", ">some text>"),
    ),
)
def test_dereplace_gt(string, expected):
    assert schemas._dereplace_gt(string) == expected


@pytest.mark.parametrize(
    "string,expected",
    (
        ("some &lt; text", "some < text"),
        ("some text &lt;", "some text <"),
        ("&lt; some text", "< some text"),
        ("&lt; some text &lt;", "< some text <"),
        ("&lt;some text&lt;", "<some text<"),
    ),
)
def test_dereplace_lt(string, expected):
    assert schemas._dereplace_lt(string) == expected


@pytest.mark.parametrize(
    "string,expected",
    (
        ("some <br> text", "some \n text"),
        ("some <br/> text", "some \n text"),
        ("some text<br>", "some text\n"),
        ("<br>some text", "\nsome text"),
        ("<br>some text<br>", "\nsome text\n"),
    ),
)
def test_dereplace_new_lines(string, expected):
    assert schemas.dereplace_new_lines(string) == expected


@pytest.mark.parametrize(
    "string,expected",
    (
        ("<span class=font-code>some</span> <br> <span class=font-weight-bold>text</span> &gt;"
         "<span class=\"font-italic\">to</span> test &lt;", "`some` \n **text** >*to* test <"),
        ("`some` \n **text** >*to* test <", "`some` \n **text** >*to* test <"),
    ),
)
def test_demark_note(string, expected):
    assert schemas.demark_note(string) == expected


@pytest.mark.parametrize(
    "string,expected",
    (
        ("some -- text", "some — text"),
        ("some – text", "some — text"),
        ("some <-> text", "some ↔ text"),
        ("some -> text", "some → text"),
        ("some <- text", "some ← text"),
        ("-- some -- text", "-- some — text"),
        ("<-> some <-> text", "<-> some ↔ text"),
        ("-> some -> text", "-> some → text"),
        ("<- some <- text", "<- some ← text"),
    ),
)
def test_replace_punctuation(string, expected):
    assert schemas._replace_punctuation(string) == expected


@pytest.mark.parametrize(
    "string,expected",
    (
        ("\\inf some text", "∞ some text"),
        (r"\inf some text", "∞ some text"),
        ("some \\inf text", "some ∞ text"),
        ("some text \\inf", "some text ∞"),
        ("\\inf some \\inf text \\inf", "∞ some ∞ text ∞"),
    ),
)
def test_replace_inf(string, expected):
    assert schemas._replace_inf(string) == expected


@pytest.mark.parametrize(
    "symbols,expected",
    (
        (["->", "<-", "--", "–", "<->"], " → ← — — ↔ "),
        (["<->", "–", "--", "<-", "->"], " ↔ — — ← → "),
    ),
)
def test_replace_punctuation_any_order(symbols, expected):
    string = " ".join(symbols)
    print(string)
    assert schemas._replace_punctuation(f" {string} ") == expected


@pytest.mark.parametrize(
    "string,tags",
    (
        ("#this_is_not_a_tag sdfhj#this_is_not", []),
        ("#this_is_not_a_tag #this_is_a_tag", ["this_is_a_tag"]),
        ("#this_is_not_a_tag #this_is_a_tag some text #a_tag", ["this_is_a_tag", "a_tag"]),
        ("#this_is_not_a_tag", []),
        ("some text #tag", ["tag"]),
        ("some text #t some text", ["t"]),
        ("# some text # some text #", []),
    ),
)
def test_tags_pattern(string, tags):
    assert schemas.TAGS_PATTERN.findall(string) == tags


@pytest.mark.parametrize(
    "string,tags",
    (
        ("valid uuid4 [[fde197da-0c98-451e-a3aa-eb86116ab964]]", "fde197da-0c98-451e-a3aa-eb86116ab964"),
        ("valid нулевой uuid [[00000000-0000-0000-0000-000000000000]]", "00000000-0000-0000-0000-000000000000"),
        ("valid uuid6 [[1eed93d0-4ee8-6fb2-93f6-a18e7cec9d61]]", "1eed93d0-4ee8-6fb2-93f6-a18e7cec9d61"),
        ("[[fde197da-0c98-451e-a3aa-eb86116ab964]] some text", "fde197da-0c98-451e-a3aa-eb86116ab964"),
        ("some text [[fde197da-0c98-451e-a3aa-eb86116ab964]] some text", "fde197da-0c98-451e-a3aa-eb86116ab964"),
    ),
)
def test_link_pattern(string, tags):
    assert schemas.LINK_PATTERN.search(string).group(1) == tags


@pytest.mark.parametrize(
    "string,tags",
    (
        ("some text [[invalid-uuid]]", []),
        ("текст [[плохой юид]]", []),
    ),
)
def test_link_pattern_without_uuid(string, tags):
    assert schemas.LINK_PATTERN.search(string) is None


@pytest.mark.parametrize(
    "string,expected",
    (
        ("some^42 text", "some<sup>42</sup> text"),
        ("some^-1042 text", "some<sup>-1042</sup> text"),
        ("some^text text", "some<sup>text</sup> text"),
        ("some ^ text", "some ^ text"),
        ("some ^text", "some ^text"),
        ("^ some ^text ^", "^ some ^text ^"),
    ),
)
def test_replace_up_index(string, expected):
    assert schemas._replace_up_index(string) == expected


@pytest.mark.parametrize(
    "text, tags, expected",
    (
        ("#a_tag", {"a_tag"}, '<a href=http://127.0.0.1:9999/notes/?tags_query=a_tag target="_blank">#a_tag</a>'),
        ("any text #with or #without a tag", set(), "any text #with or #without a tag"),
        (
            "#a_tag #another-tag #tag",
            {"a_tag", "another-tag", "tag"},
            '<a href=http://127.0.0.1:9999/notes/?tags_query=a_tag target="_blank">#a_tag</a> <a '
            'href=http://127.0.0.1:9999/notes/?tags_query=another-tag target="_blank">#another-tag</a> <a '
            'href=http://127.0.0.1:9999/notes/?tags_query=tag target="_blank">#tag</a>'),
        (
            "text with tags, some content and #some #tags",
            {"some", "tags", "tag"},
            'text with tags, some content and <a href=http://127.0.0.1:9999/notes/?tags_query=some '
            'target="_blank">#some</a> <a href=http://127.0.0.1:9999/notes/?tags_query=tags target="_blank">#tags</a>'),
        (
            "a link https://blog.burntsushi.net/ripgrep#single-file-benchmarks #and #tags",
            {"and", "tags", "single"},
            'a link https://blog.burntsushi.net/ripgrep#single-file-benchmarks <a '
            'href=http://127.0.0.1:9999/notes/?tags_query=and target="_blank">#and</a> <a '
            'href=http://127.0.0.1:9999/notes/?tags_query=tags target="_blank">#tags</a>'),
        ("text # only", {"text", "only"}, 'text # only'),
    ),
)
def test_mark_tags_with_ref(text, tags, expected):
    assert NoteDb._mark_tags_with_ref(text, tags) == expected

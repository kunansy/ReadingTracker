import pytest

from tracker.materials import db as materials_db


def test_parse_habr_emulated_html():
    html = """
    <html>
      <body>
        <div class="tm-article-presenter__header">
          <h1 class="tm-title">  Some title  </h1>
          <a class="tm-user-info__username">  author_name </a>
        </div>
      </body>
    </html>
    """

    result = materials_db.parse_habr(html)
    assert result.title == "Some title"
    assert result.authors == "author_name"


@pytest.mark.integration
async def test_parse_habr_real_article_opt_in():
    """
    Real network call to Habr (no mocks).

    Skipped unless explicitly enabled.
    """

    url = "https://habr.com/ru/articles/1016056/"
    html = await materials_db.get_html(url, http_timeout=15)
    parsed = materials_db.parse_habr(html)

    assert parsed.title == "Главная проблема vibe coding — не vibe debugging"
    assert parsed.authors == "psycura"


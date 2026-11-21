"""Page markup that other scripts depend on."""
import pytest


@pytest.mark.parametrize("page", ["trip.html", "agenda.html", "compare.html"])
def test_the_page_title_sits_in_a_span_so_the_logo_survives(client, page):
    """The shared theme puts the logo inside the <h1>; the page's script then sets the title text. If the script
    targets the <h1> itself (textContent), the logo is wiped out - so the text lives in a child <span>."""
    html = client.get("/" + page).text
    assert '<h1><span id="page-title">' in html
    assert '<h1 id="page-title">' not in html

from processing.cleaner import clean_content, clean_html

# --- plain text ---


def test_plain_text_passthrough():
    text = "Hello world\nThis is a test."
    assert clean_content(text, "text/plain") == text


def test_plain_text_collapses_excess_newlines():
    result = clean_content("line1\n\n\n\n\nline2", "text/plain")
    assert result == "line1\n\nline2"


def test_plain_text_empty():
    assert clean_content("", "text/plain") == ""


# --- HTML stripping ---


def test_strips_html_tags():
    result = clean_html("<p>Hello <b>world</b></p>")
    assert "Hello" in result
    assert "world" in result
    assert "<" not in result


def test_removes_script():
    result = clean_html("<p>Content</p><script>alert('xss')</script>")
    assert "alert" not in result
    assert "Content" in result


def test_removes_style():
    result = clean_html("<style>body { color: red; }</style><p>Content</p>")
    assert "color" not in result
    assert "Content" in result


def test_empty_html():
    assert clean_html("") == ""


# --- Link preservation ---


def test_link_text_and_href():
    result = clean_html('<a href="https://example.com">Click here</a>')
    assert "Click here (https://example.com)" in result


def test_link_text_equals_href_not_duplicated():
    result = clean_html('<a href="https://example.com">https://example.com</a>')
    assert result.count("https://example.com") == 1


def test_link_no_text_uses_href():
    result = clean_html('<a href="https://example.com"></a>')
    assert "https://example.com" in result


def test_link_no_href_uses_text():
    result = clean_html("<a>plain anchor</a>")
    assert "plain anchor" in result
    assert "<a" not in result


def test_multiple_links_preserved():
    html = '<p><a href="https://a.com">A</a> and <a href="https://b.com">B</a></p>'
    result = clean_html(html)
    assert "https://a.com" in result
    assert "https://b.com" in result


# --- content_type dispatch ---


def test_html_content_type_cleans_tags():
    result = clean_content("<p>Hello</p>", "text/html")
    assert "<p>" not in result
    assert "Hello" in result


def test_plain_content_type_does_not_parse_html():
    raw = "<p>Keep tags</p>"
    result = clean_content(raw, "text/plain")
    assert "<p>" in result

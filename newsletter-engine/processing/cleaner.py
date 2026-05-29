import re

from bs4 import BeautifulSoup


def clean_html(html: str) -> str:
    """Convert HTML to plain text, preserving links as 'text (url)'."""
    soup = BeautifulSoup(html, "lxml")

    for tag in soup(["script", "style", "head", "meta", "img"]):
        tag.decompose()

    for tag in soup.find_all("a"):
        href = tag.get("href", "").strip()
        text = tag.get_text(strip=True)
        if href and text and href != text:
            tag.replace_with(f"{text} ({href})")
        elif href:
            tag.replace_with(href)
        else:
            tag.replace_with(text)

    text = soup.get_text(separator="\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_content(raw_content: str, content_type: str) -> str:
    if content_type == "text/html":
        return clean_html(raw_content)
    text = re.sub(r"\n{3,}", "\n\n", raw_content)
    return text.strip()

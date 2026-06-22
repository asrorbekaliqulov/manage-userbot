"""
Whitelist sanitizer for Telegram-style rich text.

Used in two directions:
  * Incoming: clean the HTML Telethon produces from message entities before we
    render it in the chat UI (defends against XSS from message content).
  * Outgoing: clean the HTML produced by the in-browser editor before sending it
    to Telegram with ``parse_mode="html"``.

Only a small, Telegram-compatible tag set is allowed; everything else is
dropped while keeping its text. The only attribute kept is ``href`` on links
(restricted to safe schemes).
"""
from __future__ import annotations

from html import escape
from html.parser import HTMLParser

# Tags Telegram understands and we allow through.
ALLOWED_TAGS = {
    "b", "strong", "i", "em", "u", "ins", "s", "strike", "del",
    "code", "pre", "a", "blockquote", "br", "span", "tg-spoiler",
}
SAFE_SCHEMES = ("http://", "https://", "tg://", "mailto:")


class _Sanitizer(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._open: list[str] = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "br":
            self.parts.append("<br>")
            return
        if tag not in ALLOWED_TAGS:
            return
        if tag == "a":
            href = ""
            for name, value in attrs:
                if name.lower() == "href" and value:
                    if value.startswith(SAFE_SCHEMES):
                        href = value
                    break
            if not href:
                # Drop the link wrapper but keep its text.
                self._open.append("")
                return
            self.parts.append(f'<a href="{escape(href, quote=True)}">')
            self._open.append("a")
            return
        if tag == "span":
            # Keep only the Telegram spoiler span.
            is_spoiler = any(
                name.lower() == "class" and value and "tg-spoiler" in value
                for name, value in attrs
            )
            if is_spoiler:
                self.parts.append('<span class="tg-spoiler">')
                self._open.append("span")
            else:
                self._open.append("")
            return
        self.parts.append(f"<{tag}>")
        self._open.append(tag)

    def handle_startendtag(self, tag, attrs):
        if tag.lower() == "br":
            self.parts.append("<br>")

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "br":
            return
        if tag not in ALLOWED_TAGS:
            return
        if not self._open:
            return
        opened = self._open.pop()
        if opened:
            self.parts.append(f"</{opened}>")

    def handle_data(self, data):
        self.parts.append(escape(data))

    def result(self) -> str:
        # Close anything left open.
        while self._open:
            opened = self._open.pop()
            if opened:
                self.parts.append(f"</{opened}>")
        return "".join(self.parts)


def sanitize_html(html: str) -> str:
    if not html:
        return ""
    parser = _Sanitizer()
    parser.feed(html)
    return parser.result()


def html_to_telegram(html: str) -> str:
    """Prepare editor HTML for sending: sanitize, then turn <br> into newlines."""
    clean = sanitize_html(html)
    clean = clean.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
    return clean.strip()

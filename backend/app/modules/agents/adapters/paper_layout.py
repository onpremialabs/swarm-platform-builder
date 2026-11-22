"""Deterministic paper-layout generator for the Publicador agent.

Turns an article's markdown body + title-block metadata into a self-contained,
printable HTML document (one template per scientific citation format). No LLM and
no external dependencies: a minimal markdown->HTML converter keeps the backend
dependency-free, and all CSS is inlined so the result can be rendered in an
iframe (``srcdoc``) and exported to PDF straight from the browser.
"""
import html
import re
from typing import Any, Dict, List

# ---------------------------------------------------------------------------
# Per-format layout configuration
# Each scientific format maps to the visual conventions of its community.
# ---------------------------------------------------------------------------
_FORMAT_STYLE: Dict[str, Dict[str, Any]] = {
    "ieee": {
        "label": "IEEE",
        "columns": 2,
        "line_height": 1.25,
        "font": "'Times New Roman', Times, serif",
        "size": "9.5pt",
        "title_size": "20pt",
    },
    # Conference style (ACL/*ACL family): two columns, Times ~10pt, sections
    # numbered by CSS counters and a hanging indent on the reference list.
    "acl": {
        "label": "ACL (conference)",
        "columns": 2,
        "line_height": 1.18,
        "font": "'Times New Roman', Times, serif",
        "size": "10pt",
        "title_size": "17pt",
        # Opt-in typographic conventions (see _stylesheet / _decorate_headings).
        "numbered_sections": True,
        "hanging_references": True,
    },
    "apa": {
        "label": "APA 7th edition",
        "columns": 1,
        "line_height": 2.0,
        "font": "'Times New Roman', Times, serif",
        "size": "11pt",
        "title_size": "18pt",
    },
    "vancouver": {
        "label": "Vancouver",
        "columns": 1,
        "line_height": 1.5,
        "font": "'Times New Roman', Times, serif",
        "size": "11pt",
        "title_size": "18pt",
    },
    "chicago": {
        "label": "Chicago 17th edition",
        "columns": 1,
        "line_height": 1.6,
        "font": "Georgia, 'Times New Roman', serif",
        "size": "11pt",
        "title_size": "18pt",
    },
    "nature": {
        "label": "Nature",
        "columns": 1,
        "line_height": 1.5,
        "font": "Helvetica, Arial, sans-serif",
        "size": "10.5pt",
        "title_size": "19pt",
    },
}

_DEFAULT_FORMAT = "apa"


def _style_for(scientific_format: str) -> Dict[str, Any]:
    return _FORMAT_STYLE.get((scientific_format or "").lower(), _FORMAT_STYLE[_DEFAULT_FORMAT])


# ---------------------------------------------------------------------------
# Editable theme (SPEC-022 / T11.2)
# The user never writes CSS: they pick values from these allowlists, which the
# layout applies on top of the format preset. Anything unknown falls back to the
# preset, so a bad value can never break the page (nor inject styles).
# ---------------------------------------------------------------------------
# Curated web-safe families only — no embedded webfonts, so the PDF prints the
# same everywhere (clarify SPEC-022, 2026-07-04).
_THEME_FONTS: Dict[str, str] = {
    "times": "'Times New Roman', Times, serif",
    "georgia": "Georgia, 'Times New Roman', serif",
    "palatino": "'Palatino Linotype', Palatino, 'Book Antiqua', serif",
    "helvetica": "Helvetica, Arial, sans-serif",
    "arial": "Arial, Helvetica, sans-serif",
    "verdana": "Verdana, Geneva, sans-serif",
}

# Accent tokens from the design system (frontend/ds/zeroheight/tokens.dtcg.json,
# épica E7) — a closed set keeps tenant identity coherent and the sanitising
# surface tiny.
_THEME_ACCENTS: Dict[str, str] = {
    "ink": "#0b1b33",      # default: near-black, neutral for print
    "blue": "#0176d3",
    "violet": "#6b4fe3",
    "green": "#2e844a",
    "amber": "#c47d04",
    "red": "#ba0517",
    "teal": "#06a59a",
}

_THEME_COLUMNS = (1, 2)
_DEFAULT_ACCENT = "ink"


def sanitize_theme(theme: Dict[str, Any] | None) -> Dict[str, Any]:
    """Keep only recognised theme values; silently drop anything else.

    Dropping (rather than erroring) is what makes AC2's "falls back to the
    default without breaking the layout" true for stored themes that predate a
    palette change or arrive from an older client.
    """
    if not isinstance(theme, dict):
        return {}
    clean: Dict[str, Any] = {}

    font = theme.get("font")
    if isinstance(font, str) and font.lower() in _THEME_FONTS:
        clean["font"] = font.lower()

    accent = theme.get("accent_color")
    if isinstance(accent, str) and accent.lower() in _THEME_ACCENTS:
        clean["accent_color"] = accent.lower()

    columns = theme.get("columns")
    if isinstance(columns, bool):  # bool is an int subclass — reject explicitly
        columns = None
    if isinstance(columns, int) and columns in _THEME_COLUMNS:
        clean["columns"] = columns

    return clean


def resolve_theme(*layers: Dict[str, Any] | None) -> Dict[str, Any]:
    """Merge theme layers, most specific last (project theme → article theme).

    Each layer is sanitised independently so one bad layer cannot poison the
    result; later layers override earlier ones key by key.
    """
    resolved: Dict[str, Any] = {}
    for layer in layers:
        resolved.update(sanitize_theme(layer))
    return resolved


# ---------------------------------------------------------------------------
# Minimal markdown -> HTML conversion
# Supports the subset emitted by the Redactor/Formateador: headings, bold,
# italic, inline code, links, ordered/unordered lists and paragraphs.
# ---------------------------------------------------------------------------
def _safe_img_src(url: str, asset_resolver=None) -> str | None:
    """Resolve an image reference to a src the paper may safely embed.

    Only three shapes are accepted, and everything else (notably ``javascript:``
    and ``data:text/html``) is dropped:

    * ``asset:<id>`` → inlined as a data URI by the project-scoped resolver;
    * an existing ``data:image/...`` URI;
    * ``https://`` — kept, though it will not appear in an offline print.
    """
    ref = (url or "").strip()
    if asset_resolver is not None:
        resolved = asset_resolver(ref)
        if resolved:
            return resolved
    lowered = ref.lower()
    if lowered.startswith("data:image/"):
        return ref
    if lowered.startswith("https://"):
        return ref
    return None


# Schemes a link in a paper may legitimately use. Everything else — notably
# ``javascript:`` and ``data:`` — is dropped: the layout is rendered in an iframe
# and printed, so a hostile href is a stored-XSS vector for every reader of the
# published article (SPEC-016/AC1).
_SAFE_LINK_SCHEMES = ("http://", "https://", "mailto:")


def _safe_href(url: str) -> str | None:
    """Return the URL if its scheme is allowed, else ``None``.

    Relative and anchor links are allowed (they cannot carry a scheme). The check
    strips leading control/whitespace characters first, because
    ``java\\tscript:`` and ``  javascript:`` are both parsed as the scheme by
    browsers.
    """
    ref = re.sub(r"[\x00-\x20]", "", (url or ""))
    lowered = ref.lower()
    if lowered.startswith(_SAFE_LINK_SCHEMES):
        return ref
    if ":" not in lowered.split("/")[0]:      # no scheme at all → relative/anchor
        return ref or None
    return None


def _inline(text: str, asset_resolver=None) -> str:
    """Apply inline markdown formatting to already plain (un-escaped) text."""
    # Protect nothing fancy — escape first, then re-introduce safe tags.
    out = html.escape(text, quote=False)

    # images ![alt](ref) — handled BEFORE links so the leading '!' is not lost.
    def _image(match: "re.Match") -> str:
        alt, ref = match.group(1), match.group(2)
        src = _safe_img_src(ref, asset_resolver)
        if not src:
            return ""            # unresolvable/unsafe reference: drop it silently
        caption = f'<figcaption>{alt}</figcaption>' if alt.strip() else ""
        return (
            f'<figure class="paper-figure">'
            f'<img src="{html.escape(src, quote=True)}" alt="{html.escape(alt, quote=True)}" />'
            f"{caption}</figure>"
        )

    out = re.sub(r"!\[([^\]]*)\]\(([^)\s]+)\)", _image, out)

    # links [text](url) — scheme-checked and quote-escaped. A rejected link keeps
    # its text (the reader still sees the words) but loses the anchor.
    def _link(match: "re.Match") -> str:
        label, url = match.group(1), match.group(2)
        href = _safe_href(url)
        if not href:
            return label
        return f'<a href="{html.escape(href, quote=True)}">{label}</a>'

    out = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", _link, out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"__([^_]+)__", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", out)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    return out


def markdown_to_html(md: str, asset_resolver=None) -> str:
    """Convert a markdown string to an HTML fragment (block-level)."""
    if not md:
        return ""

    lines = md.replace("\r\n", "\n").split("\n")
    html_parts: List[str] = []
    paragraph: List[str] = []
    list_buffer: List[str] = []
    list_type: str | None = None  # "ul" | "ol"

    def flush_paragraph() -> None:
        if paragraph:
            html_parts.append(f"<p>{_inline(' '.join(paragraph), asset_resolver)}</p>")
            paragraph.clear()

    def flush_list() -> None:
        nonlocal list_type
        if list_buffer:
            items = "".join(f"<li>{_inline(it, asset_resolver)}</li>" for it in list_buffer)
            html_parts.append(f"<{list_type}>{items}</{list_type}>")
            list_buffer.clear()
            list_type = None

    for raw in lines:
        line = raw.rstrip()
        stripped = line.strip()

        if not stripped:
            flush_paragraph()
            flush_list()
            continue

        heading = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if heading:
            flush_paragraph()
            flush_list()
            level = len(heading.group(1))
            html_parts.append(f"<h{level}>{_inline(heading.group(2), asset_resolver)}</h{level}>")
            continue

        ul = re.match(r"^[-*+]\s+(.*)$", stripped)
        ol = re.match(r"^\d+[.)]\s+(.*)$", stripped)
        if ul or ol:
            flush_paragraph()
            new_type = "ul" if ul else "ol"
            if list_type and list_type != new_type:
                flush_list()
            list_type = new_type
            list_buffer.append((ul or ol).group(1))
            continue

        # plain text → accumulate into a paragraph
        flush_list()
        paragraph.append(stripped)

    flush_paragraph()
    flush_list()
    return "\n".join(html_parts)


# ---------------------------------------------------------------------------
# Heading decoration for auto-numbered formats (ACL and friends)
# ---------------------------------------------------------------------------
# Section labels that must never be auto-numbered and that introduce the
# reference list (matched case-insensitively, accent-tolerant on the stem).
_REFERENCES_RE = re.compile(
    r"^\s*(referencias?|references|bibliograf[íi]a|bibliography|works\s+cited|"
    r"literatura\s+citada)\b",
    re.IGNORECASE,
)
_H2_RE = re.compile(r"<h2>(.*?)</h2>", re.DOTALL)
_H3_RE = re.compile(r"<h3>(.*?)</h3>", re.DOTALL)
# Manual numbering the Redactor/Formateador may already have written into the
# heading text ("## 3. Arquitectura", "### 3.1 Motor"). Stripped when the layout
# numbers sections itself, so the output never reads "3. 3. Arquitectura".
_MANUAL_NUMBER_RE = re.compile(r"^\s*\d+(?:\.\d+)*\.?\s+")


def _strip_tags(fragment: str) -> str:
    return re.sub(r"<[^>]+>", "", fragment).strip()


def _decorate_headings(body_html: str) -> str:
    """Tag headings so CSS can number sections and lay out the reference list.

    ``h2`` becomes either ``section-heading`` (numbered by a CSS counter) or
    ``references-heading`` (never numbered; its following paragraphs get the
    hanging indent). Manual numbering already present in the text is removed so
    it is not duplicated by the counter. Applied only for formats that opt in,
    leaving every other format's output byte-identical.
    """
    def h2(match: re.Match) -> str:
        inner = match.group(1)
        if _REFERENCES_RE.match(_strip_tags(inner)):
            return f'<h2 class="references-heading">{inner}</h2>'
        return f'<h2 class="section-heading">{_MANUAL_NUMBER_RE.sub("", inner)}</h2>'

    def h3(match: re.Match) -> str:
        inner = match.group(1)
        return f'<h3 class="subsection-heading">{_MANUAL_NUMBER_RE.sub("", inner)}</h3>'

    return _H3_RE.sub(h3, _H2_RE.sub(h2, body_html))


# ---------------------------------------------------------------------------
# Title block (authors + affiliations + abstract)
# ---------------------------------------------------------------------------
def _authors_block(authors: List[Dict[str, Any]]) -> str:
    if not authors:
        return ""
    cells = []
    for a in authors:
        name = html.escape((a.get("name") or "").strip())
        if not name:
            continue
        affiliation = html.escape((a.get("affiliation") or "").strip())
        email = (a.get("email") or "").strip()
        email_html = (
            f'<div class="author-email">{html.escape(email)}</div>' if email else ""
        )
        aff_html = (
            f'<div class="author-affil">{affiliation}</div>' if affiliation else ""
        )
        cells.append(
            f'<div class="author">'
            f'<div class="author-name">{name}</div>{aff_html}{email_html}'
            f"</div>"
        )
    if not cells:
        return ""
    return f'<div class="authors">{"".join(cells)}</div>'


# ---------------------------------------------------------------------------
# Per-format stylesheet
# ---------------------------------------------------------------------------
def _numbering_css(s: Dict[str, Any]) -> str:
    """Extra rules for formats that number their own sections / indent references."""
    css = ""
    if s.get("numbered_sections"):
        # Counters live on the body container so the numbering restarts per paper
        # and survives the multi-column flow.
        css += """
    .paper-body { counter-reset: section; }
    .paper-body h2.section-heading { counter-increment: section; counter-reset: subsection; }
    .paper-body h2.section-heading::before { content: counter(section) "\\00a0\\00a0"; }
    .paper-body h3.subsection-heading { counter-increment: subsection; }
    .paper-body h3.subsection-heading::before {
      content: counter(section) "." counter(subsection) "\\00a0\\00a0";
    }
    /* The reference list is a section, but an unnumbered one. */
    .paper-body h2.references-heading::before { content: none; }
    """
    if s.get("hanging_references"):
        # Hanging indent: first line flush left, continuation lines indented.
        css += """
    .paper-body h2.references-heading ~ p {
      padding-left: 1.2em;
      text-indent: -1.2em;
      text-align: left;
      hyphens: none;
    }
    """
    return css


def _stylesheet(scientific_format: str, theme: Dict[str, Any] | None = None) -> str:
    s = _style_for(scientific_format)
    theme = sanitize_theme(theme)
    # Theme values override the preset; absent ones keep the format's default.
    if "font" in theme:
        s = {**s, "font": _THEME_FONTS[theme["font"]]}
    columns = theme.get("columns", s["columns"])
    accent = _THEME_ACCENTS[theme.get("accent_color", _DEFAULT_ACCENT)]
    content_columns = (
        f"column-count: {columns}; column-gap: 28px; column-fill: balance;"
        if columns > 1
        else "max-width: 720px; margin: 0 auto;"
    )
    extra_css = _numbering_css(s)
    return f"""
    :root {{ color-scheme: light; }}
    @page {{ size: A4; margin: 18mm 16mm; }}
    * {{ box-sizing: border-box; }}
    body {{
      font-family: {s['font']};
      font-size: {s['size']};
      line-height: {s['line_height']};
      color: #111;
      background: #f3f4f6;
      margin: 0;
      padding: 24px;
    }}
    .sheet {{
      background: #fff;
      max-width: 820px;
      margin: 0 auto;
      padding: 40px 48px 56px;
      box-shadow: 0 1px 4px rgba(0,0,0,0.15);
    }}
    .paper-title {{
      font-size: {s['title_size']};
      font-weight: 700;
      text-align: center;
      line-height: 1.2;
      margin: 0 0 18px;
    }}
    .authors {{
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: 8px 48px;
      margin-bottom: 24px;
    }}
    .paper-date {{ text-align: center; font-size: 10pt; color: #444; margin-bottom: 0.6em; }}
    .author {{ text-align: center; font-size: 10pt; }}
    .author-name {{ font-weight: 600; font-size: 11pt; }}
    .author-affil {{ color: #333; white-space: pre-line; }}
    .author-email {{ color: #444; font-family: 'Courier New', monospace; font-size: 9pt; }}
    .abstract {{
      margin: 0 auto 22px;
      max-width: 680px;
      font-size: {('9pt' if columns > 1 else '10.5pt')};
    }}
    .abstract h2 {{
      font-size: 11pt;
      text-align: center;
      margin: 0 0 6px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    .abstract p {{ text-align: justify; margin: 0; }}
    .paper-body {{ {content_columns} text-align: justify; hyphens: auto; }}
    .paper-body h1, .paper-body h2 {{
      font-size: 11.5pt; font-weight: 700; margin: 14px 0 6px;
      break-after: avoid; color: {accent};
    }}
    .paper-body h3, .paper-body h4 {{
      font-size: 10.5pt; font-weight: 700; margin: 10px 0 4px; color: {accent};
    }}
    .paper-body p {{ margin: 0 0 8px; orphans: 2; widows: 2; }}
    .paper-body ul, .paper-body ol {{ margin: 0 0 8px 1.1em; padding: 0; }}
    .paper-body code {{ font-family: 'Courier New', monospace; font-size: 0.92em; }}
    .paper-figure {{
      margin: 10px 0; text-align: center; break-inside: avoid;
    }}
    .paper-figure img {{ max-width: 100%; height: auto; }}
    .paper-figure figcaption {{
      font-size: 0.88em; color: #333; margin-top: 4px; text-align: center;
    }}
    .paper-body a {{ color: {accent}; text-decoration: none; word-break: break-word; }}
    .paper-body h2:last-of-type ~ p {{ font-size: 0.95em; }}
    {extra_css}
    @media print {{
      body {{ background: #fff; padding: 0; }}
      .sheet {{ box-shadow: none; max-width: none; padding: 0; }}
    }}
    """


def build_paper_html(
    *,
    title: str,
    authors: List[Dict[str, Any]],
    abstract: str,
    body_markdown: str,
    scientific_format: str,
    theme: Dict[str, Any] | None = None,
    asset_resolver=None,
    date: str = "",
) -> str:
    """Assemble a complete, self-contained printable HTML document.

    The body markdown is expected to already carry the reformatted in-text
    citations and the deterministic references section produced by the
    Formateador; this function only lays it out.

    ``theme`` optionally overrides the format preset with user-chosen values
    (``font``, ``accent_color``, ``columns``) taken from the allowlists above.
    It is *parameterisation*, never user CSS: unknown values are dropped and the
    preset's own value is used, so the layout cannot be broken or injected into.
    """
    fmt = (scientific_format or _DEFAULT_FORMAT).lower()
    style = _style_for(fmt)

    safe_title = html.escape((title or "Untitled").strip())
    authors_html = _authors_block(authors or [])
    # La fecha la pone el sistema (SPEC-037/T25.1); sin ella, salida idéntica a antes.
    if date and date.strip():
        authors_html += f'<div class="paper-date">{html.escape(date.strip())}</div>'
    abstract_html = ""
    if abstract and abstract.strip():
        abstract_html = (
            f'<section class="abstract"><h2>Abstract</h2>'
            f"<p>{_inline(abstract.strip(), asset_resolver)}</p></section>"
        )
    body_html = markdown_to_html(body_markdown, asset_resolver)
    # Only formats that opt in are decorated, so every other format's output
    # stays byte-identical to before this preset existed.
    if style.get("numbered_sections") or style.get("hanging_references"):
        body_html = _decorate_headings(body_html)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{safe_title}</title>
<meta name="citation-format" content="{html.escape(style['label'])}" />
<style>{_stylesheet(fmt, theme)}</style>
</head>
<body>
<main class="sheet" data-format="{html.escape(fmt)}">
  <h1 class="paper-title">{safe_title}</h1>
  {authors_html}
  {abstract_html}
  <div class="paper-body">
{body_html}
  </div>
</main>
</body>
</html>"""

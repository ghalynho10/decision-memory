#!/usr/bin/env python3
"""Render a small markdown subset to a styled standalone HTML file.

Minimal converter for the project brief's own dialect: ATX headings, block
quotes, pipe tables, bullet lists, bold, inline code, and blank line separated
paragraphs. Everything else is treated as a paragraph. No external packages.
"""

import re
import sys
from pathlib import Path


def inline(text: str) -> str:
    text = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    return text


def convert(md: str) -> str:
    lines = md.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]

        if line.strip().startswith("```"):
            # fenced code block: keep line breaks inside a <pre>
            i += 1
            code: list[str] = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code.append(lines[i])
                i += 1
            i += 1  # skip closing fence
            out.append("<pre>" + "\n".join(code) + "</pre>")
            continue
        elif line.startswith("### "):
            out.append(f"<h3>{inline(line[4:])}</h3>")
        elif line.startswith("## "):
            out.append(f"<h2>{inline(line[3:])}</h2>")
        elif line.startswith("# "):
            out.append(f"<h1>{inline(line[2:])}</h1>")
        elif line.startswith("> "):
            quote: list[str] = []
            while i < len(lines) and lines[i].startswith("> "):
                quote.append(inline(lines[i][2:]))
                i += 1
            out.append("<blockquote>" + "<br>".join(quote) + "</blockquote>")
            continue
        elif (
            line.startswith("|")
            and i + 1 < len(lines)
            and set(
                lines[i + 1].replace("|", "").replace("-", "").replace(":", "").strip()
            )
            == set()
        ):
            # table: header, separator row, then body rows
            header = [c.strip() for c in line.strip("|").split("|")]
            i += 2  # skip separator
            rows = []
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([c.strip() for c in lines[i].strip("|").split("|")])
                i += 1
            html = ["<table><thead><tr>"]
            html += [f"<th>{inline(c)}</th>" for c in header]
            html.append("</tr></thead><tbody>")
            for row in rows:
                html.append("<tr>")
                html += [f"<td>{inline(c)}</td>" for c in row]
                html.append("</tr>")
            html.append("</tbody></table>")
            out.append("".join(html))
            continue
        elif line.startswith("- "):
            items: list[str] = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(f"<li>{inline(lines[i][2:])}</li>")
                i += 1
            out.append("<ul>" + "".join(items) + "</ul>")
            continue
        elif line.strip() == "":
            pass
        else:
            para: list[str] = []
            while (
                i < len(lines)
                and lines[i].strip()
                and not lines[i].startswith(("#", "|", "- ", "> "))
            ):
                para.append(inline(lines[i]))
                i += 1
            out.append("<p>" + " ".join(para) + "</p>")
            continue
        i += 1
    return "\n".join(out)


CSS = """
:root { color-scheme: light; }
body { font-family: -apple-system, "Segoe UI", Helvetica, Arial, sans-serif;
       max-width: 46rem; margin: 2.5rem auto; padding: 0 1.5rem;
       color: #1a1a1a; line-height: 1.55; }
h1 { font-size: 1.7rem; border-bottom: 2px solid #0b7285; padding-bottom: .4rem; }
h2 { font-size: 1.25rem; margin-top: 2rem; color: #0b7285; }
h3 { font-size: 1.05rem; margin-top: 1.5rem; }
blockquote { border-left: 4px solid #0b7285; margin: 1.2rem 0;
             padding: .4rem 1rem; background: #f0f9fa; border-radius: 4px;
             font-size: 1.02rem; }
table { border-collapse: collapse; width: 100%; margin: 1.2rem 0;
        font-size: .9rem; }
th, td { border: 1px solid #d0d7de; padding: .5rem .6rem; text-align: left;
         vertical-align: top; }
th { background: #eef4f6; }
code { background: #f2f4f6; padding: .1em .35em; border-radius: 4px;
       font-family: "SF Mono", Menlo, Consolas, monospace; font-size: .85em; }
pre { background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 6px;
      padding: .9rem 1rem; overflow-x: auto; line-height: 1.45;
      font-family: "SF Mono", Menlo, Consolas, monospace; font-size: .82em;
      margin: 1.2rem 0; }
strong { color: #0b7285; }
"""


def main() -> int:
    src = Path(sys.argv[1])
    dst = Path(sys.argv[2])
    body = convert(src.read_text(encoding="utf-8"))
    html = (
        f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
        f"<title>{src.stem}</title><style>{CSS}</style></head>"
        f"<body>{body}</body></html>"
    )
    dst.write_text(html, encoding="utf-8")
    print(dst)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

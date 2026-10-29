from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "THEMEGRAPH_HUMAN_CONSEQUENCE_EVALUATION_RESEARCH_DESIGNS.md"
TARGET = ROOT / "THEMEGRAPH_HUMAN_CONSEQUENCE_EVALUATION_RESEARCH_DESIGNS.tex"

LATEX_ESCAPES = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}

PREAMBLE = r"""\documentclass[11pt]{article}
\usepackage[T1]{fontenc}
\usepackage[utf8]{inputenc}
\usepackage{lmodern}
\usepackage{microtype}
\usepackage[margin=0.85in,headheight=22pt]{geometry}
\usepackage{array}
\usepackage{booktabs}
\usepackage{xcolor}
\usepackage{longtable}
\usepackage{enumitem}
\usepackage{fancyhdr}
\usepackage[hidelinks]{hyperref}

\definecolor{ThemeGraphBlue}{HTML}{174A5B}
\definecolor{ThemeGraphPale}{HTML}{E8F1F3}
\definecolor{ThemeGraphRule}{HTML}{A8BEC5}
\hypersetup{
  pdftitle={ThemeGraph Human Consequence Evaluation Research Designs},
  pdfauthor={ThemeGraph Research Team},
  colorlinks=true,
  linkcolor=ThemeGraphBlue,
  urlcolor=ThemeGraphBlue
}
\setlength{\parindent}{0pt}
\setlength{\parskip}{0.55em}
\setcounter{secnumdepth}{3}
\setcounter{tocdepth}{2}
\setlist[enumerate]{leftmargin=2.1em,itemsep=0.25em,topsep=0.35em}
\renewcommand{\arraystretch}{1.18}
\pagestyle{fancy}
\fancyhf{}
\fancyhead[L]{\small\textcolor{ThemeGraphBlue}{ThemeGraph consequence evaluation}}
\fancyhead[R]{\small\thepage}
\renewcommand{\headrulewidth}{0.4pt}
\renewcommand{\headrule}{\hbox to\headwidth{\color{ThemeGraphRule}\leaders\hrule height \headrulewidth\hfill}}

\begin{document}
\pagenumbering{roman}
\begin{titlepage}
  \vspace*{0.18\textheight}
  {\color{ThemeGraphBlue}\rule{\textwidth}{2pt}}\\[1.2em]
    {\Huge\bfseries ThemeGraph Human Consequence\\Evaluation Research Designs\par}
  \vspace{1em}
  {\Large A claim-matched program for interpretation, behavior, governance, accessibility, and task outcomes\par}
  \vfill
  {\large Standalone research design report\par}
  \vspace{0.5em}
  {\normalsize Compiled \today\par}
  \vspace{1em}
  {\color{ThemeGraphBlue}\rule{\textwidth}{2pt}}
\end{titlepage}
\tableofcontents
\clearpage
\pagenumbering{arabic}
"""

POSTAMBLE = "\\end{document}\n"


def escape_latex(text: str) -> str:
    return "".join(LATEX_ESCAPES.get(character, character) for character in text)


def split_table_row(line: str) -> list[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def table_column_spec(column_count: int) -> str:
    column = r">{\raggedright\arraybackslash}p"
    if column_count == 5:
        return "@{}" + f"{column}{{0.165\\textwidth}}" * 5 + "@{}"
    if column_count == 3:
        return "@{}" + f"{column}{{0.29\\textwidth}}" * 3 + "@{}"
    width = 0.82 / column_count
    return "@{}" + f"{column}{{{width:.3f}\\textwidth}}" * column_count + "@{}"


def render_table(lines: list[str]) -> list[str]:
    rows = [split_table_row(line) for line in lines]
    header = rows[0]
    body = rows[2:]
    column_spec = table_column_spec(len(header))
    header_text = " & ".join(f"\\textbf{{{escape_latex(cell)}}}" for cell in header)
    output = [
        "\\begingroup",
        "\\small",
        "\\setlength{\\tabcolsep}{4pt}",
        f"\\begin{{longtable}}{{{column_spec}}}",
        "\\toprule",
        f"{header_text} \\\\",
        "\\midrule",
        "\\endfirsthead",
        "\\toprule",
        f"{header_text} \\\\",
        "\\midrule",
        "\\endhead",
        "\\midrule",
        f"\\multicolumn{{{len(header)}}}{{r}}{{\\footnotesize Continued on next page}} \\\\",
        "\\endfoot",
        "\\bottomrule",
        "\\endlastfoot",
    ]
    for row in body:
        output.append(" & ".join(escape_latex(cell) for cell in row) + r" \\")
    output.extend(["\\end{longtable}", "\\endgroup", ""])
    return output


def convert(markdown: str) -> str:
    source_lines = markdown.splitlines()
    output = [PREAMBLE]
    index = 1
    enumerate_open = False

    while index < len(source_lines):
        line = source_lines[index]

        if enumerate_open and not re.match(r"^\d+\.\s+", line):
            output.extend(["\\end{enumerate}", ""])
            enumerate_open = False

        if not line.strip():
            index += 1
            continue

        if line.startswith("|"):
            table_lines: list[str] = []
            while index < len(source_lines) and source_lines[index].startswith("|"):
                table_lines.append(source_lines[index])
                index += 1
            output.extend(render_table(table_lines))
            continue

        list_match = re.match(r"^\d+\.\s+(.*)$", line)
        if list_match:
            if not enumerate_open:
                output.append("\\begin{enumerate}")
                enumerate_open = True
            output.append(f"  \\item {escape_latex(list_match.group(1))}")
            index += 1
            continue

        heading_match = re.match(r"^(#{2,4})\s+(.*)$", line)
        if heading_match:
            heading_level = len(heading_match.group(1))
            command = {2: "section", 3: "subsection", 4: "subsubsection"}[heading_level]
            heading_text = heading_match.group(2)
            if heading_level == 3:
                heading_text = re.sub(r"^\d+\.\s+", "", heading_text)
            output.extend(
                [f"\\{command}{{{escape_latex(heading_text)}}}", ""]
            )
            index += 1
            continue

        paragraph = [line.strip()]
        index += 1
        while index < len(source_lines):
            next_line = source_lines[index]
            if (
                not next_line.strip()
                or next_line.startswith("|")
                or re.match(r"^#{2,4}\s+", next_line)
                or re.match(r"^\d+\.\s+", next_line)
            ):
                break
            paragraph.append(next_line.strip())
            index += 1
        output.extend([escape_latex(" ".join(paragraph)), ""])

    if enumerate_open:
        output.extend(["\\end{enumerate}", ""])
    output.append(POSTAMBLE)
    return "\n".join(output)


def main() -> None:
    markdown = SOURCE.read_text(encoding="utf-8-sig")
    TARGET.write_text(convert(markdown), encoding="utf-8", newline="\n")
    print(f"Wrote {TARGET.name}")


if __name__ == "__main__":
    main()
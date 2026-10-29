from __future__ import annotations

import argparse
import re
from pathlib import Path

WORD_PATTERN = re.compile(r"[A-Za-z0-9]+(?:[-'][A-Za-z0-9]+)*")
INPUT_PATTERN = re.compile(r"\\input\{([^}]+)\}")
COMMENT_PATTERN = re.compile(r"(?<!\\)%.*$")


def _expand_inputs(source: str, base: Path, seen: frozenset[Path]) -> str:
    def replace_input(match: re.Match[str]) -> str:
        path = (base / match.group(1)).with_suffix(".tex").resolve()
        if path in seen or not path.is_file():
            return ""
        text = path.read_text(encoding="utf-8")
        return _expand_inputs(text, path.parent, seen | {path})

    return INPUT_PATTERN.sub(replace_input, source)


def _remove_environment(source: str, environment: str) -> str:
    pattern = re.compile(
        rf"\\begin\{{{re.escape(environment)}\}}.*?"
        rf"\\end\{{{re.escape(environment)}\}}",
        re.DOTALL,
    )
    return pattern.sub(" ", source)


def _plain_text(source: str) -> str:
    source = "\n".join(COMMENT_PATTERN.sub("", line) for line in source.splitlines())
    source = re.split(r"\\bibliography\{|\\begin\{thebibliography\}", source, maxsplit=1)[0]
    source = re.split(r"\\appendix(?:\b|\{)", source, maxsplit=1)[0]
    for environment in ("figure", "figure*", "equation", "equation*", "align", "align*"):
        source = _remove_environment(source, environment)
    source = re.sub(r"\\caption(?:\[[^]]*\])?\{(?:[^{}]|\{[^{}]*\})*\}", " ", source)
    source = re.sub(r"\\Description\{(?:[^{}]|\{[^{}]*\})*\}", " ", source)
    source = re.sub(
        r"\\(?:cite|citep|citet|ref|pageref|label|url|path)"
        r"(?:\[[^]]*\])?\{[^{}]*\}",
        " ",
        source,
    )
    source = re.sub(r"\\href\{[^{}]*\}\{([^{}]*)\}", r"\1", source)
    source = re.sub(
        r"\\(?:section|subsection|subsubsection|paragraph|textbf|textit|emph|texttt|mbox)"
        r"\*?\{([^{}]*)\}",
        r"\1",
        source,
    )
    source = re.sub(r"\$.*?\$", " ", source, flags=re.DOTALL)
    source = re.sub(r"\\\[.*?\\\]", " ", source, flags=re.DOTALL)
    source = re.sub(r"\\[A-Za-z@]+\*?(?:\[[^]]*\])?", " ", source)
    return re.sub(r"[{}&_~^|]", " ", source)


def count_words(path: Path) -> tuple[int, int]:
    source = path.read_text(encoding="utf-8")
    expanded = _expand_inputs(source, path.parent, frozenset({path.resolve()}))
    abstract_match = re.search(
        r"\\begin\{abstract\}(.*?)\\end\{abstract\}", expanded, re.DOTALL
    )
    abstract_words = (
        len(WORD_PATTERN.findall(_plain_text(abstract_match.group(1))))
        if abstract_match
        else 0
    )
    paper_match = re.search(r"\\begin\{document\}(.*)", expanded, re.DOTALL)
    paper_source = paper_match.group(1) if paper_match else expanded
    return abstract_words, len(WORD_PATTERN.findall(_plain_text(paper_source)))


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Count manuscript words after expanding inputs and excluding references, "
            "figure/table captions, descriptions, displayed mathematics, and appendices."
        )
    )
    parser.add_argument(
        "path",
        nargs="?",
        type=Path,
        default=Path("manuscript/themegraph_chi_2027.tex"),
    )
    args = parser.parse_args()
    abstract_words, main_words = count_words(args.path.resolve())
    print(f"Abstract words: {abstract_words}")
    print(f"CHI-aligned main-paper words: {main_words}")


if __name__ == "__main__":
    main()
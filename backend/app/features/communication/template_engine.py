"""Module 9C — the reusable Template Engine. Deliberately minimal: `{{variable_name}}`
substitution only, no conditionals/loops — the brief asks for a reusable template
engine, not a general-purpose templating language. Missing variables are left as the
literal `{{name}}` placeholder rather than raising, so a template author's typo doesn't
take down the whole queue processor; `find_missing_variables` lets the Template
Management UI warn about that before a template is ever used.
"""

import re

_VARIABLE_PATTERN = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def render(template_text: str, variables: dict[str, str]) -> str:
    def _substitute(match: re.Match[str]) -> str:
        name = match.group(1)
        return variables.get(name, match.group(0))

    return _VARIABLE_PATTERN.sub(_substitute, template_text)


def extract_variable_names(template_text: str) -> list[str]:
    return sorted(set(_VARIABLE_PATTERN.findall(template_text)))


def find_missing_variables(template_text: str, variables: dict[str, str]) -> list[str]:
    return [name for name in extract_variable_names(template_text) if name not in variables]

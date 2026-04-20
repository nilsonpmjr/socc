# Configuration file for the Sphinx documentation builder.

project = "SOCC"
copyright = "2026, SOCC Contributors"
author = "SOCC Contributors"
release = "0.1"
version = "0.1"

extensions = [
    "myst_parser",
    "sphinx_copybutton",
]

exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

source_suffix = {
    ".md": "markdown",
    ".rst": "restructuredtext",
}

root_doc = "index"

html_theme = "furo"
html_title = "SOCC Documentation"

html_theme_options = {
    "navigation_with_keys": True,
    "source_repository": "https://github.com/nilsonpmjr/socc/",
    "source_branch": "main",
    "source_directory": "docs/",
    "light_css_variables": {
        "color-brand-primary": "#0f766e",
        "color-brand-content": "#0f766e",
    },
    "dark_css_variables": {
        "color-brand-primary": "#34d399",
        "color-brand-content": "#34d399",
    },
}

copybutton_prompt_text = r"^\$ |^>>> "
copybutton_prompt_is_regexp = True

myst_enable_extensions = [
    "colon_fence",
]

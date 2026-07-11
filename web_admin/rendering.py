from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, select_autoescape


PACKAGE_ROOT = Path(__file__).resolve().parent
TEMPLATE_DIR = PACKAGE_ROOT / "templates"
STATIC_DIR = PACKAGE_ROOT / "static"


class TemplateRenderer:
    def __init__(self) -> None:
        self.environment = Environment(
            loader=FileSystemLoader(TEMPLATE_DIR),
            autoescape=select_autoescape(("html", "xml")),
            enable_async=False,
        )

    def render(self, template_name: str, **context: Any) -> str:
        return self.environment.get_template(template_name).render(**context)

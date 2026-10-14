"""Shared policy for reproducible Windows dependency lock generation."""

from __future__ import annotations

import re
from pathlib import Path


LOCK_GENERATOR_PIP_VERSION = "26.2.1"
_INCLUDE = re.compile(r"^(?:-r|--requirement)\s+(.+)$")
_PIN = re.compile(r"^(?P<name>[A-Za-z0-9][A-Za-z0-9._-]*)==(?P<version>[A-Za-z0-9][A-Za-z0-9.+!_-]*)$")
_NAME_NORMALIZATION = re.compile(r"[-_.]+")


class RequirementInputError(ValueError):
    """Raised when an input manifest is outside the exact-pin policy."""


def normalized_name(name: str) -> str:
    return _NAME_NORMALIZATION.sub("-", name).lower()


def parse_requirement_inputs(path: Path, project_root: Path) -> dict[str, str]:
    """Read exact direct pins from a manifest and its recursive local includes."""
    root = project_root.resolve()
    pins: dict[str, str] = {}
    active: set[Path] = set()

    def visit(current: Path) -> None:
        resolved = current.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise RequirementInputError(f"Requirement include escapes the project: {current}.") from exc
        if resolved in active:
            raise RequirementInputError(f"Requirement include cycle at {current}.")
        if not resolved.is_file():
            raise RequirementInputError(f"Requirement input does not exist: {current}.")

        active.add(resolved)
        try:
            for line_number, source_line in enumerate(
                resolved.read_text(encoding="utf-8").splitlines(), start=1
            ):
                line = source_line.split("#", 1)[0].strip()
                if not line:
                    continue
                include = _INCLUDE.fullmatch(line)
                if include:
                    visit(resolved.parent / include.group(1).strip())
                    continue
                pin = _PIN.fullmatch(line)
                if pin is None:
                    raise RequirementInputError(
                        f"{resolved}:{line_number} must be an exact name==version pin "
                        "or a local -r include."
                    )
                name = normalized_name(pin.group("name"))
                version = pin.group("version")
                existing = pins.get(name)
                if existing is not None and existing != version:
                    raise RequirementInputError(
                        f"Conflicting direct pins for {name}: {existing} and {version}."
                    )
                pins[name] = version
        finally:
            active.remove(resolved)

    visit(path)
    if not pins:
        raise RequirementInputError(f"{path} contains no exact direct pins.")
    return pins

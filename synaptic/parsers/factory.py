"""Factory for obtaining the correct language parser at runtime.

Adding support for a new language requires only:

1. Creating a new subclass of :class:`BaseLanguageParser`.
2. Registering it via :meth:`ParserFactory.register`.
"""

from __future__ import annotations

import pathlib
from typing import Type

import structlog

from synaptic.parsers.base import BaseLanguageParser

logger = structlog.get_logger(__name__)


class ParserFactory:
    """Registry-based factory that maps language names to parser classes.

    Usage::

        factory = ParserFactory(repo_root)
        factory.register("python", PythonParser)
        parser = factory.get("python")
    """

    def __init__(self, repo_root: pathlib.Path) -> None:
        self._repo_root = repo_root.resolve()
        self._registry: dict[str, Type[BaseLanguageParser]] = {}
        self._instances: dict[str, BaseLanguageParser] = {}

    def register(self, language: str, parser_cls: Type[BaseLanguageParser]) -> None:
        """Register a parser class for *language*.

        Args:
            language: Lowercase language identifier (e.g. ``"python"``).
            parser_cls: A concrete subclass of :class:`BaseLanguageParser`.
        """
        self._registry[language] = parser_cls
        logger.debug("parser_registered", language=language, cls=parser_cls.__name__)

    def get(self, language: str) -> BaseLanguageParser | None:
        """Return a (cached) parser instance for *language*.

        Args:
            language: Lowercase language identifier.

        Returns:
            A parser instance, or ``None`` if no parser is registered for
            the requested language.
        """
        if language in self._instances:
            return self._instances[language]

        cls = self._registry.get(language)
        if cls is None:
            logger.warning("no_parser_registered", language=language)
            return None

        instance = cls(self._repo_root)
        self._instances[language] = instance
        return instance

    @property
    def supported_languages(self) -> list[str]:
        """Return a sorted list of registered language identifiers."""
        return sorted(self._registry.keys())

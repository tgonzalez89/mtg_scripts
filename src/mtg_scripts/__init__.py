"""Utilities for automating Magic: The Gathering workflows."""

from importlib.metadata import version

__version__: str = version("mtg-scripts")

__all__: list[str] = ["__version__"]

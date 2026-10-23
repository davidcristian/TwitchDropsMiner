"""The strings the app shows to the user, their types, and `_`, which returns one in the current language."""
from __future__ import annotations

from .english import default_translation
from .translator import Translator, _, save_template

__all__ = ["Translator", "_", "default_translation", "save_template"]

"""Fournisseurs de modeles : API, CLI externe, simulation deterministe."""

from .base import Completion, Message, Provider, ProviderError, render
from .cli import CliProvider
from .openai_compat import OpenAiCompatProvider
from .registry import KNOWN_CLIS, Registry, detect_clis, from_env
from .simulated import Persona, SimulatedProvider, make_panel

__all__ = [
    "KNOWN_CLIS",
    "CliProvider",
    "Completion",
    "Message",
    "OpenAiCompatProvider",
    "Persona",
    "Provider",
    "ProviderError",
    "Registry",
    "SimulatedProvider",
    "detect_clis",
    "from_env",
    "make_panel",
    "render",
]

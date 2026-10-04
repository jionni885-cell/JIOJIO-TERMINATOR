"""Fournisseurs de modeles : API, CLI externe, simulation deterministe."""

from .base import Completion, Message, Provider, ProviderError, render
from .cli import CliProvider
from .openai_compat import OpenAiCompatProvider
from .registry import KNOWN_CLIS, Registry, detect_clis, from_env
from .simulated import Persona, SimulatedProvider, make_panel

__all__ = [
    "Completion",
    "Message",
    "Provider",
    "ProviderError",
    "render",
    "CliProvider",
    "OpenAiCompatProvider",
    "Registry",
    "KNOWN_CLIS",
    "detect_clis",
    "from_env",
    "Persona",
    "SimulatedProvider",
    "make_panel",
]

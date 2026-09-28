"""Penguin — pre-delivery quality control for eDiscovery productions."""

__version__ = "0.1.0"

from .checks import Finding, ProductionSummary, run_all  # noqa: F401
from .loadfile import read_dat, read_opt  # noqa: F401

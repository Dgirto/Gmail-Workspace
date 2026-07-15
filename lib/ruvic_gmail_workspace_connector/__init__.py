"""Conector Ruvic para Gmail (Google Workspace) vía cuenta de servicio
con delegación de dominio."""

from .client import GmailWorkspaceClient
from .config import ENV_PREFIX, GmailWorkspaceConfig
from .exceptions import (
    GmailWorkspaceAuthError,
    GmailWorkspaceConnectorError,
    GmailWorkspaceDataError,
    GmailWorkspaceNetworkError,
)
from .logging_utils import setup_logging

__all__ = [
    "ENV_PREFIX",
    "GmailWorkspaceAuthError",
    "GmailWorkspaceClient",
    "GmailWorkspaceConfig",
    "GmailWorkspaceConnectorError",
    "GmailWorkspaceDataError",
    "GmailWorkspaceNetworkError",
    "setup_logging",
]

__version__ = "1.0.0"

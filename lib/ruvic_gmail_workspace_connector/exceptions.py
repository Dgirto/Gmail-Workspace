"""Excepciones propias del conector Gmail Workspace.

Separan los tres tipos de fallo que el usuario debe distinguir:
autenticación, red/servidor y datos. Nunca exponemos excepciones
crípticas del cliente HTTP subyacente.
"""


class GmailWorkspaceConnectorError(Exception):
    """Error base del conector."""


class GmailWorkspaceAuthError(GmailWorkspaceConnectorError):
    """Credenciales inválidas o delegación de dominio no autorizada para el buzón impersonado."""


class GmailWorkspaceNetworkError(GmailWorkspaceConnectorError):
    """No se pudo alcanzar la API de Gmail (red, timeout, error temporal del servidor)."""


class GmailWorkspaceDataError(GmailWorkspaceConnectorError):
    """La operación es válida pero el recurso no existe o los datos son inválidos."""

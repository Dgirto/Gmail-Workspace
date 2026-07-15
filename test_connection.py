"""Prueba de conexión estándar del conector gmail_workspace.

Firma estándar Ruvic: def test_connection() -> tuple[bool, str]
- Lee la configuración EXCLUSIVAMENTE de las env vars RUVIC_GMAIL_WORKSPACE_*.
- Nunca lanza excepciones; retorna (ok, mensaje).

Ejecutable también como script para pruebas locales:
    python test_connection.py
"""

from __future__ import annotations


def test_connection() -> tuple[bool, str]:
    """Verifica la delegación de dominio impersonando el buzón de prueba
    (RUVIC_GMAIL_WORKSPACE_DEFAULT_MAILBOX) y consultando su perfil."""
    try:
        from ruvic_gmail_workspace_connector import (
            GmailWorkspaceAuthError,
            GmailWorkspaceClient,
            GmailWorkspaceConfig,
            GmailWorkspaceDataError,
            GmailWorkspaceNetworkError,
        )
    except ImportError:
        return (
            False,
            "La librería ruvic-gmail-workspace-connector no está instalada. "
            "Instala con: pip install git+https://github.com/Dgirto/"
            "Gmail-Workspace.git#subdirectory=lib",
        )

    try:
        config = GmailWorkspaceConfig.from_env()
    except ValueError as exc:
        return False, str(exc)

    try:
        client = GmailWorkspaceClient(mailbox=config.default_mailbox, config=config)
    except GmailWorkspaceDataError as exc:
        return False, str(exc)

    try:
        client.ping()
    except GmailWorkspaceAuthError as exc:
        return False, f"Autenticación fallida: {exc}"
    except GmailWorkspaceNetworkError as exc:
        return False, f"Error de red: {exc}"
    except GmailWorkspaceDataError as exc:
        return False, f"Error de datos: {exc}"
    except Exception as exc:  # red de seguridad: jamás propagar
        return False, f"Error inesperado: {exc}"

    return (
        True,
        f"Conexión exitosa al buzón {config.default_mailbox} (delegación de dominio)",
    )


if __name__ == "__main__":
    ok, message = test_connection()
    print(f"{'OK' if ok else 'FALLO'}: {message}")
    raise SystemExit(0 if ok else 1)

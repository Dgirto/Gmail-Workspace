"""Configuración del conector leída desde variables de entorno.

Convención de la plataforma: cada campo del formulario de configuración
llega como variable de entorno {ENV_PREFIX}{CAMPO} en mayúsculas.
Para este conector el prefijo es RUVIC_GMAIL_WORKSPACE_.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any

ENV_PREFIX = "RUVIC_GMAIL_WORKSPACE_"


def _read_timeout(default: int = 30) -> int:
    """Lee REQUEST_TIMEOUT tratando el string vacío como ausente: la
    plataforma envía "" cuando el campo opcional queda en blanco."""
    raw = (os.environ.get(f"{ENV_PREFIX}REQUEST_TIMEOUT") or "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(
            f"{ENV_PREFIX}REQUEST_TIMEOUT debe ser un número entero de segundos, no {raw!r}."
        ) from None
    if value <= 0:
        raise ValueError(f"{ENV_PREFIX}REQUEST_TIMEOUT debe ser mayor que 0, no {value}.")
    return value


@dataclass(frozen=True)
class GmailWorkspaceConfig:
    """Credenciales de la cuenta de servicio con delegación de dominio.

    Una sola credencial (esta cuenta de servicio) puede impersonar
    cualquier buzón del dominio Google Workspace autorizado en el Admin
    Console, sin necesidad de autorización individual por usuario ni
    tokens que expiren.
    """

    service_account_info: dict[str, Any]
    default_mailbox: str
    request_timeout: int = 30

    @classmethod
    def from_env(cls) -> "GmailWorkspaceConfig":
        """Construye la configuración desde las variables RUVIC_GMAIL_WORKSPACE_*.

        Raises:
            ValueError: si falta alguna variable obligatoria o el JSON de
                la cuenta de servicio no es válido.

        Ejemplo:
            >>> config = GmailWorkspaceConfig.from_env()
            >>> config.default_mailbox
            'facturacion@tuempresa.com'
        """
        missing = [
            f"{ENV_PREFIX}{name}"
            for name in ("SERVICE_ACCOUNT_JSON", "DEFAULT_MAILBOX")
            if not os.environ.get(f"{ENV_PREFIX}{name}")
        ]
        if missing:
            raise ValueError(
                "Faltan variables de entorno del conector gmail_workspace: "
                + ", ".join(missing)
                + ". Configura el conector en Settings -> Conectores."
            )

        raw_json = os.environ[f"{ENV_PREFIX}SERVICE_ACCOUNT_JSON"]
        try:
            info = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise ValueError(
                f"{ENV_PREFIX}SERVICE_ACCOUNT_JSON no contiene un JSON válido: {exc}. "
                "Verifica que copiaste el archivo de credenciales completo, sin "
                "recortar ni modificar su contenido."
            ) from exc

        missing_keys = [k for k in ("client_email", "private_key", "client_id") if k not in info]
        if missing_keys:
            raise ValueError(
                "El JSON de la cuenta de servicio no tiene el formato esperado "
                f"(faltan campos: {', '.join(missing_keys)}). Descárgalo de nuevo "
                "desde Google Cloud Console -> IAM y administración -> Cuentas de servicio."
            )

        return cls(
            service_account_info=info,
            default_mailbox=os.environ[f"{ENV_PREFIX}DEFAULT_MAILBOX"],
            request_timeout=_read_timeout(),
        )

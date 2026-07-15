"""Cliente de Gmail (Google Workspace) vía cuenta de servicio con
delegación de dominio.

Paridad de API con ruvic_gmail_connector (CON-005, OAuth2 por usuario):
mismos métodos y misma forma de retorno. La diferencia es el constructor
—recibe el buzón a impersonar— y que una sola credencial (esta cuenta de
servicio) puede actuar como cualquier buzón autorizado del dominio, sin
volver a autorizar por usuario ni gestionar expiración de tokens.

Capacidades:
- list_messages():              buscar/listar correos con filtros (sintaxis
                                 de búsqueda de Gmail).
- get_message():                leer el detalle y cuerpo de un correo.
- send_message():                enviar un correo.
- send_message_with_attachment(): enviar un correo con un archivo adjunto.

Las credenciales SIEMPRE provienen de variables de entorno
RUVIC_GMAIL_WORKSPACE_* (ver config.GmailWorkspaceConfig.from_env).
Prohibido hardcodearlas.
"""

from __future__ import annotations

import base64
import mimetypes
import re
import socket
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any

from google.auth.exceptions import GoogleAuthError, RefreshError
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .config import GmailWorkspaceConfig
from .exceptions import (
    GmailWorkspaceAuthError,
    GmailWorkspaceConnectorError,
    GmailWorkspaceDataError,
    GmailWorkspaceNetworkError,
)
from .logging_utils import get_logger

_SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
]
_MAX_ATTACHMENT_BYTES = 20 * 1024 * 1024
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _wrap_http_error(exc: HttpError) -> GmailWorkspaceConnectorError:
    """Traduce un error HTTP de la API de Gmail a una excepción propia,
    sin dejar escapar nunca el tipo crudo del cliente HTTP."""
    status = exc.resp.status if getattr(exc, "resp", None) is not None else None
    if status in (401, 403):
        return GmailWorkspaceAuthError(
            "Credenciales inválidas o sin permiso suficiente sobre este buzón. "
            "Verifica que el Client ID de la cuenta de servicio esté autorizado "
            "en el Admin Console de Workspace con los scopes gmail.readonly y "
            "gmail.send."
        )
    if status == 404:
        return GmailWorkspaceDataError("El mensaje o recurso solicitado no existe.")
    if status == 429 or (status is not None and status >= 500):
        return GmailWorkspaceNetworkError(
            f"Gmail API no respondió correctamente (HTTP {status}). "
            "Puede ser un límite de cuota temporal; reintenta en unos segundos."
        )
    return GmailWorkspaceDataError(f"Error de Gmail API (HTTP {status}): {exc}")


def _validate_no_header_injection(**fields: str | None) -> None:
    """Evita inyección de cabeceras de correo (CRLF) en campos que se
    interpolan directamente en el mensaje MIME (to/cc/bcc/subject)."""
    for name, value in fields.items():
        if value and ("\r" in value or "\n" in value):
            raise GmailWorkspaceDataError(
                f"El campo '{name}' contiene saltos de línea, no permitido "
                "(previene inyección de cabeceras de correo)."
            )


class GmailWorkspaceClient:
    """Cliente de Gmail para un buzón específico de un dominio Google
    Workspace, vía cuenta de servicio con delegación de dominio.

    Args:
        mailbox: correo del buzón del dominio a impersonar (ej.
            "facturacion@tuempresa.com"). La cuenta de servicio debe estar
            autorizada en el Admin Console para el dominio de ese correo.
        config: configuración de conexión. Si se omite, se lee de las
            variables de entorno RUVIC_GMAIL_WORKSPACE_* (comportamiento
            estándar en el runtime de la plataforma).

    Ejemplo:
        >>> client = GmailWorkspaceClient(mailbox="facturacion@tuempresa.com")
        >>> client.list_messages(query="is:unread", max_results=5)
        [{'id': '18f2a1', 'from': 'cliente@x.com', 'subject': 'Factura', ...}]
    """

    def __init__(
        self, mailbox: str, config: GmailWorkspaceConfig | None = None
    ) -> None:
        if not _EMAIL_RE.match(mailbox):
            raise GmailWorkspaceDataError(
                f"mailbox={mailbox!r} no parece un correo válido "
                "(ej. 'facturacion@tuempresa.com')."
            )
        self.mailbox = mailbox
        self.config = config or GmailWorkspaceConfig.from_env()
        self._logger = get_logger()
        self._service: Any = None

    # ------------------------------------------------------------------ #
    # Conexión
    # ------------------------------------------------------------------ #

    def _get_service(self) -> Any:
        if self._service is not None:
            return self._service
        try:
            credentials = service_account.Credentials.from_service_account_info(
                self.config.service_account_info,
                scopes=_SCOPES,
                subject=self.mailbox,
            )
        except (ValueError, KeyError) as exc:
            raise GmailWorkspaceAuthError(
                f"El JSON de la cuenta de servicio es inválido o le faltan campos: {exc}"
            ) from exc
        try:
            self._service = build(
                "gmail",
                "v1",
                credentials=credentials,
                cache_discovery=False,
                static_discovery=False,
            )
        except (GoogleAuthError, OSError) as exc:
            raise GmailWorkspaceNetworkError(
                f"No se pudo inicializar el cliente de Gmail: {exc}"
            ) from exc
        return self._service

    def ping(self) -> bool:
        """Verifica la conexión consultando el perfil del buzón impersonado.

        Returns:
            True si la conexión y la delegación funcionan.

        Raises:
            GmailWorkspaceAuthError / GmailWorkspaceNetworkError / GmailWorkspaceDataError.
        """
        service = self._get_service()
        try:
            profile = service.users().getProfile(userId="me").execute(num_retries=1)
        except HttpError as exc:
            raise _wrap_http_error(exc) from exc
        except RefreshError as exc:
            client_id = self.config.service_account_info.get("client_id", "?")
            raise GmailWorkspaceAuthError(
                f"No se pudo autenticar como {self.mailbox!r} (unauthorized_client). "
                "Revisa en el Admin Console de Google Workspace (Seguridad -> Control "
                "de acceso a las API -> Delegación en todo el dominio) que: "
                f"1) el Client ID '{client_id}' esté agregado, "
                "2) los scopes autorizados sean exactamente "
                "'https://www.googleapis.com/auth/gmail.readonly,"
                "https://www.googleapis.com/auth/gmail.send' (separados por coma, "
                "sin espacios extra), y 3) el buzón pertenezca a ese mismo dominio."
            ) from exc
        except (socket.error, TimeoutError, OSError) as exc:
            raise GmailWorkspaceNetworkError(
                f"No se pudo conectar con Gmail API: {exc}"
            ) from exc
        self._logger.info("Ping exitoso, buzón: %s", profile.get("emailAddress"))
        return True

    # ------------------------------------------------------------------ #
    # Capacidad 1 — Buscar/listar correos con filtros
    # ------------------------------------------------------------------ #

    def list_messages(self, query: str = "", max_results: int = 20) -> list[dict[str, Any]]:
        """Busca correos en el buzón impersonado usando la sintaxis de
        búsqueda de Gmail.

        Args:
            query: filtro de búsqueda de Gmail (ej. "is:unread",
                "from:cliente@dominio.com"). Cadena vacía = todos.
            max_results: máximo de correos a retornar (default 20, máximo 100).

        Returns:
            Lista de dicts: {"id", "thread_id", "subject", "from", "date", "snippet"}.

        Ejemplo:
            >>> client.list_messages(query="is:unread", max_results=5)
            [{'id': '18f2a1', 'from': 'a@b.com', 'subject': 'Factura', ...}]
        """
        service = self._get_service()
        max_results = max(1, min(int(max_results), 100))
        try:
            resp = (
                service.users()
                .messages()
                .list(userId="me", q=query, maxResults=max_results)
                .execute(num_retries=1)
            )
        except HttpError as exc:
            raise _wrap_http_error(exc) from exc

        message_ids = [m["id"] for m in resp.get("messages", [])]
        results: list[dict[str, Any]] = []
        for mid in message_ids:
            try:
                msg = (
                    service.users()
                    .messages()
                    .get(
                        userId="me",
                        id=mid,
                        format="metadata",
                        metadataHeaders=["Subject", "From", "Date"],
                    )
                    .execute(num_retries=1)
                )
            except HttpError as exc:
                raise _wrap_http_error(exc) from exc
            headers = {
                h["name"]: h["value"]
                for h in msg.get("payload", {}).get("headers", [])
            }
            results.append(
                {
                    "id": msg["id"],
                    "thread_id": msg.get("threadId"),
                    "subject": headers.get("Subject", ""),
                    "from": headers.get("From", ""),
                    "date": headers.get("Date", ""),
                    "snippet": msg.get("snippet", ""),
                }
            )
        self._logger.info(
            "Se listaron %d mensajes de %s (query=%r)", len(results), self.mailbox, query
        )
        return results

    # ------------------------------------------------------------------ #
    # Capacidad 2 — Leer el detalle de un correo
    # ------------------------------------------------------------------ #

    def get_message(self, message_id: str) -> dict[str, Any]:
        """Obtiene el detalle completo (incluido el cuerpo) de un correo.

        Args:
            message_id: ID del mensaje (obtenido de list_messages).

        Returns:
            Dict con: id, thread_id, subject, from, to, date, body_text.

        Ejemplo:
            >>> client.get_message("18f2a1")
            {'id': '18f2a1', 'subject': 'Hola', 'body_text': 'Buen día...', ...}
        """
        service = self._get_service()
        try:
            msg = (
                service.users()
                .messages()
                .get(userId="me", id=message_id, format="full")
                .execute(num_retries=1)
            )
        except HttpError as exc:
            raise _wrap_http_error(exc) from exc
        headers = {
            h["name"]: h["value"] for h in msg.get("payload", {}).get("headers", [])
        }
        return {
            "id": msg["id"],
            "thread_id": msg.get("threadId"),
            "subject": headers.get("Subject", ""),
            "from": headers.get("From", ""),
            "to": headers.get("To", ""),
            "date": headers.get("Date", ""),
            "body_text": _extract_plain_text(msg.get("payload", {})),
        }

    # ------------------------------------------------------------------ #
    # Capacidad 3 — Enviar un correo
    # ------------------------------------------------------------------ #

    def send_message(
        self,
        to: str,
        subject: str,
        body_text: str,
        cc: str | None = None,
        bcc: str | None = None,
    ) -> dict[str, Any]:
        """Envía un correo de texto plano desde el buzón impersonado.

        Args:
            to: destinatario.
            subject: asunto del correo.
            body_text: cuerpo en texto plano.
            cc: copia (opcional).
            bcc: copia oculta (opcional).

        Returns:
            Dict con: id, thread_id del mensaje enviado.

        Ejemplo:
            >>> client.send_message("cliente@dominio.com", "Hola", "Buen día...")
            {'id': '18f2a1', 'thread_id': '18f2a1'}
        """
        _validate_no_header_injection(to=to, subject=subject, cc=cc, bcc=bcc)
        service = self._get_service()
        message = MIMEText(body_text, "plain", "utf-8")
        message["to"] = to
        message["from"] = self.mailbox
        message["subject"] = subject
        if cc:
            message["cc"] = cc
        if bcc:
            message["bcc"] = bcc
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        try:
            sent = (
                service.users()
                .messages()
                .send(userId="me", body={"raw": raw})
                .execute(num_retries=1)
            )
        except HttpError as exc:
            raise _wrap_http_error(exc) from exc
        self._logger.info("Correo enviado a %s desde %s", to, self.mailbox)
        return {"id": sent["id"], "thread_id": sent.get("threadId")}

    # ------------------------------------------------------------------ #
    # Capacidad 4 — Enviar un correo con adjunto
    # ------------------------------------------------------------------ #

    def send_message_with_attachment(
        self,
        to: str,
        subject: str,
        body_text: str,
        attachment_path: str,
        cc: str | None = None,
        bcc: str | None = None,
    ) -> dict[str, Any]:
        """Envía un correo de texto plano con un archivo adjunto.

        Args:
            to: destinatario.
            subject: asunto del correo.
            body_text: cuerpo en texto plano.
            attachment_path: ruta local del archivo a adjuntar (máx. 20 MB).
            cc: copia (opcional).
            bcc: copia oculta (opcional).

        Returns:
            Dict con: id, thread_id del mensaje enviado.
        """
        _validate_no_header_injection(to=to, subject=subject, cc=cc, bcc=bcc)
        path = Path(attachment_path)
        if not path.is_file():
            raise GmailWorkspaceDataError(f"El archivo adjunto no existe: {attachment_path}")
        size = path.stat().st_size
        if size > _MAX_ATTACHMENT_BYTES:
            raise GmailWorkspaceDataError(
                f"El adjunto pesa {size / 1_048_576:.1f} MB, supera el límite de "
                f"{_MAX_ATTACHMENT_BYTES / 1_048_576:.0f} MB soportado por el conector."
            )

        service = self._get_service()
        message = MIMEMultipart()
        message["to"] = to
        message["from"] = self.mailbox
        message["subject"] = subject
        if cc:
            message["cc"] = cc
        if bcc:
            message["bcc"] = bcc
        message.attach(MIMEText(body_text, "plain", "utf-8"))

        content_type, _ = mimetypes.guess_type(path.name)
        content_type = content_type or "application/octet-stream"
        _, subtype = content_type.split("/", 1)
        with path.open("rb") as f:
            part = MIMEApplication(f.read(), _subtype=subtype)
        part.add_header("Content-Disposition", "attachment", filename=path.name)
        message.attach(part)

        raw = base64.urlsafe_b64encode(message.as_bytes()).decode("ascii")
        try:
            sent = (
                service.users()
                .messages()
                .send(userId="me", body={"raw": raw})
                .execute(num_retries=1)
            )
        except HttpError as exc:
            raise _wrap_http_error(exc) from exc
        self._logger.info(
            "Correo con adjunto '%s' enviado a %s desde %s", path.name, to, self.mailbox
        )
        return {"id": sent["id"], "thread_id": sent.get("threadId")}


def _extract_plain_text(payload: dict[str, Any]) -> str:
    """Recorre las partes MIME de un payload de Gmail API y retorna el
    primer text/plain decodificado que encuentre."""
    if payload.get("mimeType") == "text/plain" and "data" in payload.get("body", {}):
        return _decode_body(payload["body"]["data"])
    for part in payload.get("parts", []) or []:
        text = _extract_plain_text(part)
        if text:
            return text
    return ""


def _decode_body(data: str) -> str:
    padded = data + "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(padded).decode("utf-8", errors="replace")

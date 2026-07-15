"""Validacion local del conector gmail_workspace: ejercita las 4 capacidades.

Uso:
    python validate_local.py

Requiere las variables RUVIC_GMAIL_WORKSPACE_* exportadas en el entorno,
y que el buzon RUVIC_GMAIL_WORKSPACE_DEFAULT_MAILBOX este autorizado via
delegacion de dominio.
"""

import pathlib
import tempfile

from ruvic_gmail_workspace_connector import (
    GmailWorkspaceClient,
    GmailWorkspaceConfig,
    setup_logging,
)

setup_logging("INFO")
config = GmailWorkspaceConfig.from_env()
mailbox = config.default_mailbox
client = GmailWorkspaceClient(mailbox=mailbox, config=config)

print(f"Impersonando buzon: {mailbox}")

print("== 1. Listar correos (los 5 mas recientes) ==")
messages = client.list_messages(query="", max_results=5)
for m in messages:
    print(f"  [{m['id']}] {m['from']} - {m['subject']!r} ({m['date']})")

if messages:
    print("== 2. Leer detalle del primer correo ==")
    detail = client.get_message(messages[0]["id"])
    preview = (detail["body_text"] or "")[:200].replace("\n", " ")
    print(f"  De: {detail['from']}")
    print(f"  Asunto: {detail['subject']}")
    print(f"  Cuerpo (preview): {preview!r}")
else:
    print("== 2. Sin correos en la bandeja para leer detalle ==")

print("== 3. Enviar correo de prueba ==")
sent = client.send_message(
    to=mailbox,
    subject="Prueba conector Gmail Workspace Ruvic",
    body_text="Este es un correo de prueba enviado por validate_local.py",
)
print(f"  Enviado: id={sent['id']} thread_id={sent['thread_id']}")

print("== 4. Enviar correo con adjunto ==")
with tempfile.NamedTemporaryFile(
    mode="w", suffix=".txt", delete=False, encoding="utf-8"
) as tmp:
    tmp.write("Archivo de prueba del conector Gmail Workspace Ruvic.\n")
    tmp_path = tmp.name

try:
    sent_attach = client.send_message_with_attachment(
        to=mailbox,
        subject="Prueba conector Gmail Workspace Ruvic (con adjunto)",
        body_text="Este correo incluye un adjunto de prueba.",
        attachment_path=tmp_path,
    )
    print(f"  Enviado: id={sent_attach['id']} thread_id={sent_attach['thread_id']}")
finally:
    pathlib.Path(tmp_path).unlink(missing_ok=True)

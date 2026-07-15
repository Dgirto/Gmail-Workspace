---
name: gmail-workspace
description: >
  Usa la librería ruvic_gmail_workspace_connector para leer y enviar
  correos en uno o varios buzones de un dominio Google Workspace, vía
  cuenta de servicio con delegación de dominio (impersonación) - buscar/
  listar correos con filtros (list_messages), leer el detalle de un correo
  (get_message), enviar un correo (send_message) y enviar un correo con
  adjunto (send_message_with_attachment). Úsala cuando el usuario pida
  leer, buscar, filtrar o enviar correos en un buzón corporativo de
  Google Workspace, especialmente si menciona varios buzones del mismo
  dominio (ej. "facturacion@empresa.com", "soporte@empresa.com") sin
  volver a autorizar cada uno por separado. Para un buzón de Gmail
  personal o un único buzón corporativo autorizado individualmente, usa
  en su lugar el conector `gmail` (OAuth2) o `gmail_imap` (IMAP/SMTP).
triggers:
- gmail
- correo
- correos
- email
- enviar correo
- leer correos
- bandeja de entrada
- buzón
- workspace
- delegación de dominio
- múltiples buzones
---

# Conector Gmail Workspace (ruvic_gmail_workspace_connector)

Librería Python para leer y enviar correos en buzones de un dominio **Google Workspace**, usando una **cuenta de servicio con delegación de dominio**. Está **preinstalada en el runtime** cuando el conector está configurado (si no, instálala con `pip install git+https://github.com/Dgirto/Gmail-Workspace.git#subdirectory=lib`).

## Cuándo usar este conector vs. los otros dos Gmail

Ruvic tiene tres conectores de Gmail; elige según el caso:

| Situación | Conector a usar |
|-----------|------------------|
| Gmail personal (@gmail.com) o un solo buzón corporativo, autorizado individualmente | `gmail` (OAuth2) — ver su `SKILL.md` |
| Gmail personal o corporativo, sin acceso a Google Cloud Console | `gmail_imap` (IMAP/SMTP) — ver su `SKILL.md` |
| **Google Workspace, una sola credencial para impersonar varios buzones del dominio** (ej. `facturacion@empresa.com`, `soporte@empresa.com`), sin re-autorizar cada uno | **`gmail_workspace` (este)** |

Este conector **no funciona con cuentas Gmail personales** — Google no permite delegación de dominio fuera de Workspace.

## Regla crítica de credenciales

El código generado **NUNCA hardcodea credenciales**. Siempre se leen de variables de entorno, disponibles cuando el conector `gmail_workspace` está configurado:

| Variable | Contenido |
|----------|-----------|
| `RUVIC_GMAIL_WORKSPACE_SERVICE_ACCOUNT_JSON` | JSON completo de la cuenta de servicio de Google Cloud |
| `RUVIC_GMAIL_WORKSPACE_DEFAULT_MAILBOX` | Buzón usado solo para el test de conexión |
| `RUVIC_GMAIL_WORKSPACE_REQUEST_TIMEOUT` | (opcional) timeout en segundos, default 30 |

Si estas variables NO existen, el conector no está configurado: no generes código que lo use; indica al usuario que lo configure en **Settings → Conectores**. El código generado **NUNCA** usa nombres con segmento de alias (`_DEFAULT_INSTANCIA_`, `_PRODUCCION_`, etc.) salvo que aparezcan en una sección autogenerada `## Variables en tu entorno` al final de este skill.

## Autenticación / conexión (siempre igual)

El buzón a impersonar se pasa en el **constructor**, no en cada método — así se comparte la misma sesión/servicio autenticado entre varias llamadas al mismo buzón:

```python
from ruvic_gmail_workspace_connector import GmailWorkspaceClient

# Impersona cualquier buzón autorizado del dominio (no hace falta
# que sea el mismo que RUVIC_GMAIL_WORKSPACE_DEFAULT_MAILBOX)
client = GmailWorkspaceClient(mailbox="facturacion@tuempresa.com")
```

Para trabajar con varios buzones, crea una instancia por buzón:

```python
buzones = ["facturacion@tuempresa.com", "soporte@tuempresa.com"]
clientes = {mailbox: GmailWorkspaceClient(mailbox=mailbox) for mailbox in buzones}
```

## Capacidad 1 — Buscar/listar correos con filtros

```python
tables = client.list_messages(query="is:unread", max_results=20)
for m in tables:
    print(f"{m['date']} | {m['from']} | {m['subject']}")
```

## Capacidad 2 — Leer el detalle de un correo

```python
detail = client.get_message(tables[0]["id"])
print(detail["subject"], detail["from"], detail["body_text"])
```

## Capacidad 3 — Enviar un correo

```python
result = client.send_message(
    to="cliente@dominio.com",
    subject="Actualización del ticket",
    body_text="Buen día, le confirmamos que el ticket fue resuelto.",
    cc="supervisor@tuempresa.com",  # opcional
)
```

## Capacidad 4 — Enviar un correo con adjunto

```python
result = client.send_message_with_attachment(
    to="cliente@dominio.com",
    subject="Reporte mensual",
    body_text="Adjunto el reporte solicitado.",
    attachment_path="/tmp/reporte.pdf",  # máximo 20 MB
)
```

## Manejo de errores

```python
from ruvic_gmail_workspace_connector import (
    GmailWorkspaceAuthError, GmailWorkspaceDataError, GmailWorkspaceNetworkError,
)

try:
    client.send_message("cliente@dominio.com", "Asunto", "Cuerpo")
except GmailWorkspaceAuthError:
    print("Delegación de dominio no autorizada para este buzón — revisa el Admin Console")
except GmailWorkspaceNetworkError:
    print("Gmail API no respondió — puede ser un límite de cuota temporal")
except GmailWorkspaceDataError as e:
    print(f"Error de datos: {e}")  # ej. archivo adjunto inexistente
```

`GmailWorkspaceAuthError` incluye en su mensaje el Client ID exacto que debe estar autorizado en el Admin Console, y qué revisar (Client ID, scopes exactos, dominio del buzón) — muéstraselo tal cual al usuario cuando ocurra.

## Buenas prácticas al generar código

1. Lee credenciales SOLO de las variables `RUVIC_GMAIL_WORKSPACE_*` (el constructor de `GmailWorkspaceConfig` ya lo hace).
2. Nunca imprimas `RUVIC_GMAIL_WORKSPACE_SERVICE_ACCOUNT_JSON` en logs ni en la salida — es una credencial de máximo cuidado (da acceso potencial a cualquier buzón del dominio, no solo a uno).
3. El `mailbox` del constructor puede ser **cualquier** buzón del dominio autorizado, no solo el de prueba (`DEFAULT_MAILBOX`) — no asumas que son el mismo.
4. Usa `max_results` razonable en `list_messages` (default 20, máximo 100).
5. `attachment_path` debe ser una ruta local accesible en el runtime; el conector rechaza archivos mayores a 20 MB.
6. El scope del conector es de solo lectura + envío (`gmail.readonly`, `gmail.send`): no puede modificar etiquetas, eliminar correos ni cambiar configuración del buzón.

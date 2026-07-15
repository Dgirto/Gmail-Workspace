# Conector Gmail Workspace (CON-005.2)

Conector Ruvic para Gmail en un dominio **Google Workspace**, vía **cuenta
de servicio con delegación de dominio**. Una sola credencial puede
impersonar cualquier buzón autorizado del dominio (`facturacion@empresa.com`,
`soporte@empresa.com`, …) sin re-autorizar cada uno individualmente y sin
tokens que expiren.

Es el tercer conector Gmail del catálogo — ver [CON-005](../CON-005)
(OAuth2, un buzón por autorización) y [CON-005.1](../CON-005.1)
(IMAP/SMTP, autoservicio sin Google Cloud). Este es el único que sirve
para el caso "una empresa, varios buzones, una sola configuración".

**Solo funciona con Google Workspace** — Google no permite delegación de
dominio en cuentas Gmail personales.

## Instalación

```bash
pip install git+https://github.com/Dgirto/Gmail-Workspace.git#subdirectory=lib
```

Python 3.10+. Dependencias: `google-auth` y `google-api-python-client`.

## Obtener credenciales (una sola vez, por dominio Workspace)

Este es el flujo que **requiere participación del superadministrador del
dominio** — es el paso crítico que distingue este conector de los otros dos.

### 1. Proyecto y cuenta de servicio en Google Cloud Console

1. Crea (o reutiliza) un proyecto en [Google Cloud Console](https://console.cloud.google.com/).
2. Habilita la **Gmail API**.
3. Ve a **IAM y administración → Cuentas de servicio → Crear cuenta de servicio**. Dale un nombre (ej. `ruvic-gmail-workspace`) y termina el asistente sin roles adicionales de proyecto.
4. Abre la cuenta de servicio creada → pestaña **Claves** → **Agregar clave → Crear clave nueva → JSON**. Se descarga un archivo `.json` — este es el que va al formulario del conector.
5. En la pestaña **Detalles** de la cuenta de servicio, copia el **ID de cliente único** (una cadena numérica larga, distinta al "ID de cliente de OAuth 2" si aparece uno).

### 2. Delegación de dominio (solo el superadministrador de Workspace puede hacer esto)

1. El superadministrador entra a [admin.google.com](https://admin.google.com/) → **Seguridad → Control de acceso a las API → Delegación en todo el dominio**.
2. Clic en **Agregar nuevo**.
3. **ID de cliente**: pega el ID de cliente único del paso 1.5.
4. **Alcances OAuth**: pega exactamente (separados por coma, sin espacios extra):
   ```
   https://www.googleapis.com/auth/gmail.readonly,https://www.googleapis.com/auth/gmail.send
   ```
5. Guardar.

> Sin este paso, cualquier intento de conexión falla con `unauthorized_client` — el conector detecta este error específico y explica exactamente qué revisar.

## Variables de entorno (`RUVIC_GMAIL_WORKSPACE_*`)

| Variable | Obligatoria | Descripción |
|----------|-------------|-------------|
| `RUVIC_GMAIL_WORKSPACE_SERVICE_ACCOUNT_JSON` | Sí | JSON completo de la cuenta de servicio |
| `RUVIC_GMAIL_WORKSPACE_DEFAULT_MAILBOX` | Sí | Buzón del dominio usado para el botón "Probar conexión" |
| `RUVIC_GMAIL_WORKSPACE_REQUEST_TIMEOUT` | No (default `30`) | Timeout de solicitud en segundos |

## Pruebas locales

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ./lib

export RUVIC_GMAIL_WORKSPACE_SERVICE_ACCOUNT_JSON='{"type": "service_account", ...}'
export RUVIC_GMAIL_WORKSPACE_DEFAULT_MAILBOX=facturacion@tudominio.com

python test_connection.py
python validate_local.py
```

`validate_local.py` envía dos correos de prueba reales (uno con adjunto)
al buzón de prueba configurado.

Prueba también los casos de error (delegación no configurada — el más
importante y el que da `unauthorized_client`, cuenta de servicio con
clave inválida, buzón fuera del dominio autorizado) y verifica que los
mensajes sean claros.

## Notas de integración

- **Paridad de API con CON-005**: mismos métodos (`list_messages`,
  `get_message`, `send_message`, `send_message_with_attachment`) y misma
  forma de retorno — la diferencia es el constructor, que recibe el
  `mailbox` a impersonar.
- **Una credencial, N buzones**: `GmailWorkspaceClient(mailbox="...")`
  acepta cualquier buzón autorizado del dominio, no solo el
  `DEFAULT_MAILBOX` de prueba. El agente puede crear una instancia por
  buzón según lo que pida el usuario.
- **Sin expiración de tokens**: a diferencia de OAuth2, la delegación de
  dominio no genera un `refresh_token` que pueda vencer — el acceso dura
  mientras la delegación siga activa en el Admin Console.
- **`unauthorized_client` manejado explícitamente**: el mensaje de error
  incluye el Client ID exacto de la cuenta de servicio y los tres puntos
  a revisar en el Admin Console (Client ID agregado, scopes exactos,
  dominio del buzón).
- **Credencial de máximo cuidado**: el JSON de la cuenta de servicio, a
  diferencia de un `refresh_token` de OAuth2 (que solo da acceso a un
  buzón), puede impersonar **cualquier** buzón autorizado del dominio.
  Trátalo como la credencial más sensible del conector.
- **Revocación**: para revocar el acceso, el superadministrador elimina
  la entrada de delegación en el Admin Console, o se elimina/rota la
  clave de la cuenta de servicio en Google Cloud Console.
- Los errores HTTP 401/403 de la API se clasifican como
  `GmailWorkspaceAuthError`; 404 como `GmailWorkspaceDataError`; 429 y
  5xx como `GmailWorkspaceNetworkError` (reintentable).

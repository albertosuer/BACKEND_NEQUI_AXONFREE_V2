# NEQUIAXON BOT

Bot de Telegram para gestión de usuarios y cuentas Nequi.

## Configuración

1. **Variables de entorno** (`.env`):
```
TOKEN=8712440774:AAHg1jdYGMaDmmMim7SZNm9GjRrOCUys0ec
TELEGRAM_BOT_TOKEN=8712440774:AAHg1jdYGMaDmmMim7SZNm9GjRrOCUys0ec
PORT=5000
GOOGLE_APPLICATION_CREDENTIALS=firebase_credentials.json
FIREBASE_CREDENTIALS={"type":"service_account","project_id":"nequiaxonfree-7a6f7",...}
```

2. **Credenciales Firebase**: 
   - **Local**: Archivo `firebase_credentials.json`
   - **Railway/Cloud**: Variable de entorno `FIREBASE_CREDENTIALS` con el JSON completo

3. **Configurar IDs en `main.py`**:
```python
ADMIN_PRINCIPAL_1 = "8485352219"  # @AXONDEVUI - Admin Principal ÚNICO
REQUIRED_GROUP_ID = -1003707561305  # Nuevo grupo oficial: https://t.me/Comunidadaxonlabs
grupo_vip_id = -1003875617504
```

## Configuración Firebase para Railway

Para desplegar en Railway, debes configurar la variable de entorno `FIREBASE_CREDENTIALS`:

1. Ve a tu proyecto en Railway
2. Abre la pestaña "Variables"
3. Agrega una nueva variable:
   - **Nombre**: `FIREBASE_CREDENTIALS`
   - **Valor**: El contenido completo del archivo `firebase_credentials.json` como una sola línea

Ejemplo:
```json
{"type":"service_account","project_id":"nequiaxonfree-7a6f7","private_key_id":"65ebf9cf...","private_key":"-----BEGIN PRIVATE KEY-----\nMIIEvAIBADANBgkqhkiG9w0BAQEFAASCBKYwggSiAgEAAoIBAQDS+ieEfCGawKJS\n...","client_email":"firebase-adminsdk-fbsvc@nequiaxonfree-7a6f7.iam.gserviceaccount.com",...}
```

## Comandos Principales

### Usuarios VIP
- `/crear` - Crear nueva cuenta
- `/eliminaruser numero` - Eliminar cuenta propia
- `/saldo numero` - Consultar saldo

### Administradores
- `/diagnostico` - Estado del sistema
- `/sincronizar` - Migrar usuarios existentes
- `/agregarvip id` - Agregar usuario VIP
- `/eliminarvip id` - Eliminar usuario VIP
- `/testfirebase` - Probar conexión Firebase

## Estructura Firebase

### Colección: `users`
```json
{
  "3001234567": {
    "name": "username",
    "pin": "1234",
    "saldo": "50000",
    "isActive": true,
    "created_by": 123456789,
    "created_at": "2024-01-01 12:00:00"
  }
}
```

### Colección: `usuarios_app`
```json
{
  "username": {
    "telegram_username": "username",
    "telegram_id": 123456789,
    "phone": "3001234567",
    "pin": "1234",
    "saldo": "50000",
    "isActive": true,
    "account_complete": true
  }
}
```

## API Endpoints

- `GET /` - Estado del bot
- `GET /health` - Estado de Firebase
- `POST /verify` - Verificar usuario para app
- `GET /get_user/<username>` - Obtener datos de usuario

## Deploy

```bash
git add .
git commit -m "Fix Firebase connection - Add FIREBASE_CREDENTIALS support"
git push origin main
```

El bot se reinicia automáticamente en el servidor.

## Troubleshooting

### Error de conexión Firebase
1. Verificar que `FIREBASE_CREDENTIALS` esté configurado en Railway
2. Usar `/testfirebase` para probar la conexión
3. Revisar logs del servidor para errores específicos
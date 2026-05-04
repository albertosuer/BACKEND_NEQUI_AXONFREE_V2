# NEQUIAXON BOT

Bot de Telegram para gestión de usuarios y cuentas Nequi.

## Configuración

1. **Variables de entorno** (`.env`):
```
TOKEN=tu_token_de_telegram
```

2. **Credenciales Firebase**: `firebase_credentials.json`

3. **Configurar IDs en `main.py`**:
```python
ADMIN_PRINCIPAL_1 = "8485352219"  # @AXONDEVUI - Admin Principal ÚNICO
REQUIRED_GROUP_ID = -1003707561305  # Nuevo grupo oficial
grupo_vip_id = -1003875617504
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
git commit -m "Update"
git push origin main
```

El bot se reinicia automáticamente en el servidor.
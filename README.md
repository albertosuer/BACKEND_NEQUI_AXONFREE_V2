# 🤖 Nequi Axon Labs Bot

Bot de Telegram para gestión de cuentas Nequi con sistema VIP, backup automático y control avanzado.

## ✨ Características Principales

### 🎯 Sistema de Usuarios
- **Usuarios Normales**: 3 usos diarios, requieren membresía al grupo
- **Usuarios VIP**: Acceso ilimitado, sin restricciones
- **Administradores**: Control total del sistema

### 🔐 Sistema de Control Dual
- `/off` - Desactiva solo para usuarios normales (VIPs siguen funcionando)
- `/mantenimiento` - Desactiva para TODOS (solo admins funcionan)

### 🌟 Funciones VIP
- Acceso ilimitado sin restricciones
- Pueden eliminar cuentas que ellos crearon
- Enlaces exclusivos al grupo VIP con regeneración automática
- Sin verificación de membresía

### 💾 Backup Automático
- Backup de usuarios VIP cada 5 minutos
- Restauración automática cada 5 minutos
- Sistema ligero con archivos JSON

### 🔗 Seguridad de Enlaces VIP
- Enlaces de un solo uso
- Regeneración automática al unirse
- Revocación inmediata después de uso
- Imposible compartir o rotar

## 📋 Comandos

### Para Usuarios Normales
```
/start - Iniciar el bot
/crear - Crear nueva cuenta
/saldo numero - Consultar saldo
/recargar numero cantidad - Recargar saldo
/help - Ver ayuda
```

### Para Usuarios VIP
```
/start - Iniciar el bot
/crear - Crear nueva cuenta (sin límites)
/saldo numero - Consultar saldo
/recargar numero cantidad - Recargar saldo
/eliminaruser numero - Eliminar cuenta propia
/help - Ver ayuda VIP
```

### Para Administradores
```
🤖 Control del Bot:
/off - Desactivar para usuarios normales
/activo - Activar para todos
/mantenimiento - Modo mantenimiento total
/mantenimientoapagado - Desactivar mantenimiento
/offgroup - Desactivar en grupos
/ongroup chatid - Activar en grupo específico

👥 Gestión de Usuarios:
/nuevo - Crear usuario directo
/usuarios - Listar usuarios
/eliminar numero - Eliminar usuario
/stats - Ver estadísticas

💰 Gestión de Saldo:
/agregarsaldo numero cantidad - Agregar saldo
/recargasgratis - Activar recargas automáticas
/offrecargas - Desactivar recargas automáticas

🌟 Gestión VIP:
/agregarvip telegram_id - Agregar usuario VIP
/eliminarvip telegram_id - Eliminar usuario VIP
/listavip - Ver lista de VIPs
/statusvip - Estado del backup VIP
/regenerarenlacevip telegram_id - Regenerar enlace
/configurargrupovip chatid - Configurar grupo VIP

📋 Gestión de Grupos:
/agregargrupo chatid - Agregar grupo permitido
/eliminargrupo chatid - Eliminar grupo

⚙️ Administración:
/agregaradmin telegram_id - Agregar administrador
/comandosadmin - Ver todos los comandos
```

## 🚀 Instalación

### Requisitos
- Python 3.10+
- Firebase Admin SDK
- Cuenta de Telegram Bot

### Dependencias
```bash
pip install -r requirements.txt
```

### Configuración

1. **Variables de Entorno** (`.env`):
```env
TOKEN=tu_token_de_telegram
TELEGRAM_BOT_TOKEN=tu_token_de_telegram
PORT=5000
```

2. **Firebase Credentials** (`firebase_credentials.json`):
```json
{
  "type": "service_account",
  "project_id": "tu-proyecto",
  ...
}
```

3. **Configurar IDs en `main.py`**:
```python
ADMIN_CHAT_ID = "tu_telegram_id"
REQUIRED_GROUP_ID = -1001234567890  # ID del grupo principal
grupo_vip_id = -1001234567890  # ID del grupo VIP
```

## 📊 Estructura del Proyecto

```
.
├── main.py                      # Código principal del bot
├── requirements.txt             # Dependencias
├── firebase_credentials.json    # Credenciales de Firebase
├── usuariosvip.json            # Backup de usuarios VIP
├── .env                        # Variables de entorno
├── Dockerfile                  # Para deployment
├── zeabur.json                 # Configuración Zeabur
└── README.md                   # Este archivo
```

## 🔧 Deployment

### Local
```bash
python main.py
```

### Docker
```bash
docker build -t nequi-bot .
docker run -p 5000:5000 nequi-bot
```

### Zeabur
1. Conectar repositorio de GitHub
2. Configurar variables de entorno
3. Deploy automático

## 📱 Flujo de Uso

### Usuario Normal
1. Unirse al grupo oficial
2. Iniciar el bot: `/start`
3. Crear cuenta: `/crear`
4. Ingresar arroba de Telegram
5. Completar datos: `/nequiaxonlabs numero pin saldo`

### Usuario VIP
1. Admin agrega como VIP: `/agregarvip telegram_id`
2. Usuario recibe enlace exclusivo
3. Usuario se une al grupo VIP
4. Enlace se revoca automáticamente
5. Acceso ilimitado al bot

## 🔒 Seguridad

- ✅ Verificación de membresía al grupo
- ✅ Sistema de límites diarios para usuarios normales
- ✅ Enlaces VIP de un solo uso
- ✅ Regeneración automática de enlaces
- ✅ Rastreo de quién creó cada cuenta
- ✅ VIPs solo eliminan sus propias cuentas
- ✅ Backup automático de datos VIP

## 📊 Base de Datos (Firebase)

### Colección: `users`
```json
{
  "3001234567": {
    "name": "username",
    "pin": "0515",
    "saldo": "500000",
    "isActive": true,
    "created_by": 123456789,
    "created_at": "2026-02-01 15:30:00"
  }
}
```

### Colección: `usuarios_app`
```json
{
  "username": {
    "telegram_username": "username",
    "telegram_id": 123456789,
    "created_at": "2026-02-01 15:30:00",
    "active": true
  }
}
```

## 🎨 Interfaz

- Botones interactivos para navegación
- Menús contextuales según nivel de usuario
- Mensajes con formato HTML
- Callbacks instantáneos

## 📞 Soporte

- Telegram: @AXONDEVUI
- Grupo: https://t.me/comunidadofficialchat

## 📄 Licencia

Este proyecto es privado y de uso exclusivo.

## 🔄 Versión

**v2.4** - Nequi Axon Labs - Comando actualizado a /nequiaxonlabs

---

**Desarrollado por:** Axon Dev
**Última actualización:** 2026-03-13

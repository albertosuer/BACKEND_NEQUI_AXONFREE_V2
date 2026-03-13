# 📝 CHANGELOG - Nequi Axon Labs Bot

## [2.4.0] - 2026-03-13

### 🔄 Cambiado
- **Comando Principal Renombrado**: `/nequiaxonfree` → `/nequiaxonlabs`
  - Refleja el nuevo nombre: Nequi Axon Labs
  - Comando actualizado en todo el código
  - Documentación completamente actualizada

- **Grupo Oficial Actualizado**: 
  - Nuevo grupo: https://t.me/comunidadofficialchat
  - Anterior: https://t.me/Nequiaxonfree
  - Enlaces actualizados en toda la documentación

### 📚 Documentación
- **NUEVO_COMANDO.md**: Guía completa del nuevo comando
  - Tutorial paso a paso
  - Ejemplos visuales
  - Errores comunes y soluciones
  - Preguntas frecuentes
  - Comparación con comando anterior

### 🎯 Migración
- Usuarios deben usar `/nequiaxonlabs` en lugar de `/nequiaxonfree`
- Todos los demás comandos permanecen igual
- Cuentas existentes no se ven afectadas

---

## [2.3.0] - 2026-02-01

### ✅ Arreglado
- **Comando `/eliminar` (Admin)**: Ahora acepta número de teléfono en lugar de username
  - Elimina correctamente de ambas colecciones (users y usuarios_app)
  - Muestra información completa del usuario eliminado
  - Manejo de errores mejorado

- **Comando `/crear` para VIPs**: Logs de debug agregados
  - Muestra exactamente qué verificaciones pasa el usuario
  - Identifica si es VIP, Admin o usuario normal
  - VIPs saltan todas las verificaciones innecesarias

### 🆕 Agregado
- **Comando `/eliminaruser` (VIP)**: Usuarios VIP pueden eliminar cuentas que ellos crearon
  - Sistema de rastreo con campo `created_by`
  - Verificación de propiedad antes de eliminar
  - Notificación al admin de cada eliminación
  - Admins pueden eliminar cualquier cuenta

- **Sistema de Control Dual**:
  - `/off`: Desactiva solo para usuarios normales (VIPs siguen funcionando)
  - `/mantenimiento`: Desactiva para TODOS (solo admins funcionan)
  - `/activo`: Reactiva el bot para todos
  - `/mantenimientoapagado`: Desactiva modo mantenimiento

- **Rastreo de Creadores**: Cada cuenta guarda quién la creó
  - Campo `created_by` en Firebase
  - Campo `created_at` con fecha de creación
  - Permite control de eliminación por usuario

### 🎨 Mejorado
- **Interfaz con Botones**: Menús interactivos para mejor UX
- **Mensajes Personalizados**: Diferentes mensajes según nivel de usuario
- **Logs Detallados**: Sistema de debug para troubleshooting
- **Ayuda Contextual**: Comandos diferentes para VIPs y usuarios normales

### 🔒 Seguridad
- **Enlaces VIP**: Regeneración automática al unirse al grupo
- **Sistema de Backup**: Automático cada 5 minutos para usuarios VIP
- **Verificación de Propiedad**: VIPs solo eliminan sus propias cuentas
- **Modo Mantenimiento**: Control total para actualizaciones críticas

### 📚 Documentación
- README.md completo con instrucciones
- CHANGELOG.md con historial de cambios
- Múltiples guías en formato Markdown
- Ejemplos de configuración

---

## [2.2.0] - 2026-01-31

### 🆕 Agregado
- Sistema de backup automático para usuarios VIP
- Regeneración automática de enlaces VIP
- Comando `/statusvip` para ver estado del backup
- Detección de nuevos miembros en grupo VIP

### 🎨 Mejorado
- Interfaz con botones interactivos
- Navegación fluida entre menús
- Mensajes con formato HTML mejorado

---

## [2.1.0] - 2026-01-30

### 🆕 Agregado
- Sistema de usuarios VIP
- Límites diarios para usuarios normales (3 usos/día)
- Verificación de membresía al grupo

### ✅ Arreglado
- Flujo de creación de cuentas simplificado
- Verificaciones optimizadas

---

## [2.0.0] - 2026-01-29

### 🆕 Agregado
- Bot inicial con funciones básicas
- Integración con Firebase
- Comandos de admin
- Sistema de recargas

---

**Formato del Changelog:**
- 🆕 Agregado: Nuevas funcionalidades
- ✅ Arreglado: Bugs corregidos
- 🎨 Mejorado: Mejoras en funcionalidades existentes
- 🔒 Seguridad: Mejoras de seguridad
- 📚 Documentación: Cambios en documentación
- ⚠️ Deprecado: Funcionalidades que se eliminarán
- 🗑️ Eliminado: Funcionalidades eliminadas

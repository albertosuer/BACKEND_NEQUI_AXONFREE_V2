# 🗑️ COMANDO /eliminaruser - USUARIOS VIP

## 🎯 Funcionalidad

Los usuarios VIP pueden eliminar cuentas que ELLOS MISMOS crearon, evitando errores o cuentas de prueba.

## 🔒 Sistema de Seguridad

### Protecciones Implementadas:

1. **Solo VIPs y Admins** pueden usar el comando
2. **VIPs solo eliminan sus propias creaciones**
3. **Admins pueden eliminar cualquier cuenta**
4. **Rastreo de creador** en cada cuenta

## 📊 Cómo Funciona

### Cuando se Crea una Cuenta:

```python
db.collection('users').document(phone).set({
    'name': username,
    'pin': pin,
    'saldo': saldo,
    'isActive': True,
    'created_by': user_id,  # ← ID de Telegram de quien lo creó
    'created_at': fecha
})
```

### Cuando se Elimina:

```python
1. Verificar que el usuario existe
2. Obtener el campo 'created_by'
3. Comparar con el ID del usuario que quiere eliminar
4. Si coincide → Permitir eliminación
5. Si no coincide → Denegar acceso
```

## 🎮 Uso del Comando

### Sintaxis:
```bash
/eliminaruser 3001234567
```

### Ejemplo Completo:

**Usuario VIP (ID: 123456) crea una cuenta:**
```
/crear
→ juanperez
→ /nequiaxonlabs 3001234567 0515 500000
✅ Cuenta creada (created_by: 123456)
```

**Usuario VIP quiere eliminarla:**
```
/eliminaruser 3001234567
✅ Usuario eliminado (porque created_by = 123456)
```

**Otro usuario VIP (ID: 789012) intenta eliminarla:**
```
/eliminaruser 3001234567
❌ ACCESO DENEGADO
Solo puedes eliminar cuentas que TÚ creaste.
Este usuario fue creado por: 123456
```

## 📋 Mensajes del Sistema

### Sin Argumentos:
```
📱 ELIMINAR USUARIO

Usa: /eliminaruser numero
Ejemplo: /eliminaruser 3001234567

⚠️ Solo puedes eliminar cuentas que TÚ creaste.
```

### Usuario No Encontrado:
```
❌ NÚMERO NO ENCONTRADO

El número 3001234567 no existe en la base de datos.
```

### Acceso Denegado (no es VIP):
```
❌ ACCESO DENEGADO

Este comando es solo para usuarios VIP.
Contacta: @AXONDEVUI
```

### Acceso Denegado (no es el creador):
```
❌ ACCESO DENEGADO

No puedes eliminar este usuario.
Solo puedes eliminar cuentas que TÚ creaste.

Este usuario fue creado por: 123456
```

### Eliminación Exitosa:
```
✅ USUARIO ELIMINADO

📱 Número: 3001234567
👤 Username: @juanperez

El usuario ha sido eliminado correctamente.
```

## 🔐 Niveles de Acceso

| Usuario | Puede Eliminar |
|---------|----------------|
| **Normal** | ❌ No tiene acceso |
| **VIP** | ✅ Solo sus propias cuentas |
| **Admin** | ✅ Cualquier cuenta |

## 📊 Casos de Uso

### Caso 1: Usuario VIP Crea por Error
```
1. VIP crea cuenta con número equivocado
2. VIP usa: /eliminaruser 3001234567
3. ✅ Cuenta eliminada
4. VIP crea la cuenta correcta
```

### Caso 2: Usuario VIP Hace Pruebas
```
1. VIP crea 3 cuentas de prueba
2. VIP elimina las 3:
   /eliminaruser 3001111111
   /eliminaruser 3002222222
   /eliminaruser 3003333333
3. ✅ Todas eliminadas
```

### Caso 3: VIP Intenta Eliminar Cuenta Ajena
```
1. VIP A crea: 3001234567
2. VIP B intenta: /eliminaruser 3001234567
3. ❌ Acceso denegado
4. Solo VIP A o Admin pueden eliminarla
```

### Caso 4: Admin Elimina Cualquiera
```
1. Admin usa: /eliminaruser 3001234567
2. ✅ Eliminada (sin importar quién la creó)
3. Admin tiene acceso total
```

## 🔄 Flujo Completo

```
Usuario VIP usa /eliminaruser 3001234567
    ↓
¿Es VIP o Admin?
    ↓ No
    ❌ Acceso denegado
    ↓ Sí
¿Existe el número?
    ↓ No
    ❌ Número no encontrado
    ↓ Sí
¿Es Admin?
    ↓ Sí
    ✅ Eliminar (sin más verificaciones)
    ↓ No (es VIP)
¿created_by == user_id?
    ↓ No
    ❌ No puedes eliminar cuentas ajenas
    ↓ Sí
    ✅ Eliminar cuenta
    ↓
Notificar al admin
    ↓
Confirmar al usuario
```

## 📞 Notificación al Admin

Cada vez que un VIP elimina una cuenta, el admin recibe:

```
🗑️ USUARIO ELIMINADO

👤 Eliminado por: 123456
📱 Número: 3001234567
👤 Username: @juanperez
🕐 Fecha: 2026-02-01 15:30:00
```

## 🎯 Beneficios

### Para Usuarios VIP:
- ✅ Autonomía para corregir errores
- ✅ No necesitan contactar al admin
- ✅ Gestión rápida de sus cuentas
- ✅ Seguridad (solo sus cuentas)

### Para el Admin:
- ✅ Menos solicitudes de eliminación
- ✅ Registro de todas las eliminaciones
- ✅ Control total (puede eliminar cualquiera)
- ✅ Sistema seguro y rastreable

## 🔧 Comandos Relacionados

```
/crear - Crear nueva cuenta
/eliminaruser - Eliminar cuenta propia (VIP)
/eliminar - Eliminar cualquier cuenta (Admin)
/usuarios - Ver todas las cuentas (Admin)
```

## ⚠️ Importante

1. **No hay confirmación**: La eliminación es inmediata
2. **No se puede deshacer**: Los datos se borran permanentemente
3. **Solo el creador**: VIPs solo eliminan lo que crearon
4. **Admin sin límites**: Admin puede eliminar cualquier cuenta

## 📱 En el Menú de Ayuda

**Para VIPs:**
```
📋 COMANDOS VIP 🌟

🆕 /crear - Crear nueva cuenta
💰 /saldo - Consultar saldo
💳 /recargar - Recargar saldo
🗑️ /eliminaruser - Eliminar cuenta que creaste
❌ /cancelar - Cancelar operación
```

---

**Sistema Activo:** ✅
**Versión:** 2.3
**Última actualización:** 2026-02-01

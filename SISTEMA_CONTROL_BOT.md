# 🎛️ SISTEMA DE CONTROL DEL BOT - NIVELES DE ACCESO

## 🎯 Sistema Implementado

El bot ahora tiene **DOS NIVELES** de control:

### 1️⃣ Nivel 1: `/off` - Solo Usuarios Normales
**Afecta a:** Usuarios normales únicamente
**NO afecta a:** Usuarios VIP y Admins

### 2️⃣ Nivel 2: `/mantenimiento` - TODOS
**Afecta a:** TODOS los usuarios (VIPs incluidos)
**NO afecta a:** Solo Admins

## 📊 Tabla de Acceso

| Estado | Usuarios Normales | Usuarios VIP | Admins |
|--------|------------------|--------------|---------|
| **Bot Normal** | ✅ Acceso | ✅ Acceso | ✅ Acceso |
| **Bot OFF** | ❌ Bloqueado | ✅ Acceso | ✅ Acceso |
| **Mantenimiento** | ❌ Bloqueado | ❌ Bloqueado | ✅ Acceso |

## 🎮 Comandos de Control

### `/off` - Desactivar para Usuarios Normales

```bash
/off
```

**Resultado:**
- ❌ Usuarios normales: Bloqueados
- ✅ Usuarios VIP: Siguen funcionando
- ✅ Admins: Siguen funcionando

**Mensaje para usuarios normales:**
```
⚠️ BOT DESACTIVADO

El bot está temporalmente desactivado para usuarios normales.

🌟 ¿Quieres acceso VIP ilimitado?
Contacta: 👤 @AXONDEVUI

Los usuarios VIP pueden seguir usando el bot sin restricciones.
```

---

### `/activo` - Activar para Todos

```bash
/activo
```

**Resultado:**
- ✅ Todos los usuarios pueden usar el bot
- Vuelve al funcionamiento normal

---

### `/mantenimiento` - Modo Mantenimiento Total

```bash
/mantenimiento
```

**Resultado:**
- ❌ Usuarios normales: Bloqueados
- ❌ Usuarios VIP: Bloqueados
- ✅ Solo admins: Funcionando

**Mensaje para TODOS:**
```
🔧 MODO MANTENIMIENTO

El bot está en mantenimiento.
Estamos realizando mejoras para ofrecerte un mejor servicio.

⏰ Vuelve pronto.
📞 Soporte: @AXONDEVUI
```

---

### `/mantenimientoapagado` - Desactivar Mantenimiento

```bash
/mantenimientoapagado
```

**Resultado:**
- ✅ Bot vuelve al estado anterior
- Todos los usuarios recuperan acceso según su nivel

## 🔄 Flujos de Uso

### Escenario 1: Limitar Acceso a Solo VIPs

```bash
Admin: /off
```

**Resultado:**
- Usuarios normales ven mensaje de contactar @AXONDEVUI
- Usuarios VIP siguen usando el bot normalmente
- Perfecto para promocionar membresías VIP

---

### Escenario 2: Mantenimiento Total

```bash
Admin: /mantenimiento
```

**Resultado:**
- TODOS los usuarios (incluidos VIPs) ven mensaje de mantenimiento
- Solo admins pueden usar el bot
- Perfecto para actualizaciones críticas

---

### Escenario 3: Reactivar Después de Mantenimiento

```bash
Admin: /mantenimientoapagado
```

**Resultado:**
- Bot vuelve a funcionar para todos
- VIPs y usuarios normales recuperan acceso

## 💡 Casos de Uso

### Caso 1: Promoción de VIP
**Objetivo:** Incentivar a usuarios a obtener VIP

```bash
1. Admin: /off
2. Usuarios normales contactan @AXONDEVUI
3. Admin agrega como VIP: /agregarvip ID
4. Usuario VIP puede usar el bot
5. Admin: /activo (cuando quiera reactivar para todos)
```

---

### Caso 2: Actualización del Bot
**Objetivo:** Realizar cambios sin interrupciones

```bash
1. Admin: /mantenimiento
2. Todos ven mensaje de mantenimiento
3. Admin realiza cambios
4. Admin: /mantenimientoapagado
5. Bot funciona normalmente
```

---

### Caso 3: Control de Carga
**Objetivo:** Reducir carga del servidor

```bash
1. Admin: /off
2. Solo VIPs usan el bot (menos carga)
3. Servidor se estabiliza
4. Admin: /activo
5. Todos vuelven a tener acceso
```

## 🎯 Verificaciones en el Código

### Orden de Verificación:

```python
1. ¿Es Admin?
   → Sí: Acceso total (ignora todo)
   → No: Continuar

2. ¿Modo Mantenimiento?
   → Sí: Bloquear (mensaje de mantenimiento)
   → No: Continuar

3. ¿Es VIP?
   → Sí: Acceso (ignora bot_active)
   → No: Continuar

4. ¿Bot OFF?
   → Sí: Bloquear (mensaje de contactar VIP)
   → No: Permitir acceso
```

## 📱 Mensajes para Usuarios

### Usuario Normal con Bot OFF:
```
⚠️ BOT DESACTIVADO

El bot está temporalmente desactivado para usuarios normales.

🌟 ¿Quieres acceso VIP ilimitado?
Contacta: 👤 @AXONDEVUI

Los usuarios VIP pueden seguir usando el bot sin restricciones.

[🌟 Obtener VIP] ← Botón
```

### Cualquier Usuario en Mantenimiento:
```
🔧 MODO MANTENIMIENTO

El bot está en mantenimiento.
Estamos realizando mejoras para ofrecerte un mejor servicio.

⏰ Vuelve pronto.
📞 Soporte: @AXONDEVUI

[📞 Contactar Soporte] ← Botón
```

## 🔧 Comandos Admin Actualizados

```
/comandosadmin
```

**Muestra:**
```
👑 COMANDOS DE ADMINISTRADOR

🤖 CONTROL DEL BOT
/off - Desactivar para usuarios normales (VIPs siguen)
/activo - Activar para todos
/mantenimiento - Desactivar para TODOS (incluye VIPs)
/mantenimientoapagado - Reactivar después de mantenimiento
...
```

## 📊 Estados del Bot

### Estado 1: Normal
```python
bot_active = True
mantenimiento_mode = False
```
- ✅ Todos tienen acceso

### Estado 2: OFF (Solo VIPs)
```python
bot_active = False
mantenimiento_mode = False
```
- ❌ Usuarios normales bloqueados
- ✅ VIPs y admins funcionando

### Estado 3: Mantenimiento
```python
bot_active = True/False  # No importa
mantenimiento_mode = True
```
- ❌ Todos bloqueados (excepto admins)

## 🎯 Beneficios del Sistema

### Para el Admin:
- ✅ Control granular del acceso
- ✅ Promoción de membresías VIP
- ✅ Mantenimiento sin afectar VIPs
- ✅ Reducción de carga cuando sea necesario

### Para Usuarios VIP:
- ✅ Acceso prioritario
- ✅ Funcionan incluso con bot OFF
- ✅ Valor agregado a la membresía

### Para Usuarios Normales:
- ✅ Incentivo claro para obtener VIP
- ✅ Mensajes claros de cómo obtener acceso

## 📞 Contacto para VIP

Todos los mensajes incluyen:
- **Telegram:** @AXONDEVUI
- **Botón directo** para contactar

---

**Sistema Activo:** ✅
**Versión:** 2.2
**Última actualización:** 2026-02-01

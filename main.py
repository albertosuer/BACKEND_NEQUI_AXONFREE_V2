from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
import os
from dotenv import load_dotenv
import threading
import json
import time
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes, ConversationHandler, CallbackQueryHandler

load_dotenv()

app = Flask(__name__)
CORS(app)

# Configuration
TELEGRAM_BOT_TOKEN = os.getenv('TOKEN') or os.getenv('TELEGRAM_BOT_TOKEN')
ADMIN_PRINCIPAL_1 = "8485045964"  # Admin Principal 1
ADMIN_PRINCIPAL_2 = "8485352219"  # Admin Principal 2
ADMINS_PRINCIPALES = {ADMIN_PRINCIPAL_1, ADMIN_PRINCIPAL_2}  # Admins que no se pueden eliminar
REQUIRED_GROUP_ID = -1003710645728
GROUP_LINK = "https://t.me/comunidadofficialchat"
NUMERO_RECARGA = "3210000000"  # Número donde los usuarios envían el pago

# Bot state
bot_active = True
mantenimiento_mode = False  # Modo mantenimiento para TODOS
group_active = True
recargas_gratis = True  # Si está True, las recargas son automáticas
admin_ids = set([ADMIN_PRINCIPAL_1, ADMIN_PRINCIPAL_2])  # Incluye ambos admins principales
admins_secundarios = set()  # Admins secundarios agregados dinámicamente
grupos_permitidos = set([REQUIRED_GROUP_ID])  # Grupos donde el bot puede funcionar
grupo_activo_id = REQUIRED_GROUP_ID  # Grupo actualmente activo
usuarios_vip = set()  # IDs de usuarios VIP
url_grupo_vip = "https://t.me/GrupoVIPPrivado"  # URL del grupo VIP
grupo_vip_id = -1003875617504  # ID del grupo VIP configurado
vip_backup_file = 'usuariosvip.json'
admins_backup_file = 'admins_secundarios.json'
last_vip_backup = None
last_vip_restore = None

# Control de uso diario (user_id: {'date': 'YYYY-MM-DD', 'count': 0})
uso_diario = {}
MAX_USO_DIARIO = 3

# Enlaces VIP de un solo uso (user_id: invite_link)
enlaces_vip_personales = {}

# Conversation states
USERNAME_STEP = 0
COMPLETE_ACCOUNT_STEP = 1
NUEVO_PHONE, NUEVO_PIN, NUEVO_SALDO = range(10, 13)
user_data = {}
admin_nuevo_data = {}

# Initialize Firebase
firebase_initialized = False
db = None

def init_firebase():
    global firebase_initialized, db
    if not firebase_initialized:
        try:
            cred = credentials.Certificate('firebase_credentials.json')
            firebase_admin.initialize_app(cred)
            db = firestore.client()
            firebase_initialized = True
            print("✅ Firebase initialized successfully")
        except Exception as e:
            print(f"❌ Firebase initialization error: {e}")

def load_vip_from_json():
    """Carga usuarios VIP desde el archivo JSON"""
    global usuarios_vip, last_vip_restore
    try:
        if os.path.exists(vip_backup_file):
            with open(vip_backup_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                usuarios_vip = set(data.get('usuarios_vip', []))
                last_vip_restore = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                print(f"✅ VIP usuarios cargados: {len(usuarios_vip)}")
        else:
            # Crear archivo si no existe
            save_vip_to_json()
            print("📁 Archivo VIP creado")
    except Exception as e:
        print(f"❌ Error cargando VIP: {e}")

def save_vip_to_json():
    """Guarda usuarios VIP en el archivo JSON (backup)"""
    global last_vip_backup
    try:
        data = {
            'usuarios_vip': list(usuarios_vip),
            'last_backup': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'last_restore': last_vip_restore,
            'total': len(usuarios_vip)
        }
        with open(vip_backup_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        last_vip_backup = data['last_backup']
        print(f"💾 Backup VIP guardado: {len(usuarios_vip)} usuarios")
    except Exception as e:
        print(f"❌ Error guardando VIP: {e}")

def auto_backup_vip():
    """Proceso automático de backup cada 5 minutos"""
    while True:
        try:
            time.sleep(300)  # 5 minutos
            if usuarios_vip:  # Solo hacer backup si hay usuarios
                save_vip_to_json()
        except Exception as e:
            print(f"❌ Error en auto-backup: {e}")

def auto_restore_vip():
    """Proceso automático de restauración cada 5 minutos"""
    while True:
        try:
            time.sleep(300)  # 5 minutos
            # Cargar desde JSON y sincronizar
            if os.path.exists(vip_backup_file):
                with open(vip_backup_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    vip_from_file = set(data.get('usuarios_vip', []))
                    # Solo restaurar si hay diferencias
                    if vip_from_file != usuarios_vip:
                        usuarios_vip.update(vip_from_file)
                        print(f"🔄 VIP auto-restaurados: {len(usuarios_vip)}")
        except Exception as e:
            print(f"❌ Error en auto-restore: {e}")

def send_telegram_message(message, chat_id=None):
    target_chat = chat_id or ADMIN_CHAT_ID
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {'chat_id': target_chat, 'text': message, 'parse_mode': 'HTML'}
    try:
        response = requests.post(url, json=payload)
        return response.status_code == 200
    except Exception as e:
        print(f"❌ Telegram error: {e}")
        return False

def is_admin(user_id):
    """Verifica si el usuario es admin (principal o secundario)"""
    return str(user_id) in admin_ids or str(user_id) in admins_secundarios

def is_admin_principal(user_id):
    """Verifica si el usuario es admin principal (no se puede eliminar)"""
    return str(user_id) in ADMINS_PRINCIPALES

def save_admins_to_json():
    """Guarda admins secundarios en archivo JSON"""
    try:
        data = {
            'admins_secundarios': list(admins_secundarios),
            'last_backup': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'total': len(admins_secundarios)
        }
        with open(admins_backup_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"💾 Backup admins guardado: {len(admins_secundarios)} admins secundarios")
    except Exception as e:
        print(f"❌ Error guardando admins: {e}")

def load_admins_from_json():
    """Carga admins secundarios desde archivo JSON"""
    global admins_secundarios
    try:
        if os.path.exists(admins_backup_file):
            with open(admins_backup_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                admins_secundarios = set(data.get('admins_secundarios', []))
                print(f"✅ Admins secundarios cargados: {len(admins_secundarios)}")
        else:
            save_admins_to_json()
            print("📁 Archivo admins creado")
    except Exception as e:
        print(f"❌ Error cargando admins: {e}")

def mensaje_bot_desactivado():
    """Mensaje cuando el bot está desactivado para usuarios normales"""
    return (
        "⚠️ <b>BOT DESACTIVADO</b>\n\n"
        "El bot está temporalmente desactivado para usuarios normales.\n\n"
        "🌟 <b>¿Quieres acceso VIP ilimitado?</b>\n"
        "Contacta: 👤 @AXONDEVUI\n\n"
        "Los usuarios VIP pueden seguir usando el bot sin restricciones."
    )

def mensaje_mantenimiento():
    """Mensaje cuando el bot está en mantenimiento total"""
    return (
        "🔧 <b>MODO MANTENIMIENTO</b>\n\n"
        "El bot está en mantenimiento.\n"
        "Estamos realizando mejoras para ofrecerte un mejor servicio.\n\n"
        "⏰ Vuelve pronto.\n"
        "📞 Soporte: @AXONDEVUI"
    )

def verificar_uso_diario(user_id):
    """Verifica si el usuario puede usar el bot hoy (máximo 3 veces)"""
    if user_id in usuarios_vip:
        return True, 0  # VIP tiene uso ilimitado
    
    hoy = datetime.now().strftime('%Y-%m-%d')
    
    if user_id not in uso_diario:
        uso_diario[user_id] = {'date': hoy, 'count': 0}
    
    # Si es un nuevo día, resetear contador
    if uso_diario[user_id]['date'] != hoy:
        uso_diario[user_id] = {'date': hoy, 'count': 0}
    
    usos_restantes = MAX_USO_DIARIO - uso_diario[user_id]['count']
    puede_usar = usos_restantes > 0
    
    return puede_usar, usos_restantes

def registrar_uso(user_id):
    """Registra un uso del bot"""
    if user_id in usuarios_vip:
        return  # VIP no tiene límite
    
    hoy = datetime.now().strftime('%Y-%m-%d')
    if user_id not in uso_diario or uso_diario[user_id]['date'] != hoy:
        uso_diario[user_id] = {'date': hoy, 'count': 1}
    else:
        uso_diario[user_id]['count'] += 1

async def crear_enlace_vip_personal(user_id, context):
    """Crea un enlace de invitación de un solo uso para el grupo VIP"""
    if grupo_vip_id is None:
        return None
    
    try:
        # Crear enlace de invitación que expira después de 1 uso
        invite_link = await context.bot.create_chat_invite_link(
            chat_id=grupo_vip_id,
            member_limit=1,  # Solo 1 persona puede usar este enlace
            name=f"VIP_{user_id}"
        )
        return invite_link.invite_link
    except Exception as e:
        print(f"Error creando enlace VIP: {e}")
        return None

async def notificar_activacion_vip(user_id, context):
    """Notifica al usuario que su cuenta VIP ha sido activada"""
    try:
        # Crear enlace personal de un solo uso
        enlace_personal = await crear_enlace_vip_personal(user_id, context)
        
        if enlace_personal:
            enlaces_vip_personales[user_id] = enlace_personal
            mensaje = (
                "🌟 <b>¡CUENTA VIP ACTIVADA!</b> 🌟\n\n"
                "✅ Tu cuenta VIP ha sido activada exitosamente.\n\n"
                "🎁 <b>BENEFICIOS VIP:</b>\n"
                "• Uso ilimitado del bot\n"
                "• Sin restricciones diarias\n"
                "• Acceso al grupo VIP exclusivo\n"
                "• Soporte prioritario\n\n"
                "🔐 <b>ENLACE EXCLUSIVO (UN SOLO USO):</b>\n"
                f"{enlace_personal}\n\n"
                "⚠️ Este enlace es personal y se desactivará automáticamente después de que te unas.\n\n"
                "¡Bienvenido al club VIP! 🎉"
            )
        else:
            mensaje = (
                "🌟 <b>¡CUENTA VIP ACTIVADA!</b> 🌟\n\n"
                "✅ Tu cuenta VIP ha sido activada exitosamente.\n\n"
                "🎁 <b>BENEFICIOS VIP:</b>\n"
                "• Uso ilimitado del bot\n"
                "• Sin restricciones diarias\n"
                "• Soporte prioritario\n\n"
                "¡Bienvenido al club VIP! 🎉"
            )
        
        await context.bot.send_message(chat_id=user_id, text=mensaje, parse_mode='HTML')
        return True
    except Exception as e:
        print(f"Error notificando VIP a {user_id}: {e}")
        return False

async def check_group_membership(user_id, context):
    """Verifica si el usuario está en el grupo activo configurado"""
    try:
        # Usar el grupo activo configurado
        member = await context.bot.get_chat_member(grupo_activo_id, user_id)
        is_member = member.status in ['member', 'administrator', 'creator', 'restricted']
        print(f"✅ Usuario {user_id} - Membresía: {is_member} - Status: {member.status}")
        return is_member
    except Exception as e:
        print(f"❌ Group check error for {user_id}: {e}")
        return False

async def is_group_admin(user_id, context):
    """Verifica si el usuario es admin del grupo activo"""
    try:
        member = await context.bot.get_chat_member(grupo_activo_id, user_id)
        return member.status in ['administrator', 'creator']
    except:
        return False

async def check_vip_group_membership(user_id, context):
    """Check if VIP user is member of VIP group"""
    if grupo_vip_id is None:
        return True  # Si no hay grupo VIP configurado, permitir acceso
    try:
        member = await context.bot.get_chat_member(grupo_vip_id, user_id)
        return member.status in ['member', 'administrator', 'creator', 'restricted']
    except Exception as e:
        print(f"VIP group check error for {user_id}: {e}")
        return False

# ============ TELEGRAM BOT HANDLERS ============

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /start simplificado - Muestra información básica del usuario"""
    user = update.effective_user
    user_id = user.id
    username = user.username or "Sin username"
    first_name = user.first_name or "Usuario"
    
    # Verificar si es admin o VIP
    is_bot_admin = is_admin(user_id)
    is_vip = user_id in usuarios_vip
    
    # Determinar tipo de usuario
    if is_bot_admin:
        tipo_usuario = "👑 ADMINISTRADOR"
    elif is_vip:
        tipo_usuario = "🌟 VIP"
    else:
        tipo_usuario = "👤 USUARIO NORMAL"
    
    # Botones básicos
    keyboard = [
        [InlineKeyboardButton("🆕 Crear Cuenta", callback_data='crear_cuenta')],
        [InlineKeyboardButton("💰 Consultar Saldo", callback_data='consultar_saldo')],
        [InlineKeyboardButton("💳 Recargar", callback_data='recargar_saldo')],
        [InlineKeyboardButton("❓ Ayuda", callback_data='ayuda')]
    ]
    
    # Agregar botones especiales según tipo de usuario
    if is_vip:
        keyboard.insert(3, [InlineKeyboardButton("🌟 Grupo VIP", url=url_grupo_vip)])
    elif is_bot_admin:
        keyboard.insert(3, [InlineKeyboardButton("👑 Panel Admin", callback_data='panel_admin')])
    else:
        keyboard.insert(3, [InlineKeyboardButton("🌟 Obtener VIP", url="https://t.me/AXONDEVUI")])
    
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Mensaje de bienvenida con información del usuario
    mensaje = (
        f"👋 <b>¡Bienvenido a Nequi Axon Labs!</b>\n\n"
        f"📋 <b>TU INFORMACIÓN:</b>\n"
        f"👤 Nombre: {first_name}\n"
        f"🆔 Username: @{username}\n"
        f"🔢 ID: <code>{user_id}</code>\n"
        f"⭐ Tipo: {tipo_usuario}\n\n"
    )
    
    # Agregar información adicional según tipo de usuario
    if is_bot_admin:
        mensaje += "✅ Tienes acceso completo al sistema.\n\n"
    elif is_vip:
        mensaje += "✅ Tienes acceso ilimitado sin restricciones.\n\n"
    else:
        puede_usar, usos_restantes = verificar_uso_diario(user_id)
        mensaje += f"📊 Usos restantes hoy: {usos_restantes}/{MAX_USO_DIARIO}\n\n"
    
    mensaje += "Selecciona una opción:"
    
    await update.message.reply_text(mensaje, parse_mode='HTML', reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if not bot_active and not is_admin(user_id):
        await update.message.reply_text(mensaje_bot_desactivado(), parse_mode='HTML')
        return
    
    is_vip = user_id in usuarios_vip
    
    # Si es admin, mostrar todos los comandos con botones
    if is_admin(user_id):
        keyboard = [
            [InlineKeyboardButton("👑 Panel Admin", callback_data='panel_admin')],
            [InlineKeyboardButton("📊 Estadísticas", callback_data='stats')],
            [InlineKeyboardButton("🔙 Menú Principal", callback_data='menu_principal')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "📋 <b>COMANDOS DISPONIBLES</b>\n\n"
            "👤 <b>Usuario:</b>\n"
            "/crear - Crear cuenta\n"
            "/saldo - Consultar saldo\n"
            "/recargar - Recargar saldo\n"
            "/eliminaruser - Eliminar cuenta propia\n\n"
            "👑 <b>Admin:</b>\n"
            "/nuevo - Crear usuario\n"
            "/agregarsaldo - Agregar saldo\n"
            "/comandosadmin - Ver todos los comandos\n"
            "/stats - Estadísticas",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    elif is_vip:
        keyboard = [
            [InlineKeyboardButton("🆕 Crear Cuenta", callback_data='crear_cuenta')],
            [InlineKeyboardButton("💰 Consultar Saldo", callback_data='consultar_saldo')],
            [InlineKeyboardButton("💳 Recargar", callback_data='recargar_saldo')],
            [InlineKeyboardButton("🔙 Menú Principal", callback_data='menu_principal')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "📋 <b>COMANDOS VIP</b> 🌟\n\n"
            "🆕 /crear - Crear nueva cuenta\n"
            "💰 /saldo - Consultar saldo\n"
            "💳 /recargar - Recargar saldo\n"
            "🗑️ /eliminaruser - Eliminar cuenta que creaste\n"
            "❌ /cancelar - Cancelar operación\n\n"
            "Usa los botones para acceso rápido:",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    else:
        keyboard = [
            [InlineKeyboardButton("🆕 Crear Cuenta", callback_data='crear_cuenta')],
            [InlineKeyboardButton("💰 Consultar Saldo", callback_data='consultar_saldo')],
            [InlineKeyboardButton("💳 Recargar", callback_data='recargar_saldo')],
            [InlineKeyboardButton("🔙 Menú Principal", callback_data='menu_principal')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "📋 <b>COMANDOS DISPONIBLES</b>\n\n"
            "🆕 /crear - Crear nueva cuenta\n"
            "💰 /saldo - Consultar saldo\n"
            "💳 /recargar - Recargar saldo\n"
            "❌ /cancelar - Cancelar operación\n\n"
            "Usa los botones para acceso rápido:",
            parse_mode='HTML',
            reply_markup=reply_markup
        )

# ============ CALLBACK HANDLERS (BOTONES) ============

async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja todos los callbacks de botones"""
    query = update.callback_query
    await query.answer()
    
    user_id = query.from_user.id
    data = query.data
    
    # Menú Principal
    if data == 'menu_principal':
        is_vip = user_id in usuarios_vip
        is_bot_admin = is_admin(user_id)
        
        if is_vip:
            keyboard = [
                [InlineKeyboardButton("🆕 Crear Cuenta", callback_data='crear_cuenta')],
                [InlineKeyboardButton("💰 Consultar Saldo", callback_data='consultar_saldo')],
                [InlineKeyboardButton("💳 Recargar", callback_data='recargar_saldo')],
                [InlineKeyboardButton("🌟 Grupo VIP", url=url_grupo_vip)],
                [InlineKeyboardButton("❓ Ayuda", callback_data='ayuda')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"👋 <b>¡Bienvenido Usuario VIP!</b> 🌟\n\n"
                f"Tienes acceso exclusivo ilimitado.\n\n"
                f"Selecciona una opción:",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
        elif is_bot_admin:
            keyboard = [
                [InlineKeyboardButton("🆕 Crear Cuenta", callback_data='crear_cuenta')],
                [InlineKeyboardButton("💰 Consultar Saldo", callback_data='consultar_saldo')],
                [InlineKeyboardButton("💳 Recargar", callback_data='recargar_saldo')],
                [InlineKeyboardButton("👑 Panel Admin", callback_data='panel_admin')],
                [InlineKeyboardButton("❓ Ayuda", callback_data='ayuda')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"👋 <b>¡Bienvenido Administrador!</b> 👑\n\n"
                f"Acceso completo al sistema.\n\n"
                f"Selecciona una opción:",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
        else:
            puede_usar, usos_restantes = verificar_uso_diario(user_id)
            keyboard = [
                [InlineKeyboardButton("🆕 Crear Cuenta", callback_data='crear_cuenta')],
                [InlineKeyboardButton("💰 Consultar Saldo", callback_data='consultar_saldo')],
                [InlineKeyboardButton("💳 Recargar", callback_data='recargar_saldo')],
                [InlineKeyboardButton("🌟 Obtener VIP", url="https://t.me/AXONDEVUI")],
                [InlineKeyboardButton("❓ Ayuda", callback_data='ayuda')]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.edit_message_text(
                f"👋 <b>¡Bienvenido a Nequi Axon Free!</b>\n\n"
                f"Gestiona tus cuentas de forma rápida y segura.\n\n"
                f"📊 <b>Usos restantes hoy:</b> {usos_restantes}/{MAX_USO_DIARIO}\n\n"
                f"Selecciona una opción:",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
    
    # Crear Cuenta
    elif data == 'crear_cuenta':
        keyboard = [[InlineKeyboardButton("🔙 Volver", callback_data='menu_principal')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "🆕 <b>CREAR CUENTA</b>\n\n"
            "Para crear tu cuenta usa el comando:\n"
            "<code>/crear</code>\n\n"
            "Te guiaré paso a paso.",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    
    # Consultar Saldo
    elif data == 'consultar_saldo':
        keyboard = [[InlineKeyboardButton("🔙 Volver", callback_data='menu_principal')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "💰 <b>CONSULTAR SALDO</b>\n\n"
            "Para consultar tu saldo usa:\n"
            "<code>/saldo numero</code>\n\n"
            "Ejemplo:\n"
            "<code>/saldo 3001234567</code>",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    
    # Recargar Saldo
    elif data == 'recargar_saldo':
        keyboard = [[InlineKeyboardButton("🔙 Volver", callback_data='menu_principal')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "💳 <b>RECARGAR SALDO</b>\n\n"
            "Para recargar saldo usa:\n"
            "<code>/recargar numero cantidad</code>\n\n"
            "Ejemplo:\n"
            "<code>/recargar 3001234567 50000</code>",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    
    # Ayuda
    elif data == 'ayuda':
        keyboard = [[InlineKeyboardButton("🔙 Volver", callback_data='menu_principal')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "❓ <b>AYUDA</b>\n\n"
            "📋 <b>Comandos disponibles:</b>\n\n"
            "🆕 /crear - Crear nueva cuenta\n"
            "💰 /saldo numero - Consultar saldo\n"
            "💳 /recargar numero cantidad - Recargar\n"
            "❌ /cancelar - Cancelar operación\n"
            "❓ /help - Ver ayuda\n\n"
            "💬 Soporte: @AXONDEVUI",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    
    # Panel Admin
    elif data == 'panel_admin':
        if not is_admin(user_id):
            await query.answer("❌ No tienes permisos de administrador", show_alert=True)
            return
        
        keyboard = [
            [InlineKeyboardButton("👥 Ver Usuarios", callback_data='admin_usuarios')],
            [InlineKeyboardButton("📊 Estadísticas", callback_data='stats')],
            [InlineKeyboardButton("🌟 Gestión VIP", callback_data='admin_vip')],
            [InlineKeyboardButton("🔙 Volver", callback_data='menu_principal')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "👑 <b>PANEL DE ADMINISTRACIÓN</b>\n\n"
            "Selecciona una opción:",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    
    # Stats
    elif data == 'stats':
        users_count = 0
        if db:
            users_count = len(list(db.collection('usuarios_app').stream()))
        
        keyboard = [[InlineKeyboardButton("🔙 Volver", callback_data='panel_admin' if is_admin(user_id) else 'menu_principal')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"📊 <b>ESTADÍSTICAS</b>\n\n"
            f"👥 Usuarios: {users_count}\n"
            f"🌟 VIP: {len(usuarios_vip)}\n"
            f"🤖 Bot: {'✅ Activo' if bot_active else '❌ Inactivo'}\n"
            f"👑 Admins: {len(admin_ids)}",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    
    # Admin VIP
    elif data == 'admin_vip':
        if not is_admin(user_id):
            await query.answer("❌ No tienes permisos", show_alert=True)
            return
        
        keyboard = [
            [InlineKeyboardButton("📋 Lista VIP", callback_data='lista_vip')],
            [InlineKeyboardButton("💾 Status Backup", callback_data='status_backup')],
            [InlineKeyboardButton("🔙 Volver", callback_data='panel_admin')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            "🌟 <b>GESTIÓN VIP</b>\n\n"
            "Comandos disponibles:\n"
            "/agregarvip ID - Agregar VIP\n"
            "/eliminarvip ID - Eliminar VIP\n"
            "/listavip - Ver lista completa\n"
            "/statusvip - Estado del backup",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    
    # Admin Usuarios
    elif data == 'admin_usuarios':
        if not is_admin(user_id):
            await query.answer("❌ No tienes permisos", show_alert=True)
            return
        
        users_count = 0
        users_list = []
        if db:
            users = list(db.collection('users').stream())
            users_count = len(users)
            for u in users[:5]:
                data_user = u.to_dict()
                users_list.append(f"• {u.id} - {data_user.get('name', 'N/A')} - ${int(data_user.get('saldo', 0)):,}")
        
        msg = f"👥 <b>USUARIOS REGISTRADOS</b>\n\n"
        msg += f"📊 Total: {users_count}\n\n"
        if users_list:
            msg += "<b>Últimos 5:</b>\n" + "\n".join(users_list)
            if users_count > 5:
                msg += f"\n\n... y {users_count - 5} más"
        else:
            msg += "No hay usuarios registrados."
        
        keyboard = [[InlineKeyboardButton("🔙 Volver", callback_data='panel_admin')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=reply_markup)
    
    # Lista VIP
    elif data == 'lista_vip':
        if not is_admin(user_id):
            await query.answer("❌ No tienes permisos", show_alert=True)
            return
        
        if not usuarios_vip:
            msg = "No hay usuarios VIP registrados."
        else:
            msg = f"🌟 <b>USUARIOS VIP</b>\n\n"
            msg += f"📊 Total: {len(usuarios_vip)}\n\n"
            for vip_id in list(usuarios_vip)[:10]:
                msg += f"• {vip_id}\n"
            if len(usuarios_vip) > 10:
                msg += f"\n... y {len(usuarios_vip) - 10} más"
        
        keyboard = [[InlineKeyboardButton("🔙 Volver", callback_data='admin_vip')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(msg, parse_mode='HTML', reply_markup=reply_markup)
    
    # Status Backup
    elif data == 'status_backup':
        if not is_admin(user_id):
            await query.answer("❌ No tienes permisos", show_alert=True)
            return
        
        file_size = 0
        if os.path.exists(vip_backup_file):
            file_size = os.path.getsize(vip_backup_file)
        
        keyboard = [[InlineKeyboardButton("🔙 Volver", callback_data='admin_vip')]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.edit_message_text(
            f"💾 <b>ESTADO BACKUP VIP</b>\n\n"
            f"👥 Usuarios VIP: <b>{len(usuarios_vip)}</b>\n"
            f"📁 Tamaño: {file_size} bytes\n"
            f"⏰ Último backup: {last_vip_backup or 'Pendiente'}\n"
            f"🔄 Última restauración: {last_vip_restore or 'Pendiente'}\n\n"
            f"⚙️ Auto-backup: ✅ Cada 5 min\n"
            f"⚙️ Auto-restore: ✅ Cada 5 min",
            parse_mode='HTML',
            reply_markup=reply_markup
        )

# ============ HANDLER DE NUEVOS MIEMBROS EN GRUPO VIP ============

async def handle_new_member(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Detecta cuando alguien se une al grupo VIP y regenera el enlace automáticamente"""
    try:
        chat_id = update.effective_chat.id
        
        # Solo procesar si es el grupo VIP configurado
        if chat_id != grupo_vip_id:
            return
        
        # Obtener los nuevos miembros
        new_members = update.message.new_chat_members
        
        for member in new_members:
            user_id = member.id
            username = member.username or member.first_name
            
            # Si el nuevo miembro es un usuario VIP con enlace personal
            if user_id in usuarios_vip and user_id in enlaces_vip_personales:
                # Revocar el enlace usado
                enlace_usado = enlaces_vip_personales[user_id]
                
                try:
                    # Intentar revocar el enlace en Telegram
                    await context.bot.revoke_chat_invite_link(chat_id, enlace_usado)
                    print(f"🔒 Enlace revocado para usuario {user_id}")
                except Exception as e:
                    print(f"⚠️ No se pudo revocar enlace: {e}")
                
                # Eliminar el enlace del diccionario
                del enlaces_vip_personales[user_id]
                
                # Generar nuevo enlace para el próximo VIP
                try:
                    # Crear enlace de un solo uso
                    new_invite = await context.bot.create_chat_invite_link(
                        chat_id=chat_id,
                        member_limit=1,  # Solo 1 persona puede usar este enlace
                        name=f"VIP-{user_id}-NEW"
                    )
                    
                    # Notificar al admin
                    admin_msg = (
                        f"🔄 <b>ENLACE VIP REGENERADO</b>\n\n"
                        f"👤 Usuario unido: {username} ({user_id})\n"
                        f"🔒 Enlace anterior revocado\n"
                        f"✅ Nuevo enlace generado automáticamente\n\n"
                        f"🔗 Nuevo enlace disponible para el próximo VIP:\n"
                        f"<code>{new_invite.invite_link}</code>"
                    )
                    send_telegram_message(admin_msg, ADMIN_CHAT_ID)
                    
                    print(f"✅ Nuevo enlace VIP generado después de que {user_id} se unió")
                    
                except Exception as e:
                    error_msg = (
                        f"❌ <b>ERROR AL REGENERAR ENLACE</b>\n\n"
                        f"Usuario {user_id} se unió pero no se pudo generar nuevo enlace.\n"
                        f"Error: {str(e)}"
                    )
                    send_telegram_message(error_msg, ADMIN_CHAT_ID)
                    print(f"❌ Error generando nuevo enlace: {e}")
                
                # Mensaje de bienvenida al nuevo miembro VIP
                welcome_msg = (
                    f"🌟 <b>¡Bienvenido al Grupo VIP, {username}!</b>\n\n"
                    f"Tienes acceso exclusivo a todas las funciones premium.\n\n"
                    f"🔒 Tu enlace de invitación ha sido revocado automáticamente por seguridad.\n\n"
                    f"Usa el bot: @{context.bot.username}"
                )
                try:
                    await context.bot.send_message(chat_id, welcome_msg, parse_mode='HTML')
                except:
                    pass
    
    except Exception as e:
        print(f"❌ Error en handle_new_member: {e}")

# ============ /crear - FLUJO SIMPLIFICADO (2 MENSAJES) ============

async def crear_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type
    chat_id = update.effective_chat.id
    
    print(f"🔍 CREAR_START - Usuario: {user_id}, Chat: {chat_id}, Tipo: {chat_type}")
    
    # VERIFICACIÓN 1: Modo Mantenimiento (afecta a TODOS excepto admins)
    if mantenimiento_mode and not is_admin(user_id):
        print(f"❌ Usuario {user_id} bloqueado por mantenimiento")
        keyboard = [[InlineKeyboardButton("📞 Contactar Soporte", url="https://t.me/AXONDEVUI")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(mensaje_mantenimiento(), parse_mode='HTML', reply_markup=reply_markup)
        return ConversationHandler.END
    
    is_bot_admin = is_admin(user_id)
    is_vip = user_id in usuarios_vip
    
    print(f"✅ Usuario {user_id} - Admin: {is_bot_admin}, VIP: {is_vip}")
    
    # Si es grupo, verificar que sea el grupo permitido (excepto admins y VIPs)
    if chat_type in ['group', 'supergroup']:
        if not is_bot_admin and not is_vip:
            if chat_id not in grupos_permitidos:
                print(f"❌ Usuario {user_id} - Grupo no permitido: {chat_id}")
                return ConversationHandler.END
            if not group_active:
                print(f"❌ Usuario {user_id} - Grupos desactivados")
                return ConversationHandler.END
    
    # VERIFICACIÓN 2: Bot OFF (solo afecta a usuarios normales, VIPs siguen funcionando)
    if not bot_active and not is_bot_admin and not is_vip:
        print(f"❌ Usuario {user_id} - Bot OFF")
        keyboard = [[InlineKeyboardButton("🌟 Obtener VIP", url="https://t.me/AXONDEVUI")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(mensaje_bot_desactivado(), parse_mode='HTML', reply_markup=reply_markup)
        return ConversationHandler.END
    
    # Usuarios VIP y admins tienen acceso ilimitado - SALTAR VERIFICACIONES
    if not is_bot_admin and not is_vip:
        print(f"🔍 Usuario {user_id} - Verificando límites (usuario normal)")
        # Verificar uso diario solo para usuarios normales
        puede_usar, usos_restantes = verificar_uso_diario(user_id)
        if not puede_usar:
            print(f"❌ Usuario {user_id} - Límite diario alcanzado")
            keyboard = [[InlineKeyboardButton("🌟 Obtener VIP", url="https://t.me/AXONDEVUI")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "⚠️ <b>LÍMITE DIARIO ALCANZADO</b>\n\n"
                f"Has usado el bot {MAX_USO_DIARIO} veces hoy.\n"
                "Vuelve mañana o contacta para acceso VIP ilimitado:",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            return ConversationHandler.END
        
        # Verificar membresía del grupo solo para usuarios normales (no VIP)
        is_member = await check_group_membership(user_id, context)
        if not is_member:
            print(f"❌ Usuario {user_id} - No está en el grupo")
            keyboard = [[InlineKeyboardButton("🔗 Unirse al Grupo", url=GROUP_LINK)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"❌ <b>ACCESO DENEGADO</b>\n\n"
                f"Debes unirte al grupo oficial para usar el bot.\n\n"
                f"Una vez te unas, vuelve y usa /crear",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            return ConversationHandler.END
        
        # Registrar uso para usuarios normales
        registrar_uso(user_id)
        print(f"✅ Usuario {user_id} - Uso registrado")
    else:
        print(f"✅ Usuario {user_id} - VIP/Admin - Sin verificaciones")
    
    # Iniciar el proceso de creación
    user_data[user_id] = {'telegram_id': user_id}
    print(f"✅ Usuario {user_id} - Iniciando proceso de creación")
    
    keyboard = [[InlineKeyboardButton("❌ Cancelar", callback_data='cancelar_crear')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "👤 <b>PASO 1 - ARROBA DE TELEGRAM</b>\n\n"
        "Ingresa tu @ de Telegram (sin el @):\n"
        "Ejemplo: juanperez",
        parse_mode='HTML',
        reply_markup=reply_markup
    )
    print(f"✅ Usuario {user_id} - Mensaje enviado")
    return USERNAME_STEP

async def get_username_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    username = update.message.text.strip().replace('@', '').lower()
    
    print(f"📝 get_username_step - Usuario: {user_id}, Username: {username}")
    
    if len(username) < 3:
        await update.message.reply_text("❌ Username muy corto. Mínimo 3 caracteres.\nIntenta de nuevo:")
        return USERNAME_STEP
    
    if db:
        # Verificar si ya existe en usuarios_app
        existing = db.collection('usuarios_app').document(username).get()
        if existing.exists:
            await update.message.reply_text("❌ Este username ya está registrado. Usa otro:")
            return USERNAME_STEP
        
        # Guardar solo el arroba en usuarios_app
        db.collection('usuarios_app').document(username).set({
            'telegram_username': username,
            'telegram_id': user_id,
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'active': True
        })
    
    # Guardar en user_data
    user_data[user_id]['telegram_username'] = username
    
    print(f"✅ Username guardado - user_data[{user_id}]: {user_data[user_id]}")
    
    await update.message.reply_text(
        f"✅ Arroba: <b>@{username}</b>\n\n"
        f"📋 <b>PASO 2 - COMPLETA TU CUENTA</b>\n\n"
        f"Envía el comando así:\n"
        f"<code>/nequiaxonlabs numero pin saldo</code>\n\n"
        f"📌 <b>Ejemplo:</b>\n"
        f"<code>/nequiaxonlabs 3001234567 0515 500000</code>\n\n"
        f"⚠️ Número: 10 dígitos | PIN: 4 dígitos",
        parse_mode='HTML'
    )
    
    # NO terminar el handler, esperar el comando /nequiaxonlabs
    return COMPLETE_ACCOUNT_STEP

async def complete_account_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Maneja el comando /nequiaxonlabs dentro del ConversationHandler"""
    user_id = update.effective_user.id
    
    print(f"🔍 complete_account_step - Usuario: {user_id}")
    print(f"🔍 user_data: {user_data.get(user_id, 'NO EXISTE')}")
    
    # Verificar que sea el comando correcto
    if not update.message.text.startswith('/nequiaxonlabs'):
        await update.message.reply_text(
            "❌ <b>COMANDO INCORRECTO</b>\n\n"
            "Debes usar el comando:\n"
            "<code>/nequiaxonlabs numero pin saldo</code>\n\n"
            "📌 Ejemplo:\n"
            "<code>/nequiaxonlabs 3001234567 0515 500000</code>",
            parse_mode='HTML'
        )
        return COMPLETE_ACCOUNT_STEP
    
    # Extraer argumentos del comando
    parts = update.message.text.split()
    
    if len(parts) != 4:  # /nequiaxonlabs + 3 argumentos
        await update.message.reply_text(
            "❌ <b>FORMATO INCORRECTO</b>\n\n"
            "Usa: <code>/nequiaxonlabs numero pin saldo</code>\n\n"
            "📌 Ejemplo:\n"
            "<code>/nequiaxonlabs 3001234567 0515 500000</code>\n\n"
            "⚠️ Número: 10 dígitos | PIN: 4 dígitos | Saldo: solo números",
            parse_mode='HTML'
        )
        return COMPLETE_ACCOUNT_STEP
    
    phone = parts[1].strip()
    pin = parts[2].strip()
    saldo_text = parts[3].strip().replace('.', '').replace(',', '')
    
    print(f"📱 Usuario {user_id} - Phone: {phone}, PIN: {pin}, Saldo: {saldo_text}")
    
    if not phone.isdigit() or len(phone) != 10:
        await update.message.reply_text("❌ Número inválido. Debe tener 10 dígitos.")
        return COMPLETE_ACCOUNT_STEP
    
    if not pin.isdigit() or len(pin) != 4:
        await update.message.reply_text("❌ PIN inválido. Debe tener 4 dígitos.")
        return COMPLETE_ACCOUNT_STEP
    
    if not saldo_text.isdigit():
        await update.message.reply_text("❌ Saldo inválido. Solo números.")
        return COMPLETE_ACCOUNT_STEP
    
    username = user_data[user_id]['telegram_username']
    saldo = int(saldo_text)
    created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    print(f"✅ Usuario {user_id} - Guardando cuenta: {username}, {phone}")
    
    if db:
        try:
            # Guardar en la colección 'users' con el NÚMERO como ID
            db.collection('users').document(phone).set({
                'name': username,
                'pin': str(pin),
                'saldo': str(saldo),
                'isActive': True,
                'created_by': user_id,
                'created_at': created_at
            })
            print(f"✅ Usuario {user_id} - Cuenta guardada en Firebase")
        except Exception as e:
            print(f"❌ Firebase error: {e}")
            await update.message.reply_text("❌ Error al guardar. Intenta de nuevo.")
            return COMPLETE_ACCOUNT_STEP
    
    admin_message = f"""
🆕 <b>NUEVA CUENTA CREADA</b>

👤 <b>Username:</b> @{username}
📱 <b>Teléfono:</b> {phone}
🔐 <b>PIN:</b> {pin}
💰 <b>Saldo:</b> ${saldo:,}
🆔 <b>Telegram ID:</b> {user_id}
🕐 <b>Fecha:</b> {created_at}
"""
    send_telegram_message(admin_message, ADMIN_PRINCIPAL_1)
    
    await update.message.reply_text(
        f"✅ <b>¡CUENTA CREADA EXITOSAMENTE!</b>\n\n"
        f"👤 Username: <b>@{username}</b>\n"
        f"📱 Teléfono: <code>{phone}</code>\n"
        f"🔐 PIN: <code>{pin}</code>\n"
        f"💰 Saldo: ${saldo:,}\n\n"
        f"🎉 Tu cuenta está lista para usar.\n"
        f"Ingresa a la app con tu username: <code>{username}</code>",
        parse_mode='HTML'
    )
    
    print(f"✅ Usuario {user_id} - Proceso completado")
    
    # Limpiar user_data
    if user_id in user_data:
        del user_data[user_id]
    
    return ConversationHandler.END

async def cmd_nequiaxonlabs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    print(f"🔍 NEQUIAXONLABS - Usuario: {user_id}")
    print(f"🔍 user_data: {user_data.get(user_id, 'NO EXISTE')}")
    
    if user_id not in user_data or 'telegram_username' not in user_data.get(user_id, {}):
        print(f"❌ Usuario {user_id} - No tiene telegram_username en user_data")
        await update.message.reply_text(
            "❌ <b>ERROR</b>\n\n"
            "Primero usa /crear para registrar tu arroba.\n\n"
            "Luego podrás completar tu cuenta con /nequiaxonlabs",
            parse_mode='HTML'
        )
        return
    
    if not context.args or len(context.args) != 3:
        print(f"❌ Usuario {user_id} - Formato incorrecto: {context.args}")
        await update.message.reply_text(
            "❌ <b>FORMATO INCORRECTO</b>\n\n"
            "Usa: <code>/nequiaxonlabs numero pin saldo</code>\n\n"
            "📌 Ejemplo:\n"
            "<code>/nequiaxonlabs 3001234567 0515 500000</code>\n\n"
            "⚠️ Número: 10 dígitos | PIN: 4 dígitos | Saldo: solo números",
            parse_mode='HTML'
        )
        return
    
    phone = context.args[0].strip()
    pin = context.args[1].strip()
    saldo_text = context.args[2].strip().replace('.', '').replace(',', '')
    
    print(f"📱 Usuario {user_id} - Phone: {phone}, PIN: {pin}, Saldo: {saldo_text}")
    
    if not phone.isdigit() or len(phone) != 10:
        await update.message.reply_text("❌ Número inválido. Debe tener 10 dígitos.")
        return
    
    if not pin.isdigit() or len(pin) != 4:
        await update.message.reply_text("❌ PIN inválido. Debe tener 4 dígitos.")
        return
    
    if not saldo_text.isdigit():
        await update.message.reply_text("❌ Saldo inválido. Solo números.")
        return
    
    username = user_data[user_id]['telegram_username']
    saldo = int(saldo_text)
    created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    print(f"✅ Usuario {user_id} - Guardando cuenta: {username}, {phone}")
    
    if db:
        try:
            # Guardar en la colección 'users' con el NÚMERO como ID
            db.collection('users').document(phone).set({
                'name': username,
                'pin': str(pin),
                'saldo': str(saldo),
                'isActive': True,
                'created_by': user_id,  # ID de Telegram de quien lo creó
                'created_at': created_at
            })
            print(f"✅ Usuario {user_id} - Cuenta guardada en Firebase")
        except Exception as e:
            print(f"❌ Firebase error: {e}")
            await update.message.reply_text("❌ Error al guardar. Intenta de nuevo.")
            return
    
    admin_message = f"""
🆕 <b>NUEVA CUENTA CREADA</b>

👤 <b>Username:</b> @{username}
📱 <b>Teléfono:</b> {phone}
🔐 <b>PIN:</b> {pin}
💰 <b>Saldo:</b> ${saldo:,}
🆔 <b>Telegram ID:</b> {user_id}
🕐 <b>Fecha:</b> {created_at}
"""
    send_telegram_message(admin_message, ADMIN_CHAT_ID)
    
    await update.message.reply_text(
        f"✅ <b>¡CUENTA CREADA EXITOSAMENTE!</b>\n\n"
        f"👤 Username: <b>@{username}</b>\n"
        f"📱 Teléfono: <code>{phone}</code>\n"
        f"🔐 PIN: <code>{pin}</code>\n"
        f"💰 Saldo: ${saldo:,}\n\n"
        f"🎉 Tu cuenta está lista para usar.\n"
        f"Ingresa a la app con tu username: <code>{username}</code>",
        parse_mode='HTML'
    )
    
    print(f"✅ Usuario {user_id} - Proceso completado")
    
    # Limpiar user_data
    if user_id in user_data:
        del user_data[user_id]

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in user_data:
        del user_data[user_id]
    await update.message.reply_text("❌ Proceso cancelado.")
    return ConversationHandler.END

# ============ ADMIN COMMANDS ============

async def cmd_off(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Desactiva el bot solo para usuarios normales, VIPs siguen funcionando"""
    global bot_active
    user_id = update.effective_user.id
    
    # Solo admins principales
    if not is_admin_principal(user_id):
        await update.message.reply_text(
            "❌ <b>ACCESO DENEGADO</b>\n\nSolo admins principales pueden controlar el bot.",
            parse_mode='HTML'
        )
        return
    bot_active = False
    await update.message.reply_text(
        "🔴 <b>BOT DESACTIVADO</b>\n\n"
        "✅ Usuarios VIP: Siguen funcionando\n"
        "❌ Usuarios normales: Desactivados\n\n"
        "Los usuarios normales deben contactar @AXONDEVUI para obtener VIP.",
        parse_mode='HTML'
    )

async def cmd_activo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Activa el bot para todos"""
    global bot_active
    user_id = update.effective_user.id
    
    # Solo admins principales
    if not is_admin_principal(user_id):
        await update.message.reply_text(
            "❌ <b>ACCESO DENEGADO</b>\n\nSolo admins principales pueden controlar el bot.",
            parse_mode='HTML'
        )
        return
    bot_active = True
    await update.message.reply_text(
        "🟢 <b>BOT ACTIVADO</b>\n\n"
        "✅ Todos los usuarios pueden usar el bot.",
        parse_mode='HTML'
    )

async def cmd_mantenimiento(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Activa modo mantenimiento para TODOS (VIPs y normales)"""
    global mantenimiento_mode
    user_id = update.effective_user.id
    
    # Solo admins principales
    if not is_admin_principal(user_id):
        await update.message.reply_text(
            "❌ <b>ACCESO DENEGADO</b>\n\nSolo admins principales pueden activar mantenimiento.",
            parse_mode='HTML'
        )
        return
    mantenimiento_mode = True
    await update.message.reply_text(
        "🔧 <b>MODO MANTENIMIENTO ACTIVADO</b>\n\n"
        "❌ Bot desactivado para TODOS los usuarios\n"
        "❌ Incluye usuarios VIP\n"
        "✅ Solo admins pueden usar el bot\n\n"
        "Usa /mantenimientoapagado para reactivar.",
        parse_mode='HTML'
    )

async def cmd_mantenimientoapagado(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Desactiva modo mantenimiento"""
    global mantenimiento_mode
    user_id = update.effective_user.id
    
    # Solo admins principales
    if not is_admin_principal(user_id):
        await update.message.reply_text(
            "❌ <b>ACCESO DENEGADO</b>\n\nSolo admins principales pueden desactivar mantenimiento.",
            parse_mode='HTML'
        )
        return
    mantenimiento_mode = False
    await update.message.reply_text(
        "✅ <b>MODO MANTENIMIENTO DESACTIVADO</b>\n\n"
        "🟢 Bot funcionando normalmente\n"
        "✅ Todos los usuarios pueden usar el bot según su nivel de acceso.",
        parse_mode='HTML'
    )

async def cmd_offgroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global group_active
    user_id = update.effective_user.id
    
    # Solo admins principales
    if not is_admin_principal(user_id):
        await update.message.reply_text(
            "❌ <b>ACCESO DENEGADO</b>\n\nSolo admins principales pueden gestionar grupos.",
            parse_mode='HTML'
        )
        return
    
    group_active = False
    await update.message.reply_text("🔴 Bot DESACTIVADO en grupos.")

async def cmd_ongroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin activa bot solo en un grupo específico"""
    global grupo_activo_id, group_active
    user_id = update.effective_user.id
    
    # Solo admins principales
    if not is_admin_principal(user_id):
        await update.message.reply_text(
            "❌ <b>ACCESO DENEGADO</b>\n\nSolo admins principales pueden gestionar grupos.",
            parse_mode='HTML'
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            "� Uso: <code>/ongroup chatid</code>\n"
            "Ejemplo: <code>/ongroup -1001234567890</code>\n\n"
            "Esto activará el bot SOLO en ese grupo específico.",
            parse_mode='HTML'
        )
        return
    
    try:
        chat_id = int(context.args[0])
        grupo_activo_id = chat_id
        group_active = True
        grupos_permitidos.clear()  # Limpiar grupos anteriores
        grupos_permitidos.add(chat_id)
        await update.message.reply_text(
            f"✅ <b>Bot activado SOLO en el grupo:</b>\n"
            f"<code>{chat_id}</code>\n\n"
            f"⚠️ El bot NO funcionará en ningún otro grupo.",
            parse_mode='HTML'
        )
    except:
        await update.message.reply_text("❌ Chat ID inválido.")

async def cmd_agregaradmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Solo admins principales pueden agregar admins secundarios"""
    user_id = update.effective_user.id
    
    # Solo admins principales pueden agregar otros admins
    if not is_admin_principal(user_id):
        await update.message.reply_text(
            "❌ <b>ACCESO DENEGADO</b>\n\n"
            "Solo los administradores principales pueden agregar otros administradores.",
            parse_mode='HTML'
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            "📌 <b>AGREGAR ADMINISTRADOR SECUNDARIO</b>\n\n"
            "Uso: <code>/agregaradmin telegram_id</code>\n"
            "Ejemplo: <code>/agregaradmin 123456789</code>\n\n"
            "⚠️ Los admins secundarios pueden:\n"
            "• Agregar usuarios VIP (con notificación a admins principales)\n"
            "• Usar comandos de administración\n"
            "• NO pueden agregar/eliminar otros admins",
            parse_mode='HTML'
        )
        return
    
    try:
        new_admin_id = str(context.args[0])
        
        # Verificar que no sea ya admin principal
        if new_admin_id in ADMINS_PRINCIPALES:
            await update.message.reply_text(
                "⚠️ Este usuario ya es administrador principal.",
                parse_mode='HTML'
            )
            return
        
        # Verificar que no esté ya agregado
        if new_admin_id in admins_secundarios:
            await update.message.reply_text(
                "⚠️ Este usuario ya es administrador secundario.",
                parse_mode='HTML'
            )
            return
        
        # Agregar admin secundario
        admins_secundarios.add(new_admin_id)
        save_admins_to_json()
        
        # Notificar al nuevo admin
        try:
            await context.bot.send_message(
                chat_id=new_admin_id,
                text=(
                    "🎉 <b>¡FELICIDADES!</b>\n\n"
                    "Has sido promovido a <b>Administrador Secundario</b> del bot.\n\n"
                    "✅ <b>Permisos:</b>\n"
                    "• Agregar usuarios VIP\n"
                    "• Usar comandos de administración\n"
                    "• Gestionar usuarios\n\n"
                    "⚠️ <b>Importante:</b>\n"
                    "Cuando agregues un VIP, los admins principales serán notificados.\n\n"
                    "Usa /comandosadmin para ver todos los comandos."
                ),
                parse_mode='HTML'
            )
            notificado = True
        except:
            notificado = False
        
        # Notificar a todos los admins principales
        for admin_principal in ADMINS_PRINCIPALES:
            if str(admin_principal) != str(user_id):  # No notificar al que lo agregó
                try:
                    await context.bot.send_message(
                        chat_id=admin_principal,
                        text=(
                            f"👑 <b>NUEVO ADMIN SECUNDARIO</b>\n\n"
                            f"👤 Admin que agregó: <code>{user_id}</code>\n"
                            f"🆕 Nuevo admin: <code>{new_admin_id}</code>\n"
                            f"🕐 Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        ),
                        parse_mode='HTML'
                    )
                except:
                    pass
        
        msg = (
            f"✅ <b>ADMIN SECUNDARIO AGREGADO</b>\n\n"
            f"🆔 ID: <code>{new_admin_id}</code>\n"
            f"💾 Backup guardado\n"
        )
        if notificado:
            msg += f"✉️ Usuario notificado"
        else:
            msg += f"⚠️ No se pudo notificar (debe iniciar el bot)"
        
        await update.message.reply_text(msg, parse_mode='HTML')
        
    except ValueError:
        await update.message.reply_text("❌ ID inválido. Debe ser un número.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def cmd_eliminaradmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Solo admins principales pueden eliminar admins secundarios"""
    user_id = update.effective_user.id
    
    # Solo admins principales pueden eliminar otros admins
    if not is_admin_principal(user_id):
        await update.message.reply_text(
            "❌ <b>ACCESO DENEGADO</b>\n\n"
            "Solo los administradores principales pueden eliminar administradores.",
            parse_mode='HTML'
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            "📌 <b>ELIMINAR ADMINISTRADOR SECUNDARIO</b>\n\n"
            "Uso: <code>/eliminaradmin telegram_id</code>\n"
            "Ejemplo: <code>/eliminaradmin 123456789</code>\n\n"
            "⚠️ Solo se pueden eliminar admins secundarios.\n"
            "Los admins principales no se pueden eliminar.",
            parse_mode='HTML'
        )
        return
    
    try:
        admin_id = str(context.args[0])
        
        # Verificar que no sea admin principal
        if admin_id in ADMINS_PRINCIPALES:
            await update.message.reply_text(
                "❌ <b>NO SE PUEDE ELIMINAR</b>\n\n"
                "Los administradores principales no se pueden eliminar.",
                parse_mode='HTML'
            )
            return
        
        # Verificar que exista como admin secundario
        if admin_id not in admins_secundarios:
            await update.message.reply_text(
                "❌ Este usuario no es administrador secundario.",
                parse_mode='HTML'
            )
            return
        
        # Eliminar admin secundario
        admins_secundarios.remove(admin_id)
        save_admins_to_json()
        
        # Notificar al admin eliminado
        try:
            await context.bot.send_message(
                chat_id=admin_id,
                text=(
                    "⚠️ <b>PERMISOS DE ADMIN REVOCADOS</b>\n\n"
                    "Tus permisos de administrador secundario han sido revocados.\n\n"
                    "Ya no puedes usar comandos de administración.\n\n"
                    "Contacta a los admins principales si crees que es un error."
                ),
                parse_mode='HTML'
            )
        except:
            pass
        
        # Notificar a todos los admins principales
        for admin_principal in ADMINS_PRINCIPALES:
            if str(admin_principal) != str(user_id):  # No notificar al que lo eliminó
                try:
                    await context.bot.send_message(
                        chat_id=admin_principal,
                        text=(
                            f"🗑️ <b>ADMIN SECUNDARIO ELIMINADO</b>\n\n"
                            f"👤 Admin que eliminó: <code>{user_id}</code>\n"
                            f"❌ Admin eliminado: <code>{admin_id}</code>\n"
                            f"🕐 Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                        ),
                        parse_mode='HTML'
                    )
                except:
                    pass
        
        await update.message.reply_text(
            f"✅ <b>ADMIN SECUNDARIO ELIMINADO</b>\n\n"
            f"🆔 ID: <code>{admin_id}</code>\n"
            f"💾 Backup actualizado\n"
            f"✉️ Usuario notificado",
            parse_mode='HTML'
        )
        
    except ValueError:
        await update.message.reply_text("❌ ID inválido. Debe ser un número.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def cmd_listaradmins(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra lista de todos los administradores"""
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        return
    
    msg = "👑 <b>LISTA DE ADMINISTRADORES</b>\n\n"
    
    msg += "🔹 <b>ADMINS PRINCIPALES:</b>\n"
    for admin in ADMINS_PRINCIPALES:
        msg += f"• <code>{admin}</code>\n"
    
    msg += f"\n🔸 <b>ADMINS SECUNDARIOS:</b> ({len(admins_secundarios)})\n"
    if admins_secundarios:
        for admin in admins_secundarios:
            msg += f"• <code>{admin}</code>\n"
    else:
        msg += "• No hay admins secundarios\n"
    
    msg += f"\n📊 <b>Total:</b> {len(ADMINS_PRINCIPALES) + len(admins_secundarios)} administradores"
    
    await update.message.reply_text(msg, parse_mode='HTML')

async def cmd_comandosadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra comandos de admin según permisos"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return
    
    es_principal = is_admin_principal(user_id)
    
    if es_principal:
        # ADMINS PRINCIPALES - Acceso completo
        msg = "👑 <b>COMANDOS ADMIN PRINCIPAL</b>\n\n"
        
        msg += "🤖 <b>CONTROL DEL BOT</b>\n"
        msg += "/off - Desactivar para usuarios normales\n"
        msg += "/activo - Activar para todos\n"
        msg += "/mantenimiento - Modo mantenimiento total\n"
        msg += "/mantenimientoapagado - Desactivar mantenimiento\n"
        msg += "/offgroup - Desactivar en grupos\n"
        msg += "/ongroup chatid - Activar en grupo específico\n\n"
        
        msg += "👥 <b>GESTIÓN DE USUARIOS</b>\n"
        msg += "/nuevo - Crear usuario directo\n"
        msg += "/usuarios - Listar usuarios\n"
        msg += "/eliminar numero - Eliminar usuario\n"
        msg += "/stats - Ver estadísticas\n\n"
        
        msg += "💰 <b>GESTIÓN DE SALDO</b>\n"
        msg += "/agregarsaldo numero cantidad\n"
        msg += "/recargasgratis - Activar recargas auto\n"
        msg += "/offrecargas - Desactivar recargas auto\n\n"
        
        msg += "🌟 <b>GESTIÓN VIP</b>\n"
        msg += "/agregarvip telegram_id - Agregar VIP\n"
        msg += "/eliminarvip telegram_id - Eliminar VIP\n"
        msg += "/listavip - Ver usuarios VIP\n"
        msg += "/statusvip - Estado backup VIP\n"
        msg += "/regenerarenlacevip telegram_id - Regenerar enlace\n\n"
        
        msg += "� <b>CONFIGURACIÓN VIP</b>\n"
        msg += "/agregarurlvip url - Agregar URL grupo VIP\n"
        msg += "/actualizarurlvip url - Actualizar URL\n"
        msg += "/configurargrupovip chatid - Config grupo VIP\n\n"
        
        msg += "📋 <b>GESTIÓN DE GRUPOS</b>\n"
        msg += "/agregargrupo chatid - Agregar grupo\n"
        msg += "/eliminargrupo chatid - Eliminar grupo\n\n"
        
        msg += "⚙️ <b>ADMINISTRACIÓN</b>\n"
        msg += "/agregaradmin telegram_id - Agregar admin secundario\n"
        msg += "/eliminaradmin telegram_id - Eliminar admin secundario\n"
        msg += "/listaradmins - Ver lista de admins\n"
        msg += "/comandosadmin - Ver esta ayuda\n\n"
        
        msg += "👑 <b>Tienes acceso completo al sistema</b>"
    
    else:
        # ADMINS SECUNDARIOS - Solo gestión VIP
        msg = "🔸 <b>COMANDOS ADMIN SECUNDARIO</b>\n\n"
        
        msg += "🌟 <b>GESTIÓN VIP (TU ÚNICO PERMISO)</b>\n"
        msg += "/agregarvip telegram_id - Agregar VIP\n"
        msg += "/eliminarvip telegram_id - Eliminar VIP\n"
        msg += "/listavip - Ver usuarios VIP\n"
        msg += "/statusvip - Estado backup VIP\n"
        msg += "/regenerarenlacevip telegram_id - Regenerar enlace\n\n"
        
        msg += "⚙️ <b>OTROS</b>\n"
        msg += "/listaradmins - Ver lista de admins\n"
        msg += "/comandosadmin - Ver esta ayuda\n\n"
        
        msg += "⚠️ <b>IMPORTANTE:</b>\n"
        msg += "• Solo puedes gestionar usuarios VIP\n"
        msg += "• Cuando agregues un VIP, los admins principales serán notificados\n"
        msg += "• NO tienes acceso a configuración de grupos, bot, usuarios o saldo\n"
        msg += "• Para más permisos, contacta a un admin principal"
    
    await update.message.reply_text(msg, parse_mode='HTML')

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Solo admins principales
    if not is_admin_principal(user_id):
        await update.message.reply_text(
            "❌ <b>ACCESO DENEGADO</b>\n\nSolo admins principales pueden ver estadísticas.",
            parse_mode='HTML'
        )
        return
    users_count = 0
    if db:
        users_count = len(list(db.collection('usuarios_app').stream()))
    await update.message.reply_text(
        f"� <b>ESTADÍSTICAS</b>\n\n"
        f"👥 Usuarios: {users_count}\n"
        f"🤖 Bot: {'✅ Activo' if bot_active else '❌ Inactivo'}\n"
        f"👑 Admins bot: {len(admin_ids)}",
        parse_mode='HTML'
    )

async def cmd_eliminar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin elimina un usuario por número de teléfono"""
    user_id = update.effective_user.id
    
    # Solo admins principales
    if not is_admin_principal(user_id):
        await update.message.reply_text(
            "❌ <b>ACCESO DENEGADO</b>\n\nSolo admins principales pueden eliminar usuarios.",
            parse_mode='HTML'
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            "📱 <b>ELIMINAR USUARIO (ADMIN)</b>\n\n"
            "Usa: <code>/eliminar numero</code>\n"
            "Ejemplo: <code>/eliminar 3001234567</code>",
            parse_mode='HTML'
        )
        return
    
    phone = context.args[0].strip()
    
    if db:
        try:
            # Obtener datos del usuario antes de eliminar
            doc = db.collection('users').document(phone).get()
            
            if not doc.exists:
                await update.message.reply_text(
                    f"❌ <b>NÚMERO NO ENCONTRADO</b>\n\n"
                    f"El número {phone} no existe en la base de datos.",
                    parse_mode='HTML'
                )
                return
            
            data = doc.to_dict()
            username = data.get('name', 'N/A')
            
            # Eliminar de la colección 'users' (por número)
            db.collection('users').document(phone).delete()
            
            # Intentar eliminar de 'usuarios_app' (por username)
            try:
                db.collection('usuarios_app').document(username).delete()
            except:
                pass
            
            await update.message.reply_text(
                f"✅ <b>USUARIO ELIMINADO</b>\n\n"
                f"📱 Número: {phone}\n"
                f"👤 Username: @{username}\n\n"
                f"Eliminado de ambas colecciones.",
                parse_mode='HTML'
            )
            
            print(f"✅ Admin {user_id} eliminó usuario: {phone} (@{username})")
            
        except Exception as e:
            print(f"❌ Error eliminando usuario: {e}")
            await update.message.reply_text(
                f"❌ <b>ERROR</b>\n\n"
                f"Hubo un error al eliminar el usuario.\n"
                f"Error: {str(e)}",
                parse_mode='HTML'
            )

async def cmd_usuarios(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    # Solo admins principales
    if not is_admin_principal(user_id):
        await update.message.reply_text(
            "❌ <b>ACCESO DENEGADO</b>\n\nSolo admins principales pueden ver usuarios.",
            parse_mode='HTML'
        )
        return
    if db:
        users = list(db.collection('users').stream())
        if not users:
            await update.message.reply_text("No hay usuarios registrados.")
            return
        msg = "👥 <b>USUARIOS REGISTRADOS</b>\n\n"
        for u in users[:20]:
            data = u.to_dict()
            msg += f"• {u.id} - {data.get('name', 'N/A')} - ${int(data.get('saldo', 0)):,}\n"
        if len(users) > 20:
            msg += f"\n... y {len(users) - 20} más"
        await update.message.reply_text(msg, parse_mode='HTML')

# ============ COMANDOS DE SALDO ============

async def cmd_eliminaruser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usuario VIP elimina una cuenta que ÉL creó"""
    try:
        user_id = update.effective_user.id
        
        print(f"🗑️ ELIMINARUSER - Usuario: {user_id}, Tipo: {type(user_id)}")
        print(f"🗑️ usuarios_vip: {usuarios_vip}")
        print(f"🗑️ user_id in usuarios_vip: {user_id in usuarios_vip}")
        print(f"🗑️ is_admin: {is_admin(user_id)}")
        print(f"🗑️ Argumentos: {context.args}")
        
        # Respuesta inmediata para confirmar que el comando se recibió
        await update.message.reply_text("⏳ Procesando eliminación...", parse_mode='HTML')
        print(f"✅ Respuesta inmediata enviada")
        
        # Solo VIPs y admins pueden usar este comando
        # Convertir user_id a int para comparar correctamente
        is_vip = user_id in usuarios_vip or str(user_id) in usuarios_vip
        is_bot_admin = is_admin(user_id)
        
        print(f"🔍 is_vip: {is_vip}, is_bot_admin: {is_bot_admin}")
        
        if not is_vip and not is_bot_admin:
            print(f"❌ Usuario {user_id} - No es VIP ni admin")
            await update.message.reply_text(
                "❌ <b>ACCESO DENEGADO</b>\n\n"
                "Este comando es solo para usuarios VIP.\n"
                "Contacta: @AXONDEVUI",
                parse_mode='HTML'
            )
            return
        
        print(f"✅ Usuario {user_id} - Es VIP o admin, continuando...")
        
        if not context.args:
            print(f"❌ Usuario {user_id} - Sin argumentos")
            await update.message.reply_text(
                "📱 <b>ELIMINAR USUARIO</b>\n\n"
                "Usa: <code>/eliminaruser numero</code>\n"
                "Ejemplo: <code>/eliminaruser 3001234567</code>\n\n"
                "⚠️ Solo puedes eliminar cuentas que TÚ creaste.",
                parse_mode='HTML'
            )
            return
        
        phone = context.args[0].strip()
        print(f"📱 Usuario {user_id} - Intentando eliminar: {phone}")
        
        if not db:
            print(f"❌ Firebase no disponible")
            await update.message.reply_text(
                "❌ <b>ERROR</b>\n\nBase de datos no disponible.",
                parse_mode='HTML'
            )
            return
        
        print(f"✅ Firebase disponible, buscando documento...")
        
        try:
            # Verificar que el usuario existe
            doc = db.collection('users').document(phone).get()
            print(f"✅ Documento obtenido, exists: {doc.exists}")
            
            if not doc.exists:
                print(f"❌ Usuario {user_id} - Número {phone} no existe")
                await update.message.reply_text(
                    "❌ <b>NÚMERO NO ENCONTRADO</b>\n\n"
                    f"El número {phone} no existe en la base de datos.",
                    parse_mode='HTML'
                )
                return
            
            data = doc.to_dict()
            created_by = data.get('created_by')
            username = data.get('name', 'N/A')
            
            print(f"📋 Usuario {user_id} - Cuenta encontrada: {username}, creada por: {created_by}")
            print(f"🔍 Tipos - user_id: {type(user_id)} ({user_id}), created_by: {type(created_by)} ({created_by})")
            print(f"🔍 Comparación - str(user_id): {str(user_id)}, str(created_by): {str(created_by)}")
            print(f"🔍 Son iguales? {str(created_by) == str(user_id)}")
            print(f"🔍 Es admin? {is_admin(user_id)}")
            
            # Verificar que el usuario VIP sea quien lo creó (admins pueden eliminar cualquiera)
            if not is_admin(user_id) and str(created_by) != str(user_id):
                print(f"❌ Usuario {user_id} - No es el creador. Creador: {created_by}")
                await update.message.reply_text(
                    "❌ <b>ACCESO DENEGADO</b>\n\n"
                    f"No puedes eliminar este usuario.\n"
                    f"Solo puedes eliminar cuentas que TÚ creaste.\n\n"
                    f"Este usuario fue creado por otro VIP.",
                    parse_mode='HTML'
                )
                return
            
            print(f"✅ Usuario {user_id} - Verificación pasada, eliminando...")
            
            # Eliminar de ambas colecciones
            db.collection('users').document(phone).delete()
            print(f"✅ Eliminado de users")
            
            # Intentar eliminar de usuarios_app si existe
            try:
                db.collection('usuarios_app').document(username).delete()
                print(f"✅ Usuario {user_id} - Eliminado de usuarios_app")
            except Exception as e:
                print(f"⚠️ No se pudo eliminar de usuarios_app: {e}")
            
            await update.message.reply_text(
                f"✅ <b>USUARIO ELIMINADO</b>\n\n"
                f"📱 Número: {phone}\n"
                f"👤 Username: @{username}\n\n"
                f"El usuario ha sido eliminado correctamente.",
                parse_mode='HTML'
            )
            
            print(f"✅ Usuario {user_id} - Eliminación completada")
            
            # Notificar al admin principal
            admin_msg = f"""
🗑️ <b>USUARIO ELIMINADO</b>

👤 <b>Eliminado por:</b> {user_id}
📱 <b>Número:</b> {phone}
👤 <b>Username:</b> @{username}
🕐 <b>Fecha:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            send_telegram_message(admin_msg, ADMIN_PRINCIPAL_1)
            
        except Exception as e:
            print(f"❌ Error en Firebase: {e}")
            import traceback
            traceback.print_exc()
            await update.message.reply_text(
                "❌ <b>ERROR</b>\n\n"
                f"Hubo un error al eliminar el usuario.\n"
                f"Error: {str(e)}\n\n"
                "Intenta de nuevo o contacta al soporte.",
                parse_mode='HTML'
            )
    
    except Exception as e:
        print(f"❌ ERROR GENERAL en cmd_eliminaruser: {e}")
        import traceback
        traceback.print_exc()
        try:
            await update.message.reply_text(
                "❌ <b>ERROR CRÍTICO</b>\n\n"
                f"Hubo un error inesperado: {str(e)}\n\n"
                "Contacta al soporte: @AXONDEVUI",
                parse_mode='HTML'
            )
        except Exception as e2:
            print(f"❌ No se pudo enviar mensaje de error: {e2}")

async def cmd_saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usuario consulta su saldo"""
    user_id = update.effective_user.id
    
    if not bot_active and not is_admin(user_id):
        await update.message.reply_text(mensaje_bot_desactivado(), parse_mode='HTML')
        return
    
    if not context.args:
        await update.message.reply_text(
            "💰 <b>CONSULTAR SALDO</b>\n\n"
            "Usa: <code>/saldo numero</code>\n"
            "Ejemplo: <code>/saldo 3001234567</code>",
            parse_mode='HTML'
        )
        return
    
    phone = context.args[0].strip()
    
    if db:
        doc = db.collection('users').document(phone).get()
        if doc.exists:
            data = doc.to_dict()
            saldo = int(data.get('saldo', 0))
            name = data.get('name', 'N/A')
            await update.message.reply_text(
                f"💰 <b>SALDO</b>\n\n"
                f"📱 Número: {phone}\n"
                f"👤 Nombre: {name}\n"
                f"💵 Saldo: <b>${saldo:,}</b>",
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text("❌ Número no encontrado.")

async def cmd_agregarsaldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Solo admin - Agregar saldo a un usuario"""
    user_id = update.effective_user.id
    
    # Solo admins principales
    if not is_admin_principal(user_id):
        await update.message.reply_text(
            "❌ <b>ACCESO DENEGADO</b>\n\nSolo admins principales pueden agregar saldo.",
            parse_mode='HTML'
        )
        return
    
    if not context.args or len(context.args) != 2:
        await update.message.reply_text(
            "💰 <b>AGREGAR SALDO</b>\n\n"
            "Usa: <code>/agregarsaldo numero cantidad</code>\n"
            "Ejemplo: <code>/agregarsaldo 3001234567 50000</code>",
            parse_mode='HTML'
        )
        return
    
    phone = context.args[0].strip()
    cantidad_text = context.args[1].strip().replace('.', '').replace(',', '')
    
    if not cantidad_text.isdigit():
        await update.message.reply_text("❌ Cantidad inválida. Solo números.")
        return
    
    cantidad = int(cantidad_text)
    
    if db:
        doc = db.collection('users').document(phone).get()
        if doc.exists:
            data = doc.to_dict()
            saldo_actual = int(data.get('saldo', 0))
            nuevo_saldo = saldo_actual + cantidad
            
            db.collection('users').document(phone).update({
                'saldo': str(nuevo_saldo)
            })
            
            await update.message.reply_text(
                f"✅ <b>SALDO AGREGADO</b>\n\n"
                f"📱 Número: {phone}\n"
                f"💵 Saldo anterior: ${saldo_actual:,}\n"
                f"➕ Agregado: ${cantidad:,}\n"
                f"💰 Nuevo saldo: <b>${nuevo_saldo:,}</b>",
                parse_mode='HTML'
            )
        else:
            await update.message.reply_text("❌ Número no encontrado.")

async def cmd_recargar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usuario solicita recarga"""
    user_id = update.effective_user.id
    user = update.effective_user
    
    if not bot_active and not is_admin(user_id):
        await update.message.reply_text(mensaje_bot_desactivado(), parse_mode='HTML')
        return
    
    if not context.args or len(context.args) != 2:
        await update.message.reply_text(
            "💳 <b>RECARGAR SALDO</b>\n\n"
            "Usa: <code>/recargar numero cantidad</code>\n"
            "Ejemplo: <code>/recargar 3001234567 50000</code>",
            parse_mode='HTML'
        )
        return
    
    phone = context.args[0].strip()
    cantidad_text = context.args[1].strip().replace('.', '').replace(',', '')
    
    if not cantidad_text.isdigit():
        await update.message.reply_text("❌ Cantidad inválida. Solo números.")
        return
    
    cantidad = int(cantidad_text)
    
    # Verificar que el número existe
    if db:
        doc = db.collection('users').document(phone).get()
        if not doc.exists:
            await update.message.reply_text("❌ Número no encontrado. Primero crea tu cuenta con /crear")
            return
        
        data = doc.to_dict()
        saldo_actual = int(data.get('saldo', 0))
        
        # Si recargas gratis está activo, agregar saldo directo
        if recargas_gratis:
            nuevo_saldo = saldo_actual + cantidad
            db.collection('users').document(phone).update({
                'saldo': str(nuevo_saldo)
            })
            
            await update.message.reply_text(
                f"✅ <b>RECARGA EXITOSA</b>\n\n"
                f"📱 Número: {phone}\n"
                f"� Saldo anterior: ${saldo_actual:,}\n"
                f"➕ Recargado: ${cantidad:,}\n"
                f"� Nuevo saldo: <b>${nuevo_saldo:,}</b>",
                parse_mode='HTML'
            )
        else:
            # Recargas desactivadas, enviar solicitud al admin
            username = user.username or "Sin username"
            admin_message = f"""
💳 <b>SOLICITUD DE RECARGA</b>

👤 <b>Usuario:</b> @{username}
🆔 <b>Telegram ID:</b> {user_id}
📱 <b>Número:</b> {phone}
💰 <b>Cantidad:</b> ${cantidad:,}
🕐 <b>Fecha:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

📌 Para agregar el saldo usa:
<code>/agregarsaldo {phone} {cantidad}</code>
"""
            send_telegram_message(admin_message, ADMIN_CHAT_ID)
            
            await update.message.reply_text(
                f"✅ <b>SOLICITUD ENVIADA</b>\n\n"
                f"📱 Número: {phone}\n"
                f"💰 Cantidad: ${cantidad:,}\n\n"
                f"📌 Envía el pago al número:\n"
                f"<code>{NUMERO_RECARGA}</code>\n\n"
                f"⏳ Una vez confirmes el pago, tu saldo será actualizado.",
                parse_mode='HTML'
            )

async def cmd_recargasgratis(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin activa recargas gratis"""
    global recargas_gratis
    user_id = update.effective_user.id
    
    # Solo admins principales
    if not is_admin_principal(user_id):
        await update.message.reply_text(
            "❌ <b>ACCESO DENEGADO</b>\n\nSolo admins principales pueden gestionar recargas.",
            parse_mode='HTML'
        )
        return
    
    recargas_gratis = True
    await update.message.reply_text("🟢 Recargas GRATIS activadas. Los usuarios pueden recargarse automáticamente.")

async def cmd_offrecargas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin desactiva recargas gratis"""
    global recargas_gratis
    user_id = update.effective_user.id
    
    # Solo admins principales
    if not is_admin_principal(user_id):
        await update.message.reply_text(
            "❌ <b>ACCESO DENEGADO</b>\n\nSolo admins principales pueden gestionar recargas.",
            parse_mode='HTML'
        )
        return
    
    recargas_gratis = False
    await update.message.reply_text("🔴 Recargas GRATIS desactivadas. Los usuarios enviarán solicitudes.")

# ============ GESTIÓN DE GRUPOS Y VIP ============

async def cmd_agregargrupo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin agrega grupo permitido"""
    user_id = update.effective_user.id
    
    # Solo admins principales
    if not is_admin_principal(user_id):
        await update.message.reply_text(
            "❌ <b>ACCESO DENEGADO</b>\n\nSolo admins principales pueden gestionar grupos.",
            parse_mode='HTML'
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            "📌 Uso: <code>/agregargrupo chatid</code>\n"
            "Ejemplo: <code>/agregargrupo -1001234567890</code>",
            parse_mode='HTML'
        )
        return
    
    try:
        chat_id = int(context.args[0])
        grupos_permitidos.add(chat_id)
        await update.message.reply_text(f"✅ Grupo {chat_id} agregado a la lista de permitidos.")
    except:
        await update.message.reply_text("❌ Chat ID inválido.")

async def cmd_eliminargrupo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin elimina grupo permitido"""
    user_id = update.effective_user.id
    
    # Solo admins principales
    if not is_admin_principal(user_id):
        await update.message.reply_text(
            "❌ <b>ACCESO DENEGADO</b>\n\nSolo admins principales pueden gestionar grupos.",
            parse_mode='HTML'
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            "📌 Uso: <code>/eliminargrupo chatid</code>\n"
            "Ejemplo: <code>/eliminargrupo -1001234567890</code>",
            parse_mode='HTML'
        )
        return
    
    try:
        chat_id = int(context.args[0])
        if chat_id in grupos_permitidos:
            grupos_permitidos.remove(chat_id)
            await update.message.reply_text(f"✅ Grupo {chat_id} eliminado de la lista.")
        else:
            await update.message.reply_text("❌ Ese grupo no está en la lista.")
    except:
        await update.message.reply_text("❌ Chat ID inválido.")

async def cmd_agregarvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin agrega usuario VIP, genera enlace exclusivo y notifica automáticamente"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return
    
    if not context.args:
        await update.message.reply_text(
            "📌 Uso: <code>/agregarvip telegram_id</code>\n"
            "Ejemplo: <code>/agregarvip 123456789</code>\n\n"
            "Se generará un enlace VIP exclusivo automáticamente.",
            parse_mode='HTML'
        )
        return
    
    try:
        vip_id = int(context.args[0])
        usuarios_vip.add(vip_id)
        save_vip_to_json()  # Guardar inmediatamente
        
        # Verificar si quien agregó es admin secundario
        es_admin_secundario = str(user_id) in admins_secundarios
        
        # Generar enlace VIP exclusivo automáticamente
        enlace_generado = False
        enlace_vip = None
        
        if grupo_vip_id:
            try:
                # Crear enlace de invitación de un solo uso
                invite = await context.bot.create_chat_invite_link(
                    chat_id=grupo_vip_id,
                    member_limit=1,  # Solo 1 persona puede usar este enlace
                    name=f"VIP-{vip_id}"
                )
                enlace_vip = invite.invite_link
                enlaces_vip_personales[vip_id] = enlace_vip
                enlace_generado = True
                print(f"✅ Enlace VIP generado para {vip_id}: {enlace_vip}")
            except Exception as e:
                print(f"❌ Error generando enlace VIP: {e}")
        
        # Notificar al usuario automáticamente
        notificado = await notificar_activacion_vip(vip_id, context)
        
        # Si es admin secundario, notificar a los admins principales
        if es_admin_secundario:
            for admin_principal in ADMINS_PRINCIPALES:
                try:
                    notif_msg = (
                        f"⚠️ <b>NOTIFICACIÓN DE ADMIN SECUNDARIO</b>\n\n"
                        f"👤 Admin: <code>{user_id}</code>\n"
                        f"🌟 Agregó VIP: <code>{vip_id}</code>\n"
                        f"🕐 Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                    )
                    if enlace_generado:
                        notif_msg += f"🔗 Enlace: <code>{enlace_vip}</code>\n\n"
                    notif_msg += f"💡 Revisa esta acción y contacta al admin si es necesario."
                    
                    await context.bot.send_message(
                        chat_id=admin_principal,
                        text=notif_msg,
                        parse_mode='HTML'
                    )
                except Exception as e:
                    print(f"❌ Error notificando a admin principal {admin_principal}: {e}")
        
        # Mensaje de confirmación al admin
        msg = f"✅ <b>Usuario {vip_id} agregado como VIP</b> 🌟\n\n"
        
        if enlace_generado:
            msg += f"🔗 <b>Enlace exclusivo generado:</b>\n<code>{enlace_vip}</code>\n\n"
            msg += f"⚠️ Este enlace:\n"
            msg += f"• Es de un solo uso\n"
            msg += f"• Se revocará automáticamente al unirse\n"
            msg += f"• Se generará uno nuevo para el próximo VIP\n\n"
        else:
            msg += f"⚠️ No se pudo generar enlace (configura grupo VIP)\n\n"
        
        if notificado:
            msg += f"✉️ Notificación enviada al usuario\n"
        else:
            msg += f"⚠️ No se pudo notificar (usuario debe iniciar el bot)\n"
        
        msg += f"💾 Backup guardado"
        
        if es_admin_secundario:
            msg += f"\n\n📢 Admins principales notificados"
        
        await update.message.reply_text(msg, parse_mode='HTML')
        
    except ValueError:
        await update.message.reply_text("❌ ID inválido. Debe ser un número.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")

async def cmd_eliminarvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin elimina usuario VIP"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return
    
    if not context.args:
        await update.message.reply_text(
            "📌 Uso: <code>/eliminarvip telegram_id</code>",
            parse_mode='HTML'
        )
        return
    
    try:
        vip_id = int(context.args[0])
        if vip_id in usuarios_vip:
            usuarios_vip.remove(vip_id)
            save_vip_to_json()  # Guardar inmediatamente
            # Eliminar enlace personal si existe
            if vip_id in enlaces_vip_personales:
                del enlaces_vip_personales[vip_id]
            await update.message.reply_text(f"✅ Usuario {vip_id} eliminado de VIP.\n💾 Backup actualizado")
        else:
            await update.message.reply_text("❌ Ese usuario no es VIP.")
    except:
        await update.message.reply_text("❌ ID inválido.")

async def cmd_agregarurlvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin agrega URL del grupo VIP"""
    global url_grupo_vip
    user_id = update.effective_user.id
    
    # Solo admins principales
    if not is_admin_principal(user_id):
        await update.message.reply_text(
            "❌ <b>ACCESO DENEGADO</b>\n\nSolo admins principales pueden configurar grupo VIP.",
            parse_mode='HTML'
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            f"📌 Uso: <code>/agregarurlvip url</code>\n"
            f"Ejemplo: <code>/agregarurlvip https://t.me/GrupoVIP</code>",
            parse_mode='HTML'
        )
        return
    
    nueva_url = context.args[0]
    url_grupo_vip = nueva_url
    await update.message.reply_text(f"✅ URL VIP agregada:\n{url_grupo_vip}")

async def cmd_actualizarurlvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin actualiza URL del grupo VIP"""
    global url_grupo_vip
    user_id = update.effective_user.id
    
    # Solo admins principales
    if not is_admin_principal(user_id):
        await update.message.reply_text(
            "❌ <b>ACCESO DENEGADO</b>\n\nSolo admins principales pueden configurar grupo VIP.",
            parse_mode='HTML'
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            f"📌 URL actual: <code>{url_grupo_vip}</code>\n\n"
            f"Uso: <code>/actualizarurlvip nueva_url</code>\n"
            f"Ejemplo: <code>/actualizarurlvip https://t.me/NuevoGrupoVIP</code>",
            parse_mode='HTML'
        )
        return
    
    nueva_url = context.args[0]
    url_grupo_vip = nueva_url
    await update.message.reply_text(f"✅ URL VIP actualizada:\n{url_grupo_vip}")

async def cmd_listavip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin lista usuarios VIP con información completa"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return
    
    if not usuarios_vip:
        await update.message.reply_text("No hay usuarios VIP registrados.")
        return
    
    msg = f"🌟 <b>USUARIOS VIP</b>\n\n"
    msg += f"📊 Total: {len(usuarios_vip)}\n"
    msg += f"💾 Último backup: {last_vip_backup or 'N/A'}\n"
    msg += f"🔄 Última restauración: {last_vip_restore or 'N/A'}\n\n"
    msg += "<b>Lista:</b>\n"
    for vip_id in usuarios_vip:
        tiene_enlace = "✅" if vip_id in enlaces_vip_personales else "❌"
        msg += f"• {vip_id} - Enlace: {tiene_enlace}\n"
    await update.message.reply_text(msg, parse_mode='HTML')

async def cmd_regenerarenlacevip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin regenera el enlace VIP de un usuario"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return
    
    if not context.args:
        await update.message.reply_text(
            "📌 Uso: <code>/regenerarenlacevip telegram_id</code>\n"
            "Ejemplo: <code>/regenerarenlacevip 123456789</code>",
            parse_mode='HTML'
        )
        return
    
    try:
        vip_id = int(context.args[0])
        
        if vip_id not in usuarios_vip:
            await update.message.reply_text("❌ Ese usuario no es VIP.")
            return
        
        # Crear nuevo enlace
        nuevo_enlace = await crear_enlace_vip_personal(vip_id, context)
        
        if nuevo_enlace:
            enlaces_vip_personales[vip_id] = nuevo_enlace
            
            # Notificar al usuario
            try:
                await context.bot.send_message(
                    chat_id=vip_id,
                    text=(
                        "🔄 <b>ENLACE VIP RENOVADO</b>\n\n"
                        f"Tu nuevo enlace exclusivo:\n{nuevo_enlace}\n\n"
                        "⚠️ Este enlace es de un solo uso."
                    ),
                    parse_mode='HTML'
                )
                await update.message.reply_text(
                    f"✅ Enlace regenerado para {vip_id}\n"
                    f"✉️ Usuario notificado",
                    parse_mode='HTML'
                )
            except:
                await update.message.reply_text(
                    f"✅ Enlace regenerado para {vip_id}\n"
                    f"⚠️ No se pudo notificar al usuario",
                    parse_mode='HTML'
                )
        else:
            await update.message.reply_text("❌ Error al crear enlace. Verifica que el grupo VIP esté configurado.")
    except:
        await update.message.reply_text("❌ ID inválido.")

async def cmd_configurargrupovip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin configura el ID del grupo VIP"""
    global grupo_vip_id
    user_id = update.effective_user.id
    
    # Solo admins principales
    if not is_admin_principal(user_id):
        await update.message.reply_text(
            "❌ <b>ACCESO DENEGADO</b>\n\nSolo admins principales pueden configurar grupo VIP.",
            parse_mode='HTML'
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            f"📌 Grupo VIP actual: <code>{grupo_vip_id}</code>\n\n"
            f"Uso: <code>/configurargrupovip chatid</code>\n"
            f"Ejemplo: <code>/configurargrupovip -1001234567890</code>",
            parse_mode='HTML'
        )
        return
    
    try:
        chat_id = int(context.args[0])
        grupo_vip_id = chat_id
        await update.message.reply_text(f"✅ Grupo VIP configurado: {grupo_vip_id}")
    except:
        await update.message.reply_text("❌ Chat ID inválido.")

async def cmd_statusvip(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin ve el estado del sistema de backup VIP"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return
    
    # Leer info del archivo
    backup_info = "N/A"
    file_size = 0
    if os.path.exists(vip_backup_file):
        file_size = os.path.getsize(vip_backup_file)
        try:
            with open(vip_backup_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                backup_info = data.get('last_backup', 'N/A')
        except:
            backup_info = "Error leyendo archivo"
    
    msg = (
        f"💾 <b>ESTADO BACKUP VIP</b>\n\n"
        f"👥 Usuarios VIP activos: <b>{len(usuarios_vip)}</b>\n"
        f"📁 Archivo: <code>{vip_backup_file}</code>\n"
        f"📊 Tamaño: {file_size} bytes\n\n"
        f"⏰ <b>Último backup:</b>\n{last_vip_backup or 'Pendiente'}\n\n"
        f"🔄 <b>Última restauración:</b>\n{last_vip_restore or 'Pendiente'}\n\n"
        f"⚙️ <b>Sistema:</b>\n"
        f"• Auto-backup: ✅ Cada 5 min\n"
        f"• Auto-restore: ✅ Cada 5 min\n"
        f"• Peso optimizado: ✅ Solo JSON\n\n"
        f"📝 Los cambios se guardan automáticamente"
    )
    
    await update.message.reply_text(msg, parse_mode='HTML')

# ============ /nuevo - SOLO ADMIN ============

async def nuevo_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if not is_admin(user_id):
        await update.message.reply_text("❌ Este comando es solo para el administrador.")
        return ConversationHandler.END
    admin_nuevo_data[user_id] = {}
    await update.message.reply_text(
        "👑 <b>CREAR USUARIO (ADMIN)</b>\n\n"
        "📱 <b>PASO 1/3 - NÚMERO</b>\n"
        "Ingresa el número de teléfono (10 dígitos):",
        parse_mode='HTML'
    )
    return NUEVO_PHONE

async def nuevo_get_phone(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    phone = update.message.text.strip()
    if not phone.isdigit() or len(phone) != 10:
        await update.message.reply_text("❌ Número inválido. Debe tener 10 dígitos.\nIntenta de nuevo:")
        return NUEVO_PHONE
    admin_nuevo_data[user_id]['phone'] = phone
    await update.message.reply_text(
        "🔐 <b>PASO 2/3 - PIN</b>\n\n"
        "Ingresa el PIN (4 dígitos):\n"
        "⚠️ Puede empezar con 0, ejemplo: 0123",
        parse_mode='HTML'
    )
    return NUEVO_PIN

async def nuevo_get_pin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    pin = update.message.text.strip()
    if not pin.isdigit() or len(pin) != 4:
        await update.message.reply_text("❌ PIN inválido. Debe tener 4 dígitos.\nIntenta de nuevo:")
        return NUEVO_PIN
    admin_nuevo_data[user_id]['pin'] = pin
    await update.message.reply_text(
        "💰 <b>PASO 3/3 - SALDO</b>\n\n"
        "Ingresa el saldo inicial (solo números):\n"
        "Ejemplo: 500000",
        parse_mode='HTML'
    )
    return NUEVO_SALDO

async def nuevo_get_saldo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    saldo = update.message.text.strip().replace('.', '').replace(',', '')
    if not saldo.isdigit():
        await update.message.reply_text("❌ Saldo inválido. Solo números.\nIntenta de nuevo:")
        return NUEVO_SALDO
    
    phone = admin_nuevo_data[user_id]['phone']
    pin = admin_nuevo_data[user_id]['pin']
    saldo_final = int(saldo)
    created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    if db:
        try:
            existing = db.collection('users').document(phone).get()
            if existing.exists:
                await update.message.reply_text(f"⚠️ El número {phone} ya existe.\nUsa /eliminar {phone} primero.")
                del admin_nuevo_data[user_id]
                return ConversationHandler.END
            
            db.collection('users').document(phone).set({
                'name': phone,
                'pin': str(pin),
                'saldo': str(saldo_final),
                'isActive': True,
                'created_by': user_id,  # ID de Telegram de quien lo creó
                'created_at': created_at
            })
            
            await update.message.reply_text(
                f"✅ <b>USUARIO CREADO</b>\n\n"
                f"📱 Número: <code>{phone}</code>\n"
                f"🔐 PIN: <code>{pin}</code>\n"
                f"💰 Saldo: ${saldo_final:,}\n\n"
                f"🔑 Para entrar a la app usar: <code>{phone}</code>",
                parse_mode='HTML'
            )
        except Exception as e:
            print(f"Firebase error: {e}")
            await update.message.reply_text("❌ Error al guardar. Intenta de nuevo.")
    else:
        await update.message.reply_text("❌ Firebase no está conectado.")
    
    del admin_nuevo_data[user_id]
    return ConversationHandler.END

async def nuevo_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id in admin_nuevo_data:
        del admin_nuevo_data[user_id]
    await update.message.reply_text("❌ Creación de usuario cancelada.")
    return ConversationHandler.END

# ============ FLASK ROUTES ============

@app.route('/', methods=['GET'])
def home():
    return jsonify({'status': 'online', 'bot_active': bot_active})

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'healthy', 'firebase': firebase_initialized})

@app.route('/verify', methods=['POST'])      
def verify_user():
    try:
        data = request.get_json()
        telegram_username = data.get('username', '').strip().replace('@', '').lower()
        
        if not telegram_username:
            return jsonify({'success': False, 'verified': False, 'error': 'Username required'})
        
        if db:
            # Buscar en usuarios_app por telegram_username
            user_app_doc = db.collection('usuarios_app').document(telegram_username).get()
            
            if not user_app_doc.exists:
                return jsonify({'success': True, 'verified': False, 'message': 'Username no registrado en el bot'})
            
            # El usuario existe en usuarios_app, ahora buscar sus datos en users
            # Necesitamos encontrar el documento en users que tenga este username
            users_query = db.collection('users').where('name', '==', telegram_username).limit(1).stream()
            user_doc = None
            phone = None
            
            for doc in users_query:
                user_doc = doc
                phone = doc.id
                break
            
            if user_doc:
                user_info = user_doc.to_dict()
                message = f"""
ðŸ" <b>LOGIN EN APP</b>

ðŸ'¤ <b>Username:</b> @{telegram_username}
ðŸ"± <b>Número:</b> {phone}
ðŸ'° <b>Saldo:</b> ${int(user_info.get('saldo', 0)):,}
ðŸ• <b>Fecha:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
ðŸŒ <b>IP:</b> {request.remote_addr}
"""
                send_telegram_message(message, ADMIN_CHAT_ID)
                return jsonify({
                    'success': True,
                    'verified': True,
                    'username': telegram_username,
                    'phone': phone,
                    'saldo': int(user_info.get('saldo', 0)),
                    'pin': user_info.get('pin'),
                    'isActive': user_info.get('isActive', True),
                    'message': 'Usuario verificado'
                })
            else:
                return jsonify({'success': True, 'verified': False, 'message': 'Username registrado pero sin cuenta completa. Usa /nequiaxonlabs en el bot'})
        
        return jsonify({'success': True, 'verified': False, 'message': 'Firebase no disponible'})
    except Exception as e:
        print(f"Error en verify_user: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/get_user/<username>', methods=['GET'])
def get_user(username):
    try:
        phone = username.strip()
        if db:
            doc = db.collection('users').document(phone).get()
            if doc.exists:
                return jsonify({'success': True, 'data': doc.to_dict()})
        return jsonify({'success': False, 'message': 'Not found'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

def run_flask():
    port = int(os.getenv('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False)

def main():
    init_firebase()
    load_vip_from_json()  # Cargar usuarios VIP al iniciar
    load_admins_from_json()  # Cargar admins secundarios al iniciar
    
    # Iniciar threads de backup y restore automático
    backup_thread = threading.Thread(target=auto_backup_vip, daemon=True)
    backup_thread.start()
    print("💾 Auto-backup VIP iniciado (cada 5 min)")
    
    restore_thread = threading.Thread(target=auto_restore_vip, daemon=True)
    restore_thread.start()
    print("🔄 Auto-restore VIP iniciado (cada 5 min)")
    
    flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    print("🌐 Flask started on port 5000")
    
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    # Handler /crear (solo pide arroba, luego /free)
    crear_handler = ConversationHandler(
        entry_points=[CommandHandler('crear', crear_start)],
        states={
            USERNAME_STEP: [MessageHandler(filters.TEXT & ~filters.COMMAND, get_username_step)],
            COMPLETE_ACCOUNT_STEP: [MessageHandler(filters.TEXT, complete_account_step)],
        },
        fallbacks=[CommandHandler('cancelar', cancel)],
    )
    
    # Handler /nuevo (solo admin)
    nuevo_handler = ConversationHandler(
        entry_points=[CommandHandler('nuevo', nuevo_start)],
        states={
            NUEVO_PHONE: [MessageHandler(filters.TEXT & ~filters.COMMAND, nuevo_get_phone)],
            NUEVO_PIN: [MessageHandler(filters.TEXT & ~filters.COMMAND, nuevo_get_pin)],
            NUEVO_SALDO: [MessageHandler(filters.TEXT & ~filters.COMMAND, nuevo_get_saldo)],
        },
        fallbacks=[CommandHandler('cancelar', nuevo_cancel)],
    )
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CallbackQueryHandler(button_callback))  # Handler para botones
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_member))  # Detectar nuevos miembros
    application.add_handler(crear_handler)
    application.add_handler(nuevo_handler)
    application.add_handler(CommandHandler('nequiaxonlabs', cmd_nequiaxonlabs))
    application.add_handler(CommandHandler('off', cmd_off))
    application.add_handler(CommandHandler('activo', cmd_activo))
    application.add_handler(CommandHandler('mantenimiento', cmd_mantenimiento))
    application.add_handler(CommandHandler('mantenimientoapagado', cmd_mantenimientoapagado))
    application.add_handler(CommandHandler('offgroup', cmd_offgroup))
    application.add_handler(CommandHandler('ongroup', cmd_ongroup))
    application.add_handler(CommandHandler('agregaradmin', cmd_agregaradmin))
    application.add_handler(CommandHandler('eliminaradmin', cmd_eliminaradmin))
    application.add_handler(CommandHandler('listaradmins', cmd_listaradmins))
    application.add_handler(CommandHandler('comandosadmin', cmd_comandosadmin))
    application.add_handler(CommandHandler('stats', cmd_stats))
    application.add_handler(CommandHandler('eliminar', cmd_eliminar))
    application.add_handler(CommandHandler('usuarios', cmd_usuarios))
    application.add_handler(CommandHandler('eliminaruser', cmd_eliminaruser))  # VIPs pueden eliminar sus propios usuarios
    application.add_handler(CommandHandler('saldo', cmd_saldo))
    application.add_handler(CommandHandler('agregarsaldo', cmd_agregarsaldo))
    application.add_handler(CommandHandler('recargar', cmd_recargar))
    application.add_handler(CommandHandler('recargasgratis', cmd_recargasgratis))
    application.add_handler(CommandHandler('offrecargas', cmd_offrecargas))
    application.add_handler(CommandHandler('agregargrupo', cmd_agregargrupo))
    application.add_handler(CommandHandler('eliminargrupo', cmd_eliminargrupo))
    application.add_handler(CommandHandler('agregarvip', cmd_agregarvip))
    application.add_handler(CommandHandler('eliminarvip', cmd_eliminarvip))
    application.add_handler(CommandHandler('agregarurlvip', cmd_agregarurlvip))
    application.add_handler(CommandHandler('actualizarurlvip', cmd_actualizarurlvip))
    application.add_handler(CommandHandler('configurargrupovip', cmd_configurargrupovip))
    application.add_handler(CommandHandler('listavip', cmd_listavip))
    application.add_handler(CommandHandler('statusvip', cmd_statusvip))
    application.add_handler(CommandHandler('regenerarenlacevip', cmd_regenerarenlacevip))
    
    print("🤖 Telegram bot started")
    print(f"📢 Required group: {GROUP_LINK}")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == '__main__':
    import asyncio
    # Fix para Python 3.14+
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
    main()

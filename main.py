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
ADMIN_CHAT_ID = "8485045964"
REQUIRED_GROUP_ID = -1003710645728
GROUP_LINK = "https://t.me/comunidadofficialchat"
NUMERO_RECARGA = "3210000000"  # Número donde los usuarios envían el pago

# Bot state
bot_active = True
mantenimiento_mode = False  # Modo mantenimiento para TODOS
group_active = True
recargas_gratis = True  # Si está True, las recargas son automáticas
admin_ids = set([ADMIN_CHAT_ID])
grupos_permitidos = set([REQUIRED_GROUP_ID])  # Grupos donde el bot puede funcionar
grupo_activo_id = REQUIRED_GROUP_ID  # Grupo actualmente activo
usuarios_vip = set()  # IDs de usuarios VIP
url_grupo_vip = "https://t.me/GrupoVIPPrivado"  # URL del grupo VIP
grupo_vip_id = -1003875617504  # ID del grupo VIP configurado
vip_backup_file = 'usuariosvip.json'
last_vip_backup = None
last_vip_restore = None

# Control de uso diario (user_id: {'date': 'YYYY-MM-DD', 'count': 0})
uso_diario = {}
MAX_USO_DIARIO = 3

# Enlaces VIP de un solo uso (user_id: invite_link)
enlaces_vip_personales = {}

# Conversation states
USERNAME_STEP = 0
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
    return str(user_id) in admin_ids

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
    user_id = update.effective_user.id
    chat_type = update.effective_chat.type
    chat_id = update.effective_chat.id
    
    # VERIFICACIÓN 1: Modo Mantenimiento (afecta a TODOS excepto admins)
    if mantenimiento_mode and not is_admin(user_id):
        keyboard = [[InlineKeyboardButton("📞 Contactar Soporte", url="https://t.me/AXONDEVUI")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(mensaje_mantenimiento(), parse_mode='HTML', reply_markup=reply_markup)
        return
    
    # Si es grupo, verificar que sea el grupo permitido (excepto admins y VIPs)
    if chat_type in ['group', 'supergroup']:
        if not is_admin(user_id) and user_id not in usuarios_vip:
            if chat_id not in grupos_permitidos:
                return  # Ignorar si no es un grupo permitido
            if not group_active:
                return  # Ignorar si grupos están desactivados
    
    is_bot_admin = is_admin(user_id)
    is_vip = user_id in usuarios_vip
    
    # VERIFICACIÓN 2: Bot OFF (solo afecta a usuarios normales, VIPs siguen funcionando)
    if not bot_active and not is_bot_admin and not is_vip:
        keyboard = [[InlineKeyboardButton("🌟 Obtener VIP", url="https://t.me/AXONDEVUI")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(mensaje_bot_desactivado(), parse_mode='HTML', reply_markup=reply_markup)
        return
    
    # Verificar uso diario para usuarios normales
    if not is_bot_admin and not is_vip:
        puede_usar, usos_restantes = verificar_uso_diario(user_id)
        if not puede_usar:
            keyboard = [[InlineKeyboardButton("🌟 Obtener VIP", url="https://t.me/AXONDEVUI")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                "⚠️ <b>LÍMITE DIARIO ALCANZADO</b>\n\n"
                f"Has usado el bot {MAX_USO_DIARIO} veces hoy.\n"
                "Vuelve mañana o contacta para acceso VIP:\n\n"
                "🌟 <b>ACCESO VIP ILIMITADO</b>",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            return
    
    # Verificación de membresía solo para usuarios normales (no VIP, no admins)
    if not is_bot_admin and not is_grp_admin and not is_vip:
        is_member = await check_group_membership(user_id, context)
        if not is_member:
            keyboard = [[InlineKeyboardButton("🔗 Unirse al Grupo", url=GROUP_LINK)]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(
                f"❌ <b>ACCESO DENEGADO</b>\n\n"
                f"Debes unirte al grupo oficial para usar el bot.\n\n"
                f"Una vez te unas, vuelve y usa /start",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            return
    
    # Registrar uso para usuarios normales
    if not is_bot_admin and not is_grp_admin and not is_vip:
        registrar_uso(user_id)
        puede_usar, usos_restantes = verificar_uso_diario(user_id)
    
    # Botones para usuarios VIP
    if is_vip:
        keyboard = [
            [InlineKeyboardButton("🆕 Crear Cuenta", callback_data='crear_cuenta')],
            [InlineKeyboardButton("💰 Consultar Saldo", callback_data='consultar_saldo')],
            [InlineKeyboardButton("💳 Recargar", callback_data='recargar_saldo')],
            [InlineKeyboardButton("🌟 Grupo VIP", url=url_grupo_vip)],
            [InlineKeyboardButton("❓ Ayuda", callback_data='ayuda')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        # Verificar si tiene enlace personal
        if user_id in enlaces_vip_personales:
            enlace = enlaces_vip_personales[user_id]
            await update.message.reply_text(
                f"👋 <b>¡Bienvenido Usuario VIP!</b> 🌟\n\n"
                f"Tienes acceso exclusivo ilimitado.\n\n"
                f"🎁 <b>TU ENLACE VIP EXCLUSIVO:</b>\n"
                f"{enlace}\n\n"
                f"⚠️ Este enlace es de un solo uso.\n\n"
                f"Selecciona una opción:",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
        else:
            await update.message.reply_text(
                f"👋 <b>¡Bienvenido Usuario VIP!</b> 🌟\n\n"
                f"Tienes acceso exclusivo ilimitado.\n\n"
                f"Selecciona una opción:",
                parse_mode='HTML',
                reply_markup=reply_markup
            )
    # Botones para admins
    elif is_bot_admin:
        keyboard = [
            [InlineKeyboardButton("🆕 Crear Cuenta", callback_data='crear_cuenta')],
            [InlineKeyboardButton("💰 Consultar Saldo", callback_data='consultar_saldo')],
            [InlineKeyboardButton("💳 Recargar", callback_data='recargar_saldo')],
            [InlineKeyboardButton("👑 Panel Admin", callback_data='panel_admin')],
            [InlineKeyboardButton("❓ Ayuda", callback_data='ayuda')]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"👋 <b>¡Bienvenido Administrador!</b> 👑\n\n"
            f"Acceso completo al sistema.\n\n"
            f"Selecciona una opción:",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
    # Botones para usuarios normales
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
        await update.message.reply_text(
            f"👋 <b>¡Bienvenido a Nequi Axon Free!</b>\n\n"
            f"Gestiona tus cuentas de forma rápida y segura.\n\n"
            f"📊 <b>Usos restantes hoy:</b> {usos_restantes}/{MAX_USO_DIARIO}\n\n"
            f"Selecciona una opción:",
            parse_mode='HTML',
            reply_markup=reply_markup
        )

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
    
    user_data[user_id]['telegram_username'] = username
    
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
    return ConversationHandler.END

async def cmd_nequiaxonlabs(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    
    if user_id not in user_data or 'telegram_username' not in user_data.get(user_id, {}):
        await update.message.reply_text("❌ Primero usa /crear para registrar tu arroba.")
        return
    
    if not context.args or len(context.args) != 3:
        await update.message.reply_text(
            "❌ Formato incorrecto.\n\n"
            "Usa: <code>/nequiaxonlabs numero pin saldo</code>\n"
            "Ejemplo: <code>/nequiaxonlabs 3001234567 0515 500000</code>",
            parse_mode='HTML'
        )
        return
    
    phone = context.args[0].strip()
    pin = context.args[1].strip()
    saldo_text = context.args[2].strip().replace('.', '').replace(',', '')
    
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
        except Exception as e:
            print(f"Firebase error: {e}")
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
        f"✅ <b>¡CUENTA CREADA!</b>\n\n"
        f"👤 Username: <b>@{username}</b>\n"
        f"📱 Teléfono: {phone}\n"
        f"💰 Saldo: ${saldo:,}\n\n"
        f"🔐 Ingresa a la app con: <code>{username}</code>",
        parse_mode='HTML'
    )
    
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
    if not is_admin(user_id):
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
    if not is_admin(user_id):
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
    if not is_admin(user_id):
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
    if not is_admin(user_id):
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
    is_grp_admin = await is_group_admin(user_id, context)
    if not is_admin(user_id) and not is_grp_admin:
        return
    group_active = False
    await update.message.reply_text("🔴 Bot DESACTIVADO en grupos.")

async def cmd_ongroup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin activa bot solo en un grupo específico"""
    global grupo_activo_id, group_active
    user_id = update.effective_user.id
    if not is_admin(user_id):
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
    if not is_admin(update.effective_user.id):
        return
    if not context.args:
        await update.message.reply_text("Uso: /agregaradmin <telegram_id>")
        return
    new_admin_id = context.args[0]
    admin_ids.add(new_admin_id)
    await update.message.reply_text(f"✅ Admin agregado: {new_admin_id}")

async def cmd_comandosadmin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Muestra todos los comandos de admin organizados"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return
    
    await update.message.reply_text(
        "👑 <b>COMANDOS DE ADMINISTRADOR</b>\n\n"
        
        "🤖 <b>CONTROL DEL BOT</b>\n"
        "/off - Desactivar para usuarios normales (VIPs siguen)\n"
        "/activo - Activar para todos\n"
        "/mantenimiento - Desactivar para TODOS (incluye VIPs)\n"
        "/mantenimientoapagado - Reactivar después de mantenimiento\n"
        "/offgroup - Desactivar en grupos\n"
        "/ongroup chatid - Activar solo en un grupo\n\n"
        
        "👥 <b>GESTIÓN DE USUARIOS</b>\n"
        "/nuevo - Crear usuario directo\n"
        "/usuarios - Listar usuarios\n"
        "/eliminar username - Eliminar usuario\n"
        "/stats - Ver estadísticas\n\n"
        
        "💰 <b>GESTIÓN DE SALDO</b>\n"
        "/agregarsaldo numero cantidad\n"
        "/recargasgratis - Activar recargas auto\n"
        "/offrecargas - Desactivar recargas auto\n\n"
        
        "🌟 <b>GESTIÓN VIP</b>\n"
        "/agregarvip telegram_id - Agregar VIP (notifica auto)\n"
        "/eliminarvip telegram_id\n"
        "/listavip - Ver usuarios VIP\n"
        "/statusvip - Estado backup VIP\n"
        "/regenerarenlacevip telegram_id - Crear nuevo enlace\n"
        "/agregarurlvip url - Agregar URL grupo VIP\n"
        "/actualizarurlvip url - Actualizar URL\n"
        "/configurargrupovip chatid - Config grupo VIP\n\n"
        
        "📋 <b>GESTIÓN DE GRUPOS</b>\n"
        "/agregargrupo chatid\n"
        "/eliminargrupo chatid\n\n"
        
        "⚙️ <b>ADMINISTRACIÓN</b>\n"
        "/agregaradmin telegram_id\n"
        "/comandosadmin - Ver esta ayuda",
        parse_mode='HTML'
    )

async def cmd_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    is_grp_admin = await is_group_admin(user_id, context)
    if not is_admin(user_id) and not is_grp_admin:
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
    if not is_admin(user_id):
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
    is_grp_admin = await is_group_admin(user_id, context)
    if not is_admin(user_id) and not is_grp_admin:
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
    user_id = update.effective_user.id
    
    # Solo VIPs y admins pueden usar este comando
    if user_id not in usuarios_vip and not is_admin(user_id):
        await update.message.reply_text(
            "❌ <b>ACCESO DENEGADO</b>\n\n"
            "Este comando es solo para usuarios VIP.\n"
            "Contacta: @AXONDEVUI",
            parse_mode='HTML'
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            "📱 <b>ELIMINAR USUARIO</b>\n\n"
            "Usa: <code>/eliminaruser numero</code>\n"
            "Ejemplo: <code>/eliminaruser 3001234567</code>\n\n"
            "⚠️ Solo puedes eliminar cuentas que TÚ creaste.",
            parse_mode='HTML'
        )
        return
    
    phone = context.args[0].strip()
    
    if db:
        try:
            # Verificar que el usuario existe
            doc = db.collection('users').document(phone).get()
            
            if not doc.exists:
                await update.message.reply_text(
                    "❌ <b>NÚMERO NO ENCONTRADO</b>\n\n"
                    f"El número {phone} no existe en la base de datos.",
                    parse_mode='HTML'
                )
                return
            
            data = doc.to_dict()
            created_by = data.get('created_by')
            username = data.get('name', 'N/A')
            
            # Verificar que el usuario VIP sea quien lo creó (admins pueden eliminar cualquiera)
            if not is_admin(user_id) and created_by != user_id:
                await update.message.reply_text(
                    "❌ <b>ACCESO DENEGADO</b>\n\n"
                    f"No puedes eliminar este usuario.\n"
                    f"Solo puedes eliminar cuentas que TÚ creaste.\n\n"
                    f"Este usuario fue creado por: {created_by}",
                    parse_mode='HTML'
                )
                return
            
            # Eliminar de ambas colecciones
            db.collection('users').document(phone).delete()
            
            # Intentar eliminar de usuarios_app si existe
            try:
                db.collection('usuarios_app').document(username).delete()
            except:
                pass
            
            await update.message.reply_text(
                f"✅ <b>USUARIO ELIMINADO</b>\n\n"
                f"📱 Número: {phone}\n"
                f"👤 Username: @{username}\n\n"
                f"El usuario ha sido eliminado correctamente.",
                parse_mode='HTML'
            )
            
            # Notificar al admin
            admin_msg = f"""
🗑️ <b>USUARIO ELIMINADO</b>

👤 <b>Eliminado por:</b> {user_id}
📱 <b>Número:</b> {phone}
👤 <b>Username:</b> @{username}
🕐 <b>Fecha:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            send_telegram_message(admin_msg, ADMIN_CHAT_ID)
            
        except Exception as e:
            print(f"Error eliminando usuario: {e}")
            await update.message.reply_text(
                "❌ <b>ERROR</b>\n\n"
                "Hubo un error al eliminar el usuario.\n"
                "Intenta de nuevo o contacta al soporte.",
                parse_mode='HTML'
            )

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
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Este comando es solo para el administrador.")
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
    if not is_admin(user_id):
        return
    recargas_gratis = True
    await update.message.reply_text("🟢 Recargas GRATIS activadas. Los usuarios pueden recargarse automáticamente.")

async def cmd_offrecargas(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin desactiva recargas gratis"""
    global recargas_gratis
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return
    recargas_gratis = False
    await update.message.reply_text("🔴 Recargas GRATIS desactivadas. Los usuarios enviarán solicitudes.")

# ============ GESTIÓN DE GRUPOS Y VIP ============

async def cmd_agregargrupo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Admin agrega grupo permitido"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
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
    if not is_admin(user_id):
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
    if not is_admin(user_id):
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
    if not is_admin(user_id):
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
    if not is_admin(user_id):
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

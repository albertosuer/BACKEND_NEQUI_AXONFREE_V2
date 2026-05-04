from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
from dateutil.relativedelta import relativedelta
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
ADMIN_PRINCIPAL_1 = "8485352219"  # Admin Principal ÚNICO - @AXONDEVUI
ADMIN_PRINCIPAL_2 = ""  # Sin segundo admin principal
ADMINS_PRINCIPALES = {ADMIN_PRINCIPAL_1}  # Solo un admin principal
REQUIRED_GROUP_ID = -1003707561305  # Nuevo grupo oficial
GROUP_LINK = "https://t.me/Comunidadaxonlabs"
NUMERO_RECARGA = "3210000000"  # Número donde los usuarios envían el pago

# Bot state
bot_active = True
mantenimiento_mode = False  # Modo mantenimiento para TODOS
group_active = True
recargas_gratis = True  # Si está True, las recargas son automáticas
admin_ids = set([ADMIN_PRINCIPAL_1])  # Solo un admin principal
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
usuarios_que_iniciaron = set()  # Lista de usuarios que han iniciado el bot

# Initialize Firebase (OBLIGATORIO)
firebase_initialized = False
db = None

# ============ FUNCIONES JSON LOCALES (SIN FIREBASE) ============

def load_users_local():
    """Cargar usuarios desde archivo JSON local"""
    try:
        if os.path.exists(users_file):
            with open(users_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"❌ Error cargando users local: {e}")
        return {}

def save_users_local(users_data):
    """Guardar usuarios en archivo JSON local"""
    try:
        with open(users_file, 'w', encoding='utf-8') as f:
            json.dump(users_data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"❌ Error guardando users local: {e}")
        return False

def load_usuarios_app_local():
    """Cargar usuarios_app desde archivo JSON local"""
    try:
        if os.path.exists(usuarios_app_file):
            with open(usuarios_app_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"❌ Error cargando usuarios_app local: {e}")
        return {}

def save_usuarios_app_local(usuarios_app_data):
    """Guardar usuarios_app en archivo JSON local"""
    try:
        with open(usuarios_app_file, 'w', encoding='utf-8') as f:
            json.dump(usuarios_app_data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"❌ Error guardando usuarios_app local: {e}")
        return False

def init_firebase():
    """Inicializar Firebase - OBLIGATORIO para la app"""
    global firebase_initialized, db
    
    print("🔥 INICIANDO FIREBASE...")
    
    try:
        # Verificar archivo de credenciales
        if not os.path.exists('firebase_credentials.json'):
            print("❌ firebase_credentials.json NO EXISTE")
            return False
        
        print("✅ Archivo de credenciales encontrado")
        
        # Configurar variable de entorno si no existe
        if not os.getenv('GOOGLE_APPLICATION_CREDENTIALS'):
            os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = 'firebase_credentials.json'
            print("✅ Variable GOOGLE_APPLICATION_CREDENTIALS configurada")
        
        # Limpiar cualquier inicialización previa
        try:
            app = firebase_admin.get_app()
            firebase_admin.delete_app(app)
            print("🔄 App Firebase anterior eliminada")
        except ValueError:
            pass  # No hay app previa
        
        # Inicializar Firebase
        cred = credentials.Certificate('firebase_credentials.json')
        firebase_admin.initialize_app(cred)
        
        # Crear cliente Firestore
        db = firestore.client()
        firebase_initialized = True
        
        print("✅ FIREBASE INICIALIZADO CORRECTAMENTE")
        
        # Test básico
        test_collection = db.collection('usuarios_app').limit(1)
        docs = test_collection.get()
        print(f"✅ Test conexión: {len(docs)} documentos encontrados")
        
        return True
        
    except Exception as e:
        print(f"❌ ERROR FIREBASE: {e}")
        print(f"❌ Tipo de error: {type(e).__name__}")
        
        # Información adicional para debugging
        import sys
        print(f"❌ Python version: {sys.version}")
        print(f"❌ Working directory: {os.getcwd()}")
        
        firebase_initialized = False
        db = None
        return False

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
                print(f"✅ VIP usuarios: {usuarios_vip}")
                print(f"✅ VIP tipos: {[type(u) for u in usuarios_vip]}")
        else:
            # Crear archivo si no existe
            save_vip_to_json()
            print("📁 Archivo VIP creado")
    except Exception as e:
        print(f"❌ Error cargando VIP: {e}")
        import traceback
        traceback.print_exc()

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
    return str(user_id) == ADMIN_PRINCIPAL_1

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
    global usuarios_que_iniciaron
    user = update.effective_user
    user_id = user.id
    username = user.username or "Sin username"
    first_name = user.first_name or "Usuario"
    
    # Agregar usuario a la lista de usuarios que han iniciado el bot
    usuarios_que_iniciaron.add(user_id)
    print(f"✅ Usuario {user_id} agregado a lista de usuarios que iniciaron el bot")
    
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
    
    # PAGINACIÓN DE USUARIOS
    elif data.startswith('usuarios_page_'):
        if not is_admin_principal(user_id):
            await query.answer("❌ No tienes permisos", show_alert=True)
            return
        
        try:
            pagina = int(data.split('_')[-1])
            await mostrar_usuarios_paginados(update, context, pagina)
        except ValueError:
            await query.answer("❌ Error en paginación", show_alert=True)
    
    # ESTADÍSTICAS DE USUARIOS
    elif data == 'usuarios_stats':
        if not is_admin_principal(user_id):
            await query.answer("❌ No tienes permisos", show_alert=True)
            return
        
        await mostrar_estadisticas_usuarios(update, context)

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
                    send_telegram_message(admin_msg, ADMIN_PRINCIPAL_1)
                    
                    print(f"✅ Nuevo enlace VIP generado después de que {user_id} se unió")
                    
                except Exception as e:
                    error_msg = (
                        f"❌ <b>ERROR AL REGENERAR ENLACE</b>\n\n"
                        f"Usuario {user_id} se unió pero no se pudo generar nuevo enlace.\n"
                        f"Error: {str(e)}"
                    )
                    send_telegram_message(error_msg, ADMIN_PRINCIPAL_1)
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
    
    # VALIDACIÓN OBLIGATORIA DE USERNAME PARA VIPs
    if is_vip and not update.effective_user.username:
        print(f"❌ Usuario VIP {user_id} - Sin username de Telegram")
        keyboard = [[InlineKeyboardButton("📞 Contactar Soporte", url="https://t.me/AXONDEVUI")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "⚠️ <b>USERNAME REQUERIDO PARA VIP</b>\n\n"
            "Como usuario VIP, necesitas tener un username de Telegram para usar el bot.\n\n"
            "📋 <b>Cómo configurar tu username:</b>\n"
            "1. Ve a Configuración de Telegram\n"
            "2. Toca en 'Editar Perfil'\n"
            "3. Agrega un nombre de usuario único\n"
            "4. Guarda los cambios\n\n"
            "Una vez tengas username, podrás usar el bot normalmente.\n\n"
            "💡 <b>¿Por qué es necesario?</b>\n"
            "Para identificar correctamente qué usuario VIP creó cada cuenta.",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        return ConversationHandler.END
    
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
    
    # VERIFICAR QUE EL USUARIO TENGA USERNAME CONFIGURADO EN TELEGRAM
    telegram_username = update.effective_user.username
    if not telegram_username:
        print(f"❌ Usuario {user_id} - No tiene username configurado")
        keyboard = [[InlineKeyboardButton("📞 Contactar Soporte", url="https://t.me/AXONDEVUI")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            "❌ <b>USERNAME REQUERIDO</b>\n\n"
            "Para crear una cuenta necesitas tener configurado un username (@) en tu perfil de Telegram.\n\n"
            "📌 <b>Cómo configurar tu username:</b>\n"
            "1. Ve a Configuración de Telegram\n"
            "2. Edita tu perfil\n"
            "3. Agrega un username único\n"
            "4. Guarda los cambios\n\n"
            "Una vez configurado, vuelve y usa /crear",
            parse_mode='HTML',
            reply_markup=reply_markup
        )
        return ConversationHandler.END
    
    # IR DIRECTO A CREAR CUENTA CON INSTRUCCIONES
    user_data[user_id] = {
        'telegram_id': user_id,
        'telegram_username': telegram_username
    }
    print(f"✅ Usuario {user_id} - Username detectado: @{telegram_username}")
    
    keyboard = [[InlineKeyboardButton("❌ Cancelar", callback_data='cancelar_crear')]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        f"📱 <b>CREAR CUENTA NEQUI</b>\n\n"
        f"Username detectado: <b>@{telegram_username}</b>\n\n"
        f"Envía el comando con tus datos:\n"
        f"<code>/nequiaxonlabs numero pin saldo</code>\n\n"
        f"📌 <b>Ejemplo:</b>\n"
        f"<code>/nequiaxonlabs 3001234567 0515 500000</code>\n\n"
        f"⚠️ Número: 10 dígitos | PIN: 4 dígitos | Saldo: solo números",
        parse_mode='HTML',
        reply_markup=reply_markup
    )
    print(f"✅ Usuario {user_id} - Mensaje enviado")
    return COMPLETE_ACCOUNT_STEP

async def get_username_step(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global db
    user_id = update.effective_user.id
    username = update.message.text.strip().replace('@', '').lower()
    
    print(f"📝 get_username_step - Usuario: {user_id}, Username: {username}")
    print(f"📝 db disponible: {db is not None}")
    print(f"📝 firebase_initialized: {firebase_initialized}")
    
    if len(username) < 3:
        await update.message.reply_text("❌ Username muy corto. Mínimo 3 caracteres.\nIntenta de nuevo:")
        return USERNAME_STEP
    
    if not db:
        print(f"❌ CRÍTICO: db es None en get_username_step")
        await update.message.reply_text(
            "❌ <b>ERROR DE CONEXIÓN</b>\n\n"
            "No se puede conectar a la base de datos.\n"
            "Intenta de nuevo en unos segundos.",
            parse_mode='HTML'
        )
        return USERNAME_STEP
    
    try:
        print(f"🔍 Verificando si username '{username}' ya existe...")
        # Verificar si ya existe en usuarios_app
        existing = db.collection('usuarios_app').document(username).get()
        print(f"🔍 Username existe: {existing.exists}")
        
        if existing.exists:
            print(f"❌ Username '{username}' ya existe")
            await update.message.reply_text("❌ Este username ya está registrado. Usa otro:")
            return USERNAME_STEP
        
        print(f"✅ Username '{username}' disponible, guardando en usuarios_app...")
        
        # Guardar solo el arroba en usuarios_app
        user_doc_data = {
            'telegram_username': username,
            'telegram_id': user_id,
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'active': True
        }
        
        print(f"📝 Datos a guardar: {user_doc_data}")
        
        db.collection('usuarios_app').document(username).set(user_doc_data)
        print(f"✅ Username '{username}' guardado exitosamente en usuarios_app")
        
        # Verificar que se guardó correctamente
        verification = db.collection('usuarios_app').document(username).get()
        if verification.exists:
            print(f"✅ Verificación exitosa: documento '{username}' existe en usuarios_app")
            saved_data = verification.to_dict()
            print(f"✅ Datos guardados: {saved_data}")
        else:
            print(f"❌ ERROR: documento '{username}' NO se guardó en usuarios_app")
        
    except Exception as e:
        print(f"❌ Error guardando username en Firebase: {e}")
        import traceback
        traceback.print_exc()
        await update.message.reply_text(
            "❌ <b>ERROR</b>\n\n"
            "Hubo un error guardando tu username.\n"
            "Intenta de nuevo.",
            parse_mode='HTML'
        )
        return USERNAME_STEP
    
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
    global db
    user_id = update.effective_user.id
    
    print(f"🔍 complete_account_step - Usuario: {user_id}")
    print(f"🔍 user_data: {user_data.get(user_id, 'NO EXISTE')}")
    
    # Verificar que sea el comando correcto - Si no es /nequiaxonlabs, terminar el handler
    if not update.message.text.startswith('/nequiaxonlabs'):
        # Si es otro comando, terminar el ConversationHandler para que el comando funcione normalmente
        if update.message.text.startswith('/'):
            print(f"🔍 Usuario {user_id} - Comando diferente detectado: {update.message.text[:20]}, terminando handler")
            # Limpiar user_data
            if user_id in user_data:
                del user_data[user_id]
            return ConversationHandler.END
        
        # Si no es un comando, mostrar mensaje de ayuda
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
    
    # Usar el username guardado del paso anterior
    username = user_data[user_id]['telegram_username']
    saldo = int(saldo_text)
    created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    print(f"✅ Usuario {user_id} - Guardando cuenta: {username}, {phone}")
    
    if db:
        try:
            # VERIFICAR SI EL NÚMERO YA EXISTE en 'users'
            print(f"🔍 Verificando si número {phone} ya existe en 'users'...")
            try:
                existing_doc = db.collection('users').document(phone).get()
                if existing_doc.exists:
                    print(f"❌ Usuario {user_id} - Número {phone} ya existe en 'users'")
                    await update.message.reply_text(
                        f"❌ <b>NÚMERO YA REGISTRADO</b>\n\n"
                        f"El número <code>{phone}</code> ya se encuentra registrado.\n"
                        f"Usa un número diferente para crear tu cuenta.",
                        parse_mode='HTML'
                    )
                    return COMPLETE_ACCOUNT_STEP
                print(f"✅ Número {phone} disponible en 'users'")
            except Exception as check_error:
                print(f"❌ Error verificando número: {check_error}")
                await update.message.reply_text("❌ Error verificando número. Intenta de nuevo.")
                return COMPLETE_ACCOUNT_STEP
            
            # Guardar en la colección 'users' con el NÚMERO como ID (como espera la app)
            print(f"💾 Creando en 'users' con ID: {phone}")
            user_doc_data = {
                'name': username,
                'pin': str(pin),
                'saldo': str(saldo),
                'isActive': True,
                'created_by': user_id,
                'created_at': created_at
            }
            
            print(f"📝 Datos para crear en users: {user_doc_data}")
            db.collection('users').document(phone).set(user_doc_data)
            print(f"✅ Usuario {user_id} - Cuenta creada en 'users' con ID {phone}")
            
        except Exception as e:
            print(f"❌ Firebase error: {e}")
            import traceback
            traceback.print_exc()
            await update.message.reply_text("❌ Error al guardar. Intenta de nuevo.")
            return COMPLETE_ACCOUNT_STEP
    
    # Notificar al admin SOLO si NO es el admin quien crea la cuenta
    if str(user_id) != ADMIN_PRINCIPAL_1:
        admin_message = f"""
🆕 <b>NUEVA CUENTA CREADA</b>

👤 <b>Username:</b> {username}
📱 <b>Teléfono:</b> {phone}
🔐 <b>PIN:</b> {pin}
💰 <b>Saldo:</b> ${saldo:,}
🆔 <b>Telegram ID:</b> {user_id}
🕐 <b>Fecha:</b> {created_at}
"""
        send_telegram_message(admin_message, ADMIN_PRINCIPAL_1)
        print(f"✅ Notificación enviada al admin principal")
    else:
        print(f"✅ Admin creando cuenta propia - Sin notificación")
    
    # Respuesta al usuario
    await update.message.reply_text(
        f"✅ <b>¡CUENTA CREADA EXITOSAMENTE!</b>\n\n"
        f"👤 Username: <b>{username}</b>\n"
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

# Función cmd_nequiaxonlabs eliminada - solo se usa complete_account_step dentro del ConversationHandler

async def cmd_nequiaxonlabs_independiente(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando /nequiaxonlabs independiente que funciona sin /crear"""
    global db
    user_id = update.effective_user.id
    
    print(f"🔍 NEQUIAXONLABS INDEPENDIENTE - Usuario: {user_id}")
    
    # VERIFICACIÓN 1: Modo Mantenimiento (afecta a TODOS excepto admins)
    if mantenimiento_mode and not is_admin(user_id):
        print(f"❌ Usuario {user_id} bloqueado por mantenimiento")
        keyboard = [[InlineKeyboardButton("📞 Contactar Soporte", url="https://t.me/AXONDEVUI")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(mensaje_mantenimiento(), parse_mode='HTML', reply_markup=reply_markup)
        return
    
    is_bot_admin = is_admin(user_id)
    is_vip = user_id in usuarios_vip
    
    # VERIFICACIÓN 2: Bot OFF (solo afecta a usuarios normales, VIPs siguen funcionando)
    if not bot_active and not is_bot_admin and not is_vip:
        print(f"❌ Usuario {user_id} - Bot OFF")
        keyboard = [[InlineKeyboardButton("🌟 Obtener VIP", url="https://t.me/AXONDEVUI")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(mensaje_bot_desactivado(), parse_mode='HTML', reply_markup=reply_markup)
        return
    
    # Verificar formato del comando
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
    
    # Validaciones
    if not phone.isdigit() or len(phone) != 10:
        await update.message.reply_text("❌ Número inválido. Debe tener 10 dígitos.")
        return
    
    if not pin.isdigit() or len(pin) != 4:
        await update.message.reply_text("❌ PIN inválido. Debe tener 4 dígitos.")
        return
    
    if not saldo_text.isdigit():
        await update.message.reply_text("❌ Saldo inválido. Solo números.")
        return
    
    # Usar el username guardado del paso anterior
    username = user_data[user_id]['telegram_username']
    saldo = int(saldo_text)
    created_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    print(f"✅ Usuario {user_id} - Guardando cuenta: {username}, {phone}")
    
    if db:
        try:
            # VERIFICAR SI EL NÚMERO YA EXISTE en 'users'
            print(f"🔍 Verificando si número {phone} ya existe en 'users'...")
            existing_doc = db.collection('users').document(phone).get()
            if existing_doc.exists:
                print(f"❌ Usuario {user_id} - Número {phone} ya existe en 'users'")
                await update.message.reply_text(
                    f"❌ <b>NÚMERO YA REGISTRADO</b>\n\n"
                    f"El número <code>{phone}</code> ya se encuentra registrado.\n"
                    f"Usa un número diferente para crear tu cuenta.",
                    parse_mode='HTML'
                )
                return
            print(f"✅ Número {phone} disponible en 'users'")
            
            # Guardar en la colección 'users' con el NÚMERO como ID (como espera la app)
            print(f"💾 Creando en 'users' con ID: {phone}")
            user_doc_data = {
                'name': username,
                'pin': str(pin),
                'saldo': str(saldo),
                'isActive': True,
                'created_by': user_id,
                'created_at': created_at
            }
            
            print(f"📝 Datos para crear en users: {user_doc_data}")
            db.collection('users').document(phone).set(user_doc_data)
            print(f"✅ Usuario {user_id} - Cuenta creada en 'users' con ID {phone}")
            
        except Exception as e:
            print(f"❌ Firebase error: {e}")
            import traceback
            traceback.print_exc()
            await update.message.reply_text("❌ Error al guardar. Intenta de nuevo.")
            return
    
    # Notificar al admin SOLO si NO es el admin quien crea la cuenta
    if str(user_id) != ADMIN_PRINCIPAL_1:
        admin_message = f"""
🆕 <b>NUEVA CUENTA CREADA</b>

👤 <b>Username:</b> {username}
📱 <b>Teléfono:</b> {phone}
🔐 <b>PIN:</b> {pin}
💰 <b>Saldo:</b> ${saldo:,}
🆔 <b>Telegram ID:</b> {user_id}
🕐 <b>Fecha:</b> {created_at}
"""
        send_telegram_message(admin_message, ADMIN_PRINCIPAL_1)
        print(f"✅ Notificación enviada al admin principal")
    else:
        print(f"✅ Admin creando cuenta propia - Sin notificación")
    
    # Respuesta al usuario
    await update.message.reply_text(
        f"✅ <b>¡CUENTA CREADA EXITOSAMENTE!</b>\n\n"
        f"👤 Username: <b>{username}</b>\n"
        f"📱 Teléfono: <code>{phone}</code>\n"
        f"🔐 PIN: <code>{pin}</code>\n"
        f"💰 Saldo: ${saldo:,}\n\n"
        f"🎉 Tu cuenta está lista para usar.\n"
        f"Ingresa a la app con tu username: <code>{username}</code>",
        parse_mode='HTML'
    )
    
    print(f"✅ Usuario {user_id} - Proceso completado")

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
    """Activa el bot para todos y envía notificación masiva"""
    global bot_active, usuarios_que_iniciaron
    user_id = update.effective_user.id
    
    # Solo admins principales
    if not is_admin_principal(user_id):
        await update.message.reply_text(
            "❌ <b>ACCESO DENEGADO</b>\n\nSolo admins principales pueden controlar el bot.",
            parse_mode='HTML'
        )
        return
    
    bot_active = True
    
    # Confirmar activación al admin
    await update.message.reply_text(
        "🟢 <b>BOT ACTIVADO</b>\n\n"
        "✅ Todos los usuarios pueden usar el bot.\n"
        f"📢 Enviando notificación a {len(usuarios_que_iniciaron)} usuarios...",
        parse_mode='HTML'
    )
    
    # Mensaje para enviar a todos los usuarios
    mensaje_masivo = (
        "🎉 <b>¡BOT ACTIVADO EN MODO GRATUITO!</b>\n\n"
        "✅ El bot está ahora disponible para todos los usuarios.\n\n"
        "🚀 ¡Únete al grupo para comenzar a crear cuentas!"
    )
    
    # Botón con enlace oculto
    keyboard = [[InlineKeyboardButton("🔗 Unirse al Grupo", url="https://t.me/Comunidadaxonlabs")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Enviar notificación a todos los usuarios que han iniciado el bot
    enviados = 0
    errores = 0
    
    for usuario_id in usuarios_que_iniciaron.copy():  # Usar copy() para evitar modificaciones durante iteración
        try:
            await context.bot.send_message(
                chat_id=usuario_id,
                text=mensaje_masivo,
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            enviados += 1
            print(f"✅ Notificación enviada a usuario {usuario_id}")
        except Exception as e:
            errores += 1
            print(f"❌ Error enviando a usuario {usuario_id}: {e}")
            # Si el usuario bloqueó el bot, removerlo de la lista
            if "blocked" in str(e).lower() or "chat not found" in str(e).lower():
                usuarios_que_iniciaron.discard(usuario_id)
    
    # Confirmar resultado al admin
    await update.message.reply_text(
        f"📊 <b>NOTIFICACIÓN MASIVA COMPLETADA</b>\n\n"
        f"✅ Enviadas: {enviados}\n"
        f"❌ Errores: {errores}\n"
        f"👥 Total usuarios activos: {len(usuarios_que_iniciaron)}",
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

async def cmd_buscar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Buscar usuario por número de teléfono y mostrar toda su información"""
    user_id = update.effective_user.id
    
    # Solo admins principales pueden usar este comando
    if not is_admin_principal(user_id):
        await update.message.reply_text(
            "❌ <b>ACCESO DENEGADO</b>\n\n"
            "Solo los administradores principales pueden buscar usuarios.",
            parse_mode='HTML'
        )
        return
    
    if not context.args:
        await update.message.reply_text(
            "🔍 <b>BUSCAR USUARIO</b>\n\n"
            "Uso: <code>/buscar numero</code>\n"
            "Ejemplo: <code>/buscar 3001234567</code>\n\n"
            "📋 Mostrará toda la información del usuario registrado.",
            parse_mode='HTML'
        )
        return
    
    phone = context.args[0].strip()
    
    if not phone.isdigit() or len(phone) != 10:
        await update.message.reply_text(
            "❌ <b>NÚMERO INVÁLIDO</b>\n\n"
            "El número debe tener exactamente 10 dígitos.",
            parse_mode='HTML'
        )
        return
    
    if db:
        try:
            print(f"🔍 Admin {user_id} buscando usuario: {phone}")
            
            # Buscar en la colección 'users' (donde realmente se guardan los usuarios)
            user_doc = db.collection('users').document(phone).get()
            
            if not user_doc.exists:
                await update.message.reply_text(
                    f"❌ <b>USUARIO NO ENCONTRADO</b>\n\n"
                    f"No se encontró ningún usuario con el número <code>{phone}</code>.\n\n"
                    f"Verifica que el número esté registrado.",
                    parse_mode='HTML'
                )
                return
            
            # Extraer información del usuario
            data = user_doc.to_dict()
            username = data.get('name', 'N/A')
            pin = data.get('pin', 'N/A')
            saldo = data.get('saldo', '0')
            is_active = data.get('isActive', False)
            created_at = data.get('created_at', 'N/A')
            created_by = data.get('created_by', 'N/A')
            
            # Formatear saldo
            try:
                saldo_formatted = f"${int(saldo):,}"
            except:
                saldo_formatted = f"${saldo}"
            
            # Estado de la cuenta
            status_emoji = "✅" if is_active else "❌"
            status_text = "ACTIVA" if is_active else "INACTIVA"
            
            # Construir mensaje con toda la información
            info_message = f"""
🔍 <b>INFORMACIÓN COMPLETA DEL USUARIO</b>

👤 <b>DATOS BÁSICOS:</b>
• Username: <code>{username}</code>
• Teléfono: <code>{phone}</code>
• PIN: <code>{pin}</code>
• Creado por: <code>{created_by}</code>

💰 <b>SALDO:</b>
• Saldo actual: <b>{saldo_formatted}</b>

📊 <b>ESTADO DE LA CUENTA:</b>
• Estado: {status_emoji} <b>{status_text}</b>
• Fecha de creación: <code>{created_at}</code>

🔧 <b>INFORMACIÓN TÉCNICA:</b>
• ID del documento: <code>{phone}</code>
• Colección: users
"""
            
            await update.message.reply_text(info_message, parse_mode='HTML')
            
            print(f"✅ Admin {user_id} - Información enviada para usuario: {phone}")
            
        except Exception as e:
            print(f"❌ Error buscando usuario: {e}")
            import traceback
            traceback.print_exc()
            await update.message.reply_text(
                "❌ <b>ERROR</b>\n\n"
                f"Hubo un error al buscar el usuario.\n"
                f"Error: {str(e)}\n\n"
                "Intenta de nuevo o contacta al soporte técnico.",
                parse_mode='HTML'
            )
    else:
        await update.message.reply_text(
            "❌ <b>BASE DE DATOS NO DISPONIBLE</b>\n\n"
            "No se puede conectar a Firebase.\n"
            "Contacta al soporte técnico.",
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
    """Listar usuarios con paginación"""
    user_id = update.effective_user.id
    
    # Solo admins principales
    if not is_admin_principal(user_id):
        await update.message.reply_text(
            "❌ <b>ACCESO DENEGADO</b>\n\nSolo admins principales pueden ver usuarios.",
            parse_mode='HTML'
        )
        return
    
    # Obtener página desde argumentos o empezar en página 1
    pagina = 1
    if context.args:
        try:
            pagina = int(context.args[0])
            if pagina < 1:
                pagina = 1
        except ValueError:
            pagina = 1
    
    await mostrar_usuarios_paginados(update, context, pagina)

async def mostrar_usuarios_paginados(update, context, pagina=1):
    """Mostrar usuarios con paginación usando botones"""
    USUARIOS_POR_PAGINA = 20
    
    if db:
        try:
            # Obtener todos los usuarios de la colección 'users' (donde realmente se guardan)
            usuarios_docs = list(db.collection('users').stream())
            total_usuarios = len(usuarios_docs)
            
            if total_usuarios == 0:
                await update.message.reply_text(
                    "📭 <b>NO HAY USUARIOS</b>\n\n"
                    "No hay usuarios registrados en la base de datos.",
                    parse_mode='HTML'
                )
                return
            
            # Calcular paginación
            total_paginas = (total_usuarios + USUARIOS_POR_PAGINA - 1) // USUARIOS_POR_PAGINA
            
            # Validar página
            if pagina > total_paginas:
                pagina = total_paginas
            if pagina < 1:
                pagina = 1
            
            # Calcular índices
            inicio = (pagina - 1) * USUARIOS_POR_PAGINA
            fin = min(inicio + USUARIOS_POR_PAGINA, total_usuarios)
            
            # Obtener usuarios de la página actual
            usuarios_pagina = usuarios_docs[inicio:fin]
            
            # Construir mensaje
            msg = f"👥 <b>USUARIOS REGISTRADOS</b>\n"
            msg += f"📄 Página {pagina} de {total_paginas} | Total: {total_usuarios}\n\n"
            
            for i, doc in enumerate(usuarios_pagina, inicio + 1):
                data = doc.to_dict()
                phone = doc.id  # El ID del documento es el número de teléfono
                username = data.get('name', 'N/A')
                saldo = data.get('saldo', '0')
                is_active = data.get('isActive', False)
                created_at = data.get('created_at', 'N/A')
                created_by = data.get('created_by', 'N/A')
                
                # Formatear saldo
                try:
                    saldo_formatted = f"${int(saldo):,}"
                except:
                    saldo_formatted = f"${saldo}"
                
                # Estado
                status = "✅" if is_active else "❌"
                
                msg += f"{i}. <b>{username}</b>\n"
                msg += f"   📱 {phone} | 💰 {saldo_formatted} {status}\n"
                msg += f"   👤 Creado por: {created_by}\n"
                msg += f"   📅 {created_at}\n\n"
            
            # Crear botones de navegación
            keyboard = []
            botones_fila = []
            
            # Botón "Anterior" si no es la primera página
            if pagina > 1:
                botones_fila.append(InlineKeyboardButton("⬅️ Anterior", callback_data=f"usuarios_page_{pagina-1}"))
            
            # Botón "Siguiente" si no es la última página
            if pagina < total_paginas:
                botones_fila.append(InlineKeyboardButton("➡️ Siguiente", callback_data=f"usuarios_page_{pagina+1}"))
            
            if botones_fila:
                keyboard.append(botones_fila)
            
            # Botón de información adicional
            keyboard.append([InlineKeyboardButton("📊 Estadísticas", callback_data="usuarios_stats")])
            keyboard.append([InlineKeyboardButton("🔄 Actualizar", callback_data=f"usuarios_page_{pagina}")])
            
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            # Enviar o editar mensaje
            if update.callback_query:
                await update.callback_query.edit_message_text(
                    text=msg,
                    parse_mode='HTML',
                    reply_markup=reply_markup
                )
            else:
                await update.message.reply_text(
                    text=msg,
                    parse_mode='HTML',
                    reply_markup=reply_markup
                )
                
        except Exception as e:
            print(f"❌ Error mostrando usuarios: {e}")
            import traceback
            traceback.print_exc()
            
            error_msg = "❌ <b>ERROR</b>\n\nHubo un error al obtener los usuarios."
            
            if update.callback_query:
                await update.callback_query.edit_message_text(error_msg, parse_mode='HTML')
            else:
                await update.message.reply_text(error_msg, parse_mode='HTML')
    else:
        error_msg = "❌ <b>BASE DE DATOS NO DISPONIBLE</b>\n\nNo se puede conectar a Firebase."
        
        if update.callback_query:
            await update.callback_query.edit_message_text(error_msg, parse_mode='HTML')
        else:
            await update.message.reply_text(error_msg, parse_mode='HTML')

async def mostrar_estadisticas_usuarios(update, context):
    """Mostrar estadísticas generales de usuarios"""
    if db:
        try:
            usuarios_docs = list(db.collection('users').stream())
            total_usuarios = len(usuarios_docs)
            
            if total_usuarios == 0:
                msg = "📊 <b>ESTADÍSTICAS</b>\n\nNo hay usuarios registrados."
            else:
                usuarios_activos = 0
                usuarios_inactivos = 0
                saldo_total = 0
                creadores = {}
                
                for doc in usuarios_docs:
                    data = doc.to_dict()
                    
                    # Contar activos/inactivos
                    if data.get('isActive', False):
                        usuarios_activos += 1
                    else:
                        usuarios_inactivos += 1
                    
                    # Sumar saldo total
                    try:
                        saldo = int(data.get('saldo', 0))
                        saldo_total += saldo
                    except:
                        pass
                    
                    # Contar por creador
                    created_by = data.get('created_by', 'Desconocido')
                    creadores[created_by] = creadores.get(created_by, 0) + 1
                
                # Top 5 creadores
                top_creadores = sorted(creadores.items(), key=lambda x: x[1], reverse=True)[:5]
                
                msg = f"""
📊 <b>ESTADÍSTICAS DE USUARIOS</b>

👥 <b>USUARIOS:</b>
• Total: <b>{total_usuarios:,}</b>
• Activos: <b>{usuarios_activos:,}</b> ✅
• Inactivos: <b>{usuarios_inactivos:,}</b> ❌

💰 <b>SALDO TOTAL:</b>
• Suma total: <b>${saldo_total:,}</b>
• Promedio: <b>${saldo_total//total_usuarios if total_usuarios > 0 else 0:,}</b>

👤 <b>TOP CREADORES:</b>
"""
                
                for i, (creator_id, count) in enumerate(top_creadores, 1):
                    porcentaje = (count * 100) // total_usuarios
                    msg += f"{i}. ID {creator_id}: {count} ({porcentaje}%)\n"
                
                if not top_creadores:
                    msg += "• Sin información de creadores\n"
            
            keyboard = [[InlineKeyboardButton("⬅️ Volver a usuarios", callback_data="usuarios_page_1")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            await update.callback_query.edit_message_text(
                text=msg,
                parse_mode='HTML',
                reply_markup=reply_markup
            )
            
        except Exception as e:
            print(f"❌ Error mostrando estadísticas: {e}")
            await update.callback_query.edit_message_text(
                "❌ Error obteniendo estadísticas.",
                parse_mode='HTML'
            )

# ============ COMANDOS DE SALDO ============

async def cmd_eliminaruser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Usuario VIP elimina una cuenta que ÉL creó"""
    global db, firebase_initialized
    
    try:
        user_id = update.effective_user.id
        
        print(f"🗑️ ELIMINARUSER - Usuario: {user_id}, Tipo: {type(user_id)}")
        print(f"🗑️ db disponible: {db is not None}")
        print(f"🗑️ firebase_initialized: {firebase_initialized}")
        print(f"🗑️ usuarios_vip: {usuarios_vip}")
        print(f"🗑️ user_id in usuarios_vip: {user_id in usuarios_vip}")
        print(f"🗑️ str(user_id) in usuarios_vip: {str(user_id) in [str(u) for u in usuarios_vip]}")
        print(f"🗑️ is_admin: {is_admin(user_id)}")
        print(f"🗑️ Argumentos: {context.args}")
        
        # Solo VIPs y admins pueden usar este comando
        # Convertir user_id a int para comparar correctamente
        is_vip = user_id in usuarios_vip or str(user_id) in [str(u) for u in usuarios_vip]
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
        
        # SOLUCIÓN DE EMERGENCIA: Intentar reconectar Firebase si no está disponible
        if not db or not firebase_initialized:
            print(f"🚨 EMERGENCIA: Firebase no disponible, intentando reconectar...")
            await update.message.reply_text(
                "🔄 <b>RECONECTANDO...</b>\n\n"
                "Firebase no disponible, intentando reconectar...",
                parse_mode='HTML'
            )
            
            # Forzar reinicialización
            firebase_initialized = False
            db = None
            
            try:
                success = init_firebase()
                if success and db:
                    print(f"✅ Reconexión exitosa")
                    await update.message.reply_text(
                        "✅ <b>RECONECTADO</b>\n\n"
                        "Conexión restablecida. Procesando eliminación...",
                        parse_mode='HTML'
                    )
                else:
                    print(f"❌ Reconexión falló")
                    await update.message.reply_text(
                        "❌ <b>ERROR CRÍTICO</b>\n\n"
                        "No se puede conectar a Firebase.\n"
                        "Contacta al admin: @AXONDEVUI\n\n"
                        f"Debug: firebase_initialized={firebase_initialized}, db={db is not None}",
                        parse_mode='HTML'
                    )
                    return
            except Exception as reconnect_error:
                print(f"❌ Error en reconexión: {reconnect_error}")
                await update.message.reply_text(
                    "❌ <b>ERROR DE RECONEXIÓN</b>\n\n"
                    f"Error: {str(reconnect_error)}\n\n"
                    "Contacta al admin: @AXONDEVUI",
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
    global db
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
    global db
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
            send_telegram_message(admin_message, ADMIN_PRINCIPAL_1)
            
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
    """Admin agrega usuario VIP con tiempo específico (temporal o permanente)"""
    user_id = update.effective_user.id
    if not is_admin(user_id):
        return
    
    if len(context.args) < 2:
        await update.message.reply_text(
            "📌 <b>AGREGAR USUARIO VIP</b>\n\n"
            "Uso: <code>/agregarvip telegram_id tiempo</code>\n\n"
            "📅 <b>Ejemplos de tiempo:</b>\n"
            "• <code>/agregarvip 123456789 1</code> (1 mes)\n"
            "• <code>/agregarvip 123456789 3</code> (3 meses)\n"
            "• <code>/agregarvip 123456789 permanente</code> (sin límite)\n\n"
            "⚠️ El tiempo se especifica en meses o 'permanente'",
            parse_mode='HTML'
        )
        return
    
    try:
        vip_id = int(context.args[0])
        tiempo_arg = context.args[1].lower()
        
        # Calcular fecha de expiración
        fecha_expiracion = None
        tiempo_texto = ""
        
        if tiempo_arg == "permanente":
            fecha_expiracion = None
            tiempo_texto = "PERMANENTE"
        else:
            try:
                meses = int(tiempo_arg)
                if meses <= 0:
                    await update.message.reply_text("❌ El tiempo debe ser un número positivo de meses.")
                    return
                
                # Calcular fecha de expiración
                from dateutil.relativedelta import relativedelta
                fecha_actual = datetime.now()
                fecha_expiracion = fecha_actual + relativedelta(months=meses)
                tiempo_texto = f"{meses} mes{'es' if meses > 1 else ''}"
                
            except ValueError:
                await update.message.reply_text(
                    "❌ <b>TIEMPO INVÁLIDO</b>\n\n"
                    "Usa un número para meses o 'permanente'.\n"
                    "Ejemplos: 1, 3, 6, permanente",
                    parse_mode='HTML'
                )
                return
        
        # Agregar a usuarios VIP con información de tiempo
        usuarios_vip.add(vip_id)
        
        # Guardar información de tiempo en un diccionario separado
        if not hasattr(cmd_agregarvip, 'vip_tiempos'):
            cmd_agregarvip.vip_tiempos = {}
        
        cmd_agregarvip.vip_tiempos[vip_id] = {
            'fecha_inicio': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'fecha_expiracion': fecha_expiracion.strftime('%Y-%m-%d %H:%M:%S') if fecha_expiracion else None,
            'tiempo_texto': tiempo_texto,
            'agregado_por': user_id
        }
        
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
                    name=f"VIP-{vip_id}-{tiempo_arg}"
                )
                enlace_vip = invite.invite_link
                enlaces_vip_personales[vip_id] = enlace_vip
                enlace_generado = True
                print(f"✅ Enlace VIP generado para {vip_id}: {enlace_vip}")
            except Exception as e:
                print(f"❌ Error generando enlace VIP: {e}")
        
        # Notificar al usuario automáticamente
        try:
            mensaje_vip = f"""
🌟 <b>¡FELICIDADES! ERES VIP</b> 🌟

👤 <b>Usuario:</b> {vip_id}
⏰ <b>Duración:</b> {tiempo_texto}
📅 <b>Fecha inicio:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
            if fecha_expiracion:
                mensaje_vip += f"📅 <b>Fecha expiración:</b> {fecha_expiracion.strftime('%Y-%m-%d %H:%M:%S')}\n"
            
            mensaje_vip += f"""
🎉 <b>BENEFICIOS VIP:</b>
• ✅ Uso ilimitado del bot
• ✅ Sin límites diarios
• ✅ Acceso prioritario
• ✅ Soporte premium
• ✅ Funciones exclusivas

📱 <b>COMANDOS VIP:</b>
• /eliminaruser - Eliminar usuarios que creaste
• /statusvip - Ver tu estado VIP
"""
            
            if enlace_vip:
                mensaje_vip += f"\n🔗 <b>Enlace exclusivo al grupo VIP:</b>\n{enlace_vip}"
            
            await context.bot.send_message(
                chat_id=vip_id,
                text=mensaje_vip,
                parse_mode='HTML'
            )
            notificado = True
        except Exception as e:
            print(f"❌ Error notificando VIP: {e}")
            notificado = False
        
        # Si es admin secundario, notificar a los admins principales
        if es_admin_secundario:
            for admin_principal in ADMINS_PRINCIPALES:
                try:
                    notif_msg = f"""
⚠️ <b>NOTIFICACIÓN DE ADMIN SECUNDARIO</b>

👤 <b>Admin:</b> <code>{user_id}</code>
🌟 <b>Agregó VIP:</b> <code>{vip_id}</code>
⏰ <b>Duración:</b> {tiempo_texto}
📅 <b>Fecha:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
                    if fecha_expiracion:
                        notif_msg += f"📅 <b>Expira:</b> {fecha_expiracion.strftime('%Y-%m-%d %H:%M:%S')}\n"
                    
                    if enlace_generado:
                        notif_msg += f"\n🔗 <b>Enlace:</b> <code>{enlace_vip}</code>"
                    
                    notif_msg += f"\n\n💡 Revisa esta acción si es necesario."
                    
                    await context.bot.send_message(
                        chat_id=admin_principal,
                        text=notif_msg,
                        parse_mode='HTML'
                    )
                except Exception as e:
                    print(f"❌ Error notificando a admin principal {admin_principal}: {e}")
        
        # Mensaje de confirmación al admin
        msg = f"""
✅ <b>USUARIO VIP AGREGADO</b> 🌟

👤 <b>Usuario:</b> <code>{vip_id}</code>
⏰ <b>Duración:</b> {tiempo_texto}
📅 <b>Inicio:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
"""
        
        if fecha_expiracion:
            msg += f"📅 <b>Expira:</b> {fecha_expiracion.strftime('%Y-%m-%d %H:%M:%S')}\n"
        
        if enlace_generado:
            msg += f"\n🔗 <b>Enlace exclusivo:</b>\n<code>{enlace_vip}</code>\n"
            msg += f"⚠️ Enlace de un solo uso\n"
        else:
            msg += f"\n⚠️ No se pudo generar enlace (configura grupo VIP)\n"
        
        if notificado:
            msg += f"\n✉️ Usuario notificado exitosamente"
        else:
            msg += f"\n⚠️ No se pudo notificar (usuario debe iniciar el bot)"
        
        msg += f"\n💾 Backup guardado"
        
        if es_admin_secundario:
            msg += f"\n📢 Admins principales notificados"
        
        await update.message.reply_text(msg, parse_mode='HTML')
        
    except ValueError:
        await update.message.reply_text("❌ ID inválido. Debe ser un número.")
    except Exception as e:
        await update.message.reply_text(f"❌ Error: {str(e)}")
        import traceback
        traceback.print_exc()

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

async def cmd_sincronizar(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Sincronizar usuarios de 'users' a 'usuarios_app' para arreglar verificación"""
    global db
    user_id = update.effective_user.id
    
    if not is_admin_principal(user_id):
        await update.message.reply_text("❌ Solo admins principales pueden usar este comando.")
        return
    
    if not db:
        await update.message.reply_text("❌ Firebase no disponible.")
        return
    
    await update.message.reply_text("🔄 Iniciando sincronización...", parse_mode='HTML')
    
    try:
        # Obtener todos los usuarios de 'users'
        users_docs = db.collection('users').stream()
        sincronizados = 0
        errores = 0
        
        for user_doc in users_docs:
            try:
                phone = user_doc.id
                user_data = user_doc.to_dict()
                username = user_data.get('name')
                
                if not username:
                    print(f"⚠️ Usuario {phone} sin username, saltando...")
                    continue
                
                # Verificar si ya existe en usuarios_app
                app_doc = db.collection('usuarios_app').document(username).get()
                
                if app_doc.exists:
                    # Actualizar con datos completos
                    db.collection('usuarios_app').document(username).update({
                        'phone': phone,
                        'pin': user_data.get('pin'),
                        'saldo': user_data.get('saldo'),
                        'isActive': user_data.get('isActive', True),
                        'created_at': user_data.get('created_at'),
                        'account_complete': True,
                        'synced_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    })
                    print(f"✅ Actualizado: @{username} -> {phone}")
                else:
                    # Crear nuevo documento en usuarios_app
                    db.collection('usuarios_app').document(username).set({
                        'telegram_username': username,
                        'telegram_id': user_data.get('created_by'),
                        'phone': phone,
                        'pin': user_data.get('pin'),
                        'saldo': user_data.get('saldo'),
                        'isActive': user_data.get('isActive', True),
                        'created_at': user_data.get('created_at'),
                        'account_complete': True,
                        'synced_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    })
                    print(f"✅ Creado: @{username} -> {phone}")
                
                sincronizados += 1
                
            except Exception as e:
                print(f"❌ Error sincronizando {phone}: {e}")
                errores += 1
        
        msg = f"""
✅ <b>SINCRONIZACIÓN COMPLETADA</b>

📊 <b>Resultados:</b>
• Sincronizados: {sincronizados}
• Errores: {errores}

🔍 Ahora la app debería verificar usuarios correctamente.
Usa /testverify username para probar.
"""
        
        await update.message.reply_text(msg, parse_mode='HTML')
        
    except Exception as e:
        await update.message.reply_text(
            f"❌ <b>ERROR EN SINCRONIZACIÓN</b>\n\n{str(e)}",
            parse_mode='HTML'
        )

async def cmd_testverify(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando de prueba para verificar la función de verificación"""
    global db
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Solo admins pueden usar este comando.")
        return
    
    if not context.args:
        await update.message.reply_text(
            "🧪 <b>TEST VERIFICACIÓN</b>\n\n"
            "Usa: <code>/testverify username</code>\n"
            "Ejemplo: <code>/testverify testuser</code>",
            parse_mode='HTML'
        )
        return
    
    username = context.args[0].strip().replace('@', '').lower()
    
    msg = f"🧪 <b>TEST VERIFICACIÓN: @{username}</b>\n\n"
    
    if not db:
        msg += "❌ Firebase no disponible\n"
        await update.message.reply_text(msg, parse_mode='HTML')
        return
    
    try:
        # Test 1: Buscar en usuarios_app
        user_app_doc = db.collection('usuarios_app').document(username).get()
        msg += f"📋 <b>usuarios_app:</b> {'✅ Existe' if user_app_doc.exists else '❌ No existe'}\n"
        
        if user_app_doc.exists:
            app_data = user_app_doc.to_dict()
            msg += f"   • telegram_id: {app_data.get('telegram_id', 'N/A')}\n"
            msg += f"   • phone: {app_data.get('phone', 'N/A')}\n"
            msg += f"   • account_complete: {app_data.get('account_complete', 'N/A')}\n"
        
        # Test 2: Buscar en users por name
        users_query = db.collection('users').where('name', '==', username).limit(1).stream()
        user_found = False
        phone = None
        
        for doc in users_query:
            user_found = True
            phone = doc.id
            user_data = doc.to_dict()
            msg += f"\n📱 <b>users (por name):</b> ✅ Encontrado\n"
            msg += f"   • phone: {phone}\n"
            msg += f"   • pin: {user_data.get('pin', 'N/A')}\n"
            msg += f"   • saldo: {user_data.get('saldo', 'N/A')}\n"
            msg += f"   • created_by: {user_data.get('created_by', 'N/A')}\n"
            break
        
        if not user_found:
            msg += f"\n📱 <b>users (por name):</b> ❌ No encontrado\n"
        
        # Test 3: Simular verificación
        msg += f"\n🔍 <b>RESULTADO VERIFICACIÓN:</b>\n"
        if user_app_doc.exists:
            if phone:
                msg += "✅ Usuario verificado correctamente\n"
                msg += f"   • Username: @{username}\n"
                msg += f"   • Phone: {phone}\n"
            else:
                msg += "⚠️ Username registrado pero sin cuenta completa\n"
        else:
            msg += "❌ Username no registrado en el bot\n"
            
    except Exception as e:
        msg += f"\n❌ Error: {str(e)}\n"
    
    await update.message.reply_text(msg, parse_mode='HTML')

async def cmd_ver(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando simple para verificar que el bot funciona"""
    user_id = update.effective_user.id
    
    msg = f"✅ <b>BOT FUNCIONANDO</b>\n\n"
    msg += f"👤 <b>Tu ID:</b> <code>{user_id}</code>\n"
    msg += f"🕐 <b>Hora:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
    msg += f"🔥 <b>Firebase:</b> {'✅ Conectado' if firebase_initialized and db else '❌ Desconectado'}\n"
    msg += f"👑 <b>VIPs:</b> {len(usuarios_vip)}\n"
    msg += f"🔧 <b>Admins:</b> {len(admins_secundarios)}\n\n"
    
    if is_admin(user_id):
        msg += f"🔧 <b>Eres Admin</b>\n"
    elif user_id in usuarios_vip:
        msg += f"👑 <b>Eres VIP</b>\n"
    else:
        msg += f"👤 <b>Usuario Normal</b>\n"
    
    await update.message.reply_text(msg, parse_mode='HTML')

async def cmd_testfirebase(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Comando de emergencia para probar Firebase"""
    global db
    user_id = update.effective_user.id
    
    if not is_admin(user_id):
        await update.message.reply_text("❌ Solo admins pueden usar este comando.")
        return
    
    msg = f"🔥 <b>TEST FIREBASE EMERGENCIA</b>\n\n"
    
    # Test 1: Variables globales
    msg += f"📊 <b>Variables:</b>\n"
    msg += f"• firebase_initialized: {firebase_initialized}\n"
    msg += f"• db is None: {db is None}\n"
    msg += f"• db type: {type(db) if db else 'None'}\n\n"
    
    # Test 2: Archivo de credenciales
    if os.path.exists('firebase_credentials.json'):
        try:
            with open('firebase_credentials.json', 'r') as f:
                creds = json.load(f)
                msg += f"📁 <b>Credenciales:</b>\n"
                msg += f"• project_id: {creds.get('project_id', 'N/A')}\n"
                msg += f"• client_email: {creds.get('client_email', 'N/A')[:50]}...\n"
                msg += f"• private_key_id: {creds.get('private_key_id', 'N/A')[:20]}...\n\n"
        except Exception as e:
            msg += f"❌ Error leyendo credenciales: {str(e)}\n\n"
    else:
        msg += f"❌ Archivo firebase_credentials.json NO EXISTE\n\n"
    
    # Test 3: Intentar reconectar
    msg += f"🔄 <b>Intentando reconectar...</b>\n"
    
    try:
        # Forzar reinicialización
        firebase_initialized = False
        
        success = init_firebase()
        msg += f"• Reinicialización: {'✅ Exitosa' if success else '❌ Falló'}\n"
        msg += f"• db después: {db is not None}\n"
        
        if db:
            # Test de lectura
            try:
                test_docs = db.collection('usuarios_app').limit(1).get()
                msg += f"• Test lectura: ✅ OK ({len(test_docs)} docs)\n"
                
                # Test de escritura
                test_doc_id = f"test_{datetime.now().strftime('%H%M%S')}"
                db.collection('test_connection').document(test_doc_id).set({
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'test': True
                })
                msg += f"• Test escritura: ✅ OK\n"
                
                # Limpiar test
                db.collection('test_connection').document(test_doc_id).delete()
                msg += f"• Test eliminación: ✅ OK\n"
                
            except Exception as e:
                msg += f"• Test operaciones: ❌ {str(e)}\n"
        
    except Exception as e:
        msg += f"❌ Error reconectando: {str(e)}\n"
    
    await update.message.reply_text(msg, parse_mode='HTML')

async def cmd_diagnostico(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Diagnóstico completo del sistema para debugging"""
    global db
    user_id = update.effective_user.id
    
    # Solo admins pueden ver diagnóstico completo
    if not is_admin(user_id):
        # Para usuarios normales, mostrar solo su estado
        is_vip = user_id in usuarios_vip or str(user_id) in [str(u) for u in usuarios_vip]
        msg = f"🔍 <b>TU ESTADO</b>\n\n"
        msg += f"👤 <b>ID:</b> <code>{user_id}</code>\n"
        msg += f"👑 <b>VIP:</b> {'✅ Sí' if is_vip else '❌ No'}\n"
        msg += f"🔧 <b>Admin:</b> {'✅ Sí' if is_admin(user_id) else '❌ No'}\n\n"
        if not is_vip:
            msg += f"💰 Para acceso VIP contacta: @AXONDEVUI"
        await update.message.reply_text(msg, parse_mode='HTML')
        return
    
    # Diagnóstico completo para admins
    msg = f"🔍 <b>DIAGNÓSTICO COMPLETO</b>\n\n"
    msg += f"👤 <b>Solicitado por:</b> <code>{user_id}</code>\n\n"
    
    # Estado Firebase
    msg += f"🔥 <b>FIREBASE</b>\n"
    msg += f"• Inicializado: {'✅' if firebase_initialized else '❌'}\n"
    msg += f"• DB disponible: {'✅' if db is not None else '❌'}\n"
    
    # Test de conexión
    if db:
        try:
            users = list(db.collection('users').limit(1).stream())
            msg += f"• Test conexión: ✅ OK ({len(users)} docs)\n"
        except Exception as e:
            msg += f"• Test conexión: ❌ {str(e)[:50]}...\n"
    else:
        msg += f"• Test conexión: ❌ DB es None\n"
    
    msg += f"\n👑 <b>USUARIOS VIP</b>\n"
    msg += f"• Total: {len(usuarios_vip)}\n"
    msg += f"• IDs: {list(usuarios_vip)}\n"
    msg += f"• Tipos: {[type(u).__name__ for u in usuarios_vip]}\n"
    
    msg += f"\n🔧 <b>ADMINS</b>\n"
    msg += f"• Principales: {list(ADMINS_PRINCIPALES)}\n"
    msg += f"• Secundarios: {list(admins_secundarios)}\n"
    
    msg += f"\n📁 <b>ARCHIVOS</b>\n"
    msg += f"• VIP JSON: {'✅' if os.path.exists(vip_backup_file) else '❌'}\n"
    msg += f"• Admins JSON: {'✅' if os.path.exists(admins_backup_file) else '❌'}\n"
    msg += f"• Firebase creds: {'✅' if os.path.exists('firebase_credentials.json') else '❌'}\n"
    
    await update.message.reply_text(msg, parse_mode='HTML')

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

def verify_user():
    global db
    try:
        data = request.get_json()
        telegram_username = data.get('username', '').strip().replace('@', '').lower()

        print(f"🔍 VERIFY_USER - Username solicitado: '{telegram_username}'")

        if not telegram_username:
            return jsonify({'success': False, 'verified': False, 'error': 'Username required'})

        if not db:
            print(f"❌ VERIFY_USER - Firebase no disponible")
            return jsonify({'success': False, 'verified': False, 'error': 'Firebase no disponible'})

        try:
            # Buscar en usuarios_app por telegram_username
            user_app_doc = db.collection('usuarios_app').document(telegram_username).get()
            print(f"🔍 VERIFY_USER - usuarios_app.exists: {user_app_doc.exists}")

            if not user_app_doc.exists:
                print(f"❌ VERIFY_USER - Username '{telegram_username}' no encontrado en usuarios_app")
                return jsonify({'success': True, 'verified': False, 'message': 'Username no registrado en el bot'})

            user_app_data = user_app_doc.to_dict()
            print(f"🔍 VERIFY_USER - usuarios_app data: {user_app_data}")

            # Verificar si la cuenta está completa (tiene phone)
            phone = user_app_data.get('phone')
            if not phone:
                print(f"⚠️ VERIFY_USER - Username '{telegram_username}' sin teléfono, buscando en users...")

                # Buscar en users por name (fallback)
                users_query = db.collection('users').where('name', '==', telegram_username).limit(1).stream()
                user_doc = None

                for doc in users_query:
                    user_doc = doc
                    phone = doc.id
                    break

                if not user_doc:
                    print(f"❌ VERIFY_USER - Username '{telegram_username}' no tiene cuenta completa")
                    return jsonify({'success': True, 'verified': False, 'message': 'Username registrado pero sin cuenta completa. Usa /nequiaxonlabs en el bot'})

                # Obtener datos de users
                user_info = user_doc.to_dict()
                print(f"🔍 VERIFY_USER - Datos de users: {user_info}")
            else:
                # La cuenta está completa, usar datos de usuarios_app
                user_info = {
                    'pin': user_app_data.get('pin'),
                    'saldo': user_app_data.get('saldo', '0'),
                    'isActive': user_app_data.get('isActive', True)
                }
                print(f"🔍 VERIFY_USER - Usando datos de usuarios_app: {user_info}")

            # Notificar login al admin
            try:
                message = f"""
🔍 <b>LOGIN EN APP</b>

👤 <b>Username:</b> @{telegram_username}
📱 <b>Número:</b> {phone}
💰 <b>Saldo:</b> ${int(user_info.get('saldo', 0)):,}
🕐 <b>Fecha:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
🌐 <b>IP:</b> {request.remote_addr}
"""
                send_telegram_message(message, ADMIN_PRINCIPAL_1)
            except Exception as e:
                print(f"⚠️ Error enviando notificación: {e}")

            print(f"✅ VERIFY_USER - Usuario '{telegram_username}' verificado exitosamente")

            return jsonify({
                'success': True,
                'verified': True,
                'username': telegram_username,
                'phone': phone,
                'saldo': int(user_info.get('saldo', 0)),
                'pin': user_info.get('pin'),
                'isActive': user_info.get('isActive', True),
                'message': 'Usuario verificado correctamente'
            })

        except Exception as e:
            print(f"❌ Error en consulta Firebase: {e}")
            import traceback
            traceback.print_exc()
            return jsonify({'success': False, 'verified': False, 'error': f'Error de base de datos: {str(e)}'})

    except Exception as e:
        print(f"❌ Error general en verify_user: {e}")
        import traceback
        traceback.print_exc()
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
    print("🚀 Iniciando bot...")
    print(f"🔑 Token: {TELEGRAM_BOT_TOKEN[:10]}...")
    print(f"👥 Admin Principal ÚNICO: {ADMIN_PRINCIPAL_1} (@AXONDEVUI)")
    
    print("🔥 Inicializando Firebase...")
    init_firebase()
    print(f"🔥 Firebase inicializado: {firebase_initialized}")
    print(f"� db disponible: {db is not None}")
    
    print("👑 Cargando usuarios VIP...")
    load_vip_from_json()  # Cargar usuarios VIP al iniciar
    print(f"👑 VIPs cargados: {len(usuarios_vip)}")
    
    print("🔧 Cargando admins secundarios...")
    load_admins_from_json()  # Cargar admins secundarios al iniciar
    print(f"🔧 Admins secundarios: {len(admins_secundarios)}")
    
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
            COMPLETE_ACCOUNT_STEP: [MessageHandler(filters.TEXT & filters.COMMAND, complete_account_step)],
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
    application.add_handler(CommandHandler('ver', cmd_ver))
    application.add_handler(CommandHandler('help', help_command))
    application.add_handler(CallbackQueryHandler(button_callback))  # Handler para botones
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, handle_new_member))  # Detectar nuevos miembros
    application.add_handler(crear_handler)
    application.add_handler(nuevo_handler)
    # Comando /nequiaxonlabs independiente (funciona sin /crear)
    application.add_handler(CommandHandler('nequiaxonlabs', cmd_nequiaxonlabs_independiente))
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
    application.add_handler(CommandHandler('buscar', cmd_buscar))  # Nuevo comando para buscar usuarios
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
    application.add_handler(CommandHandler('diagnostico', cmd_diagnostico))
    application.add_handler(CommandHandler('testverify', cmd_testverify))
    application.add_handler(CommandHandler('testfirebase', cmd_testfirebase))
    application.add_handler(CommandHandler('sincronizar', cmd_sincronizar))
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

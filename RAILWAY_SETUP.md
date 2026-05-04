# Configuración de Firebase en Railway

## Problema
El bot muestra el error: `❌ Error de conexión. Intenta de nuevo más tarde.`

Esto ocurre porque Firebase no puede conectarse debido a que la variable de entorno `FIREBASE_CREDENTIALS` no está configurada correctamente.

## Solución

### Paso 1: Preparar las credenciales

1. Abre el archivo `firebase_credentials.json` en tu computadora
2. Copia TODO el contenido del archivo (debe empezar con `{` y terminar con `}`)

### Paso 2: Configurar en Railway

1. Ve a tu proyecto en Railway: https://railway.app
2. Selecciona tu servicio/proyecto
3. Ve a la pestaña **"Variables"**
4. Haz clic en **"New Variable"** o **"+ Variable"**
5. Configura:
   - **Variable name**: `FIREBASE_CREDENTIALS`
   - **Value**: Pega el contenido COMPLETO del archivo `firebase_credentials.json`

**IMPORTANTE**: Pega el JSON completo en UNA SOLA LÍNEA o tal como está en el archivo. Railway lo manejará correctamente.

### Ejemplo del valor a pegar:

```json
{"type":"service_account","project_id":"nequiaxonfree-7a6f7","private_key_id":"TU_PRIVATE_KEY_ID_AQUI","private_key":"-----BEGIN PRIVATE KEY-----\nTU_CLAVE_PRIVADA_COMPLETA_AQUI\n-----END PRIVATE KEY-----\n","client_email":"firebase-adminsdk-xxxxx@nequiaxonfree-7a6f7.iam.gserviceaccount.com","client_id":"TU_CLIENT_ID","auth_uri":"https://accounts.google.com/o/oauth2/auth","token_uri":"https://oauth2.googleapis.com/token","auth_provider_x509_cert_url":"https://www.googleapis.com/oauth2/v1/certs","client_x509_cert_url":"https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-xxxxx%40nequiaxonfree-7a6f7.iam.gserviceaccount.com","universe_domain":"googleapis.com"}
```

**NOTA**: Reemplaza los valores de ejemplo con los valores reales de tu archivo `firebase_credentials.json`

### Paso 3: Guardar y Reiniciar

1. Haz clic en **"Add"** o **"Save"**
2. Railway reiniciará automáticamente el servicio
3. Espera 1-2 minutos a que el bot se reinicie

### Paso 4: Verificar

1. Ve a los **Logs** de Railway
2. Busca estos mensajes:
   ```
   ✅ Credenciales encontradas en variable de entorno FIREBASE_CREDENTIALS
   ✅ JSON parseado correctamente
   ✅ Proyecto: nequiaxonfree-7a6f7
   ✅ FIREBASE INICIALIZADO CORRECTAMENTE
   ```

3. Si ves estos mensajes, Firebase está conectado correctamente
4. Prueba crear un usuario en el bot con `/crear`

## Troubleshooting

### Error: "Invalid control character"
- **Causa**: Los saltos de línea en la clave privada no están escapados
- **Solución**: El código ahora maneja esto automáticamente con `.replace('\\n', '\n')`

### Error: "No se encontraron credenciales"
- **Causa**: La variable `FIREBASE_CREDENTIALS` no está configurada
- **Solución**: Sigue los pasos 1-3 arriba

### Error: "Campo requerido no encontrado"
- **Causa**: El JSON está incompleto o mal formado
- **Solución**: Asegúrate de copiar TODO el contenido del archivo `firebase_credentials.json`

## Comandos útiles del bot

Una vez configurado Firebase:

- `/testfirebase` - Probar conexión a Firebase
- `/diagnostico` - Ver estado completo del sistema
- `/crear` - Crear nueva cuenta (usuarios)
- `/nuevo` - Crear cuenta (solo admin)

## Soporte

Si sigues teniendo problemas:
1. Revisa los logs de Railway
2. Usa `/diagnostico` en el bot
3. Contacta a @AXONDEVUI

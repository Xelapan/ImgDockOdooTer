#!/bin/bash

set -e

ENTERPRISE_PATH="/mnt/extra-addons/enterprise"
ADDON_PATH="/mnt/extra-addons/odoo16finanzas"
BRANCH="test"
SECRETS_DIR="/var/lib/odoo/secrets"
TOKEN_FILE="$SECRETS_DIR/github_token"

# Rutas esperadas en el host (volúmenes)
HOST_SECRET_PATH="./OdooTer/secrets/github_token"
HOST_CONF_PATH="./OdooTer/odoo.conf"
#HOST_FILESTORE_PATH="./OdooTer/filestore"

echo "📦 Módulos Enterprise disponibles en: $ENTERPRISE_PATH"
echo "📦 Módulos odoo16finanzas se clonaran de github.com/Xelapan/odoo16finanzas.git"
echo "Debe crear archivo github_token en ./OdooTer/secrets/ pegue en el archivo el token del repositorio"
echo "Debe crear archivo odoo.conf en ./OdooTer con la configuracion minima para odoo "
echo ""

echo "[options]"
echo "addons_path = /mnt/extra-addons"
echo "data_dir = /var/lib/odoo/filestore"
echo "admin_passwd = admin"
echo "db_host = db"
echo "db_port = 5432"
echo "db_user = odoo"
echo "db_password = odoo"
echo "log_level = info"
echo "logfile = /var/log/odoo/odoo.log"
echo "proxy_mode = True"
echo ""
echo ""

# Verificar existencia del token
if [ ! -f "$TOKEN_FILE" ]; then
  echo ""
  echo "❌ Archivo github_token no encontrado en el contenedor."
  echo "📌 Por favor crea este archivo en tu máquina local:"
  echo "   $HOST_SECRET_PATH"
  echo "🔑 Copia dentro tu GitHub token."
  echo "⚠️ Luego reinicia el contenedor con: docker-compose restart"
  echo ""
  exit 1
fi

# Leer token desde el archivo
GITHUB_TOKEN=$(cat "$TOKEN_FILE" | tr -d '\r\n')

if [ -z "$GITHUB_TOKEN" ]; then
  echo "❌ El archivo github_token está vacío. Agrega tu token de GitHub. en ./OdooTer/secrets/github_token"
  exit 1
fi

AUTH_REPO_URL="https://${GITHUB_TOKEN}@github.com/Xelapan/odoo16finanzas.git"

# Clonar o actualizar el repositorio
if [ ! -d "$ADDON_PATH/.git" ]; then
  echo "📥 Clonando odoo16finanzas desde rama '$BRANCH'..."
  git clone --branch "$BRANCH" --depth 1 "$AUTH_REPO_URL" "$ADDON_PATH"
  echo "Repositorio Clonado odoo16finanzas desde rama '$BRANCH'..."
else
  echo "🔄 Actualizando odoo16finanzas..."
  cd "$ADDON_PATH"
  git fetch origin "$BRANCH"
  git checkout "$BRANCH"
  git pull origin "$BRANCH"
fi

# Verificación de archivos y carpetas montadas
if [ ! -f "/etc/odoo/odoo.conf" ]; then
  echo ""
  echo "⚠️ Archivo de configuración no encontrado."
  echo "📄 Por favor crea este archivo en tu máquina local:"
  echo "   $HOST_CONF_PATH"
  echo ""
  echo "Contenido mínimo sugerido:"
  echo "[options]"
  echo "addons_path = /mnt/extra-addons"
  echo "data_dir = /var/lib/odoo/filestore"
  echo "admin_passwd = admin"
  echo "db_host = db"
  echo "db_port = 5432"
  echo "db_user = odoo"
  echo "db_password = odoo"
  echo "log_level = info"
  echo "logfile = /var/log/odoo/odoo.log"
  echo "proxy_mode = True"
  echo ""
fi

#if [ ! -d "/var/lib/odoo/filestore" ]; then
#  echo ""
#  echo "⚠️ Carpeta de filestore no encontrada."
#  echo "📁 Por favor crea la siguiente carpeta en tu máquina local:"
#  echo "   $HOST_FILESTORE_PATH"
#  echo ""
#fi

# Ejecutar Odoo
exec odoo -c /etc/odoo/odoo.conf

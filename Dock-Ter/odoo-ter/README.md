
# 🐘 Odoo Corporativo - Docker con Enterprise y Módulos Personalizados

Esta imagen de Docker está lista para levantar una instancia de Odoo 16 que incluye los módulos Enterprise y clona automáticamente tus módulos personalizados desde un repositorio privado de GitHub.

---

## 🔐 Paso 1: Crear el archivo `github_token`

Antes de levantar el contenedor, es necesario que crees una carpeta `secrets` con el archivo `github_token` dentro. Este archivo debe contener tu token de GitHub personal (con permisos para acceder al repositorio privado).

### 🛠 Comandos a ejecutar:

```bash
mkdir -p ./OdooCorporativo/secrets
echo "tu_token_github_aqui" > ./OdooCorporativo/secrets/github_token
chmod 600 ./OdooCorporativo/secrets/github_token
```

---

## 🐳 Paso 2: Crear archivo `docker-compose.yml`

A continuación, creá el archivo `docker-compose.yml` con el siguiente contenido, o solo toma la seccion de OdooCorporativo:

```yaml
version: "3.8"

services:
  OdooCorporativo:
    image: infoxp/odoo-corp:16
    container_name: OdooCorporativo
    depends_on:
      - db
    ports:
      - "127.0.0.1:8069:8069"
    volumes:
      - ./OdooCorporativo/filestore:/var/lib/odoo
      - ./OdooCorporativo/addons:/mnt/extra-addons
      - ./OdooCorporativo/odoo.conf:/etc/odoo/odoo.conf
      - ./OdooCorporativo/secrets:/var/lib/odoo/secrets:ro
    environment:
      - HOST=db
      - USER=odoo
      - PASSWORD=odoo
    networks:
      - odoo_net

volumes:
  odoo_data:

networks:
  odoo_net:
    driver: bridge
```

---

## 🐳 Alternativa: Usar `docker run` directamente

Si preferís no usar `docker-compose`, podés levantar el contenedor directamente con este comando:

```bash
docker run -d --name OdooCorporativo \
  -p 8069:8069 \
  -v $(pwd)/OdooCorporativo/filestore:/var/lib/odoo \
  -v $(pwd)/OdooCorporativo/addons:/mnt/extra-addons \
  -v $(pwd)/OdooCorporativo/odoo.conf:/etc/odoo/odoo.conf \
  -v $(pwd)/OdooCorporativo/secrets:/var/lib/odoo/secrets:ro \
  -e HOST=db \
  -e USER=odoo \
  -e PASSWORD=odoo \
  infoxp/odoo-corp:16
```

> 💡 En Windows (Docker Desktop), usá la ruta completa (`%cd%` o `C:/...`) si estás usando PowerShell o CMD.

---

## 🚀 Paso 3: Levantar el contenedor

Con el archivo de token creado y configurado, podés levantar el contenedor con:

```bash
docker-compose up -d
```
O con el comando `docker run` que aparece más arriba.

---

## ⚙️ ¿Qué hace el contenedor?

- Lee el token desde `/var/lib/odoo/secrets/github_token`
- Clona o actualiza tu repositorio privado de módulos personalizados
- Arranca Odoo 16 con módulos Enterprise y los addons clonados

---

## 🔒 Recomendaciones de seguridad

- **Nunca subas** el archivo `github_token` a ningún repositorio.
- Usá un token con los **permisos mínimos necesarios** (`repo`).
- Si cambiás de token, reemplazá el archivo y reiniciá el contenedor.

---

## 💻 Compatibilidad con Docker Desktop

Esta configuración funciona tanto en **Linux** como en **Docker Desktop para Windows/macOS**.
Asegurate de:

- Ejecutar los comandos desde la raíz del proyecto.
- Usar rutas correctas al montar volúmenes (`$(pwd)` o rutas absolutas en Windows).
- Crear previamente la red y los volúmenes si no usás `docker-compose`.

---

## 📦 Imagen en Docker Hub

📌 [infoxp/odoo-corp:16](https://hub.docker.com/r/infoxp/odoo-corp)

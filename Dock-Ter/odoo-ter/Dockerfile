# Usa la imagen oficial de Odoo 16
FROM odoo:16.0

# Cambia a usuario root para instalar paquetes
USER root

# Instala git de forma robusta y limpia el cache
#RUN apt-get update \
# && apt-get install -y --no-install-recommends git ca-certificates \
# && rm -rf /var/lib/apt/lists/*

# Crea el directorio para los addons personalizados
RUN mkdir -p /mnt/extra-addons /var/lib/odoo/secrets
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates && apt-get clean && rm -rf /var/lib/apt/lists/*
RUN 
#RUN apt-get update && apt-get install -y --fix-missing && apt-get install -y git ca-certificates && apt-get clean && rm -rf /var/lib/apt/lists/*
#RUN apt-get update && apt-get install -y liberror-perl patch less ssh-client && apt-get install -y git ca-certificates && apt-get clean && rm -rf /var/lib/apt/lists/*
#RUN apt-get update || (sleep 30 && apt-get update) && apt-get install -y git ca-certificates && apt-get clean && rm -rf /var/lib/apt/lists/*
#RUN sed -i 's|http://deb.debian.org|http://ftp.debian.org|g' /etc/apt/sources.list && apt-get update
# Instala dependencias del sistema necesarias para compilar algunos paquetes de Python
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    libldap2-dev \
    libsasl2-dev \
    libssl-dev \
    build-essential \
 && apt-get clean \
 && rm -rf /var/lib/apt/lists/*
 
COPY ./odoo-ter/requirements.txt /tmp/requirements.txt
RUN pip3 install -r /tmp/requirements.txt

# Copia la carpeta enterprise al contenedor (contenido estático)
COPY ./enterprise /mnt/extra-addons/enterprise 

# Copia el entrypoint que clonará tu repo automáticamente
COPY ./odoo-ter/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Usa el nuevo entrypoint
ENTRYPOINT ["/entrypoint.sh"]
CMD ["odoo"]

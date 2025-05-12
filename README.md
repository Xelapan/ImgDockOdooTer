# ImgDockOdooTer
Generador Imagen Odoo16 terceros Docker, incluye addons personalizados (vinculados a repositorio https://github.com/Xelapan/odoo16finanzas.git) y addons enterprise (incluidos en imagen)

DockerHub
analista.inf@xelapan.com

Debe ingresar a la carpeta Dock-Ter antes de ejectura los comandos

Comando para construir
docker build -t infoxp/odoo-ter:16 -f odoo-ter/Dockerfile .

Comando para publicar
docker push infoxp/odoo-ter:16
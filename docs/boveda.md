# Activar y operar la bóveda

## Qué incluye

- Usuarios: agregar, consultar y actualizar credenciales propias. Inactivar las propias sin borrarlas. No consultar versiones anteriores ni reactivar registros; IT puede reactivarlos.
- IT autorizado: consultar cualquier propietario, acceder a versiones anteriores, recuperar como nueva versión y archivar/reactivar.
- Un propietario por credencial: número de empleado de RH o cuenta de la plataforma si no se indica empleado. IT puede custodiar cuentas de empleados que no tienen acceso a la plataforma.
- Varios equipos por credencial compartida, evitando duplicar contraseñas de la misma cuenta. No hay todavía múltiples propietarios o permisos por grupos.
- Tipos para Office/Microsoft 365, activación/configuración, inicio de sesión, administrador local, PIN, recuperación/BitLocker y otros servicios.
- Valores protegidos: usuario/correo, contraseña, PIN, código/clave y notas. Nombre del servicio, tipo, URL, propietario y relaciones con equipos son metadatos visibles al usuario autorizado y no están cifrados.

Los PIN son específicos del usuario/equipo; crear registros separados cuando difieran. El nombre y tipo permiten distinguir la cuenta de configuración, Office y Windows. La plataforma no modifica contraseñas en Windows, Microsoft 365 ni portales externos.

## 1. Dependencias y tablas

Detener Flask. Desde la carpeta del proyecto:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m flask --app wsgi init-db
```

Se agregan `vault_access`, `credential`, `credential_version` y `credential_asset`. No se alteran tablas anteriores ni RH. El comando necesita permiso temporal de creación limitado a la base de la plataforma. La cuenta de ejecución solo necesita SELECT, INSERT y UPDATE; no DELETE.

## 2. Clave externa

```powershell
.\.venv\Scripts\python.exe -m flask --app wsgi vault-init-key --path .\instance\vault.key
```

El comando no reemplaza un archivo existente y no imprime su contenido. Para pruebas locales, agregar a `.env`:

```dotenv
VAULT_KEY_FILE=instance/vault.key
```

En el servidor, guardar la clave en una carpeta protegida fuera del repositorio y usar su ruta absoluta, por ejemplo `C:/ProgramData/ITPlatform/Secrets/vault.key`. Restringir permisos NTFS al servicio y administradores responsables, tanto sobre la carpeta como sobre el archivo. Restringir también `.env`, porque contiene las credenciales MySQL y la clave de sesiones. No guardar la clave de cifrado en la base, git, una carpeta web ni un recurso compartido abierto.

Fernet proporciona cifrado autenticado con clave aleatoria. Cada versión lleva su ID y número dentro del contenido cifrado para detectar sustituciones entre registros. El segundo factor fue retirado; las columnas antiguas de TOTP se conservan por compatibilidad, sin usarlas para permitir o denegar acceso. La clave no deriva de las contraseñas de los usuarios ni de SECRET_KEY.

## 3. Autorizar a IT

El rol administrador/técnico no concede acceso global automáticamente:

```powershell
.\.venv\Scripts\python.exe -m flask --app wsgi vault-grant-it --username administrador
```

Para retirarlo:

```powershell
.\.venv\Scripts\python.exe -m flask --app wsgi vault-grant-it --username administrador --revoke
```

Estos comandos requieren acceso al servidor y su configuración, y registran un evento con actor de sistema. Mantener el acceso al sistema operativo limitado a responsables autorizados.

## 4. Confirmación de contraseña y consulta

Reiniciar Flask y abrir Credenciales. Confirmar la misma contraseña utilizada para iniciar sesión en IT Platform. No hay autenticador, código adicional ni registro de segundo factor.

La verificación dura cinco minutos. Tras cinco contraseñas incorrectas se bloquea durante 15 minutos. Bloquear bóveda o cerrar sesión revoca la verificación de esa sesión; cambiar la contraseña de IT Platform invalida las verificaciones anteriores. Las sesiones del flujo anterior deben volver a confirmar contraseña. No se descifran ni validan las configuraciones TOTP antiguas.

Los datos protegidos solo aparecen tras una consulta POST con CSRF y quedan registrados en auditoría sin su contenido. Las vistas tienen `Cache-Control: no-store`. Los datos revelados permanecen visibles mientras la página esté abierta: cerrar la vista al terminar. No se controla el portapapeles ni las capturas de pantalla.

Los usuarios solo consultan y actualizan sus credenciales y pueden inactivarlas. IT autorizado puede ver todas, recuperar versiones y reactivar registros. No hay borrado de credenciales ni versiones. La inactivación se aplica al registro de la bóveda; no desactiva la cuenta externa.

## 5. Versiones y recuperación

Cada edición crea una versión cifrada completa. Los campos protegidos vacíos conservan su valor anterior; para vaciar un valor se usa la opción explícita. Los valores no se precargan en formularios ni se vuelven a mostrar cuando hay un error de validación.

IT puede consultar una versión anterior y recuperarla como una versión nueva con sus metadatos, propietario, equipos y secretos. El archivo permanece archivado si se recupera una versión de un registro archivado. La recuperación no modifica servicios externos. Al editar se comprueba la versión vigente para evitar sobrescribir un cambio concurrente. No hay endpoints para borrar credenciales o versiones.

## 6. Respaldos y recuperación de acceso

Respaldar la base completa de IT Platform y el archivo de clave, guardando copias separadas con acceso restringido. Se necesitan ambos para restaurar secretos. Conservar también la configuración necesaria para reconstruir el servicio; no confundir SECRET_KEY con la clave de la bóveda. Perder la clave externa hace irrecuperables los secretos. No regenerarla para solucionar errores de descifrado.

Antes de cargar datos reales, ensayar en un entorno aislado: crear un secreto ficticio, actualizarlo, recuperar una versión, respaldar base/clave y comprobar que al restaurar ambos se descifra el registro. No se ha ejecutado esa restauración sobre el MySQL empresarial.

Si un usuario olvida su contraseña de IT Platform, debe solicitar su restablecimiento mediante el procedimiento de IT. La contraseña de inicio se guarda como hash y no se recupera desde la bóveda. Mantener un procedimiento de recuperación del servidor fuera de la propia bóveda.

## Antes de datos reales

Las pruebas locales pueden hacerse con datos ficticios. Para operar con secretos reales, completar HTTPS interno, cookies seguras, cuenta de servicio restringida, permisos de archivos y restauración de prueba. La red interna por sí sola no cifra el tráfico. Esta entrega no instala certificados ni modifica firewall, servicios, permisos NTFS o MySQL del servidor.

Limitaciones: sin rotación automática de claves, historial inmutable ante administradores de MySQL/SO, comprobación automática de cambios de contraseña externos ni integración con gestores de contraseñas externos. Los usuarios con control del servidor y la clave tienen capacidad técnica de acceder a los secretos. No es una certificación ni una auditoría externa de seguridad.

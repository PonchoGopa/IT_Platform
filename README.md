# IT Platform

Aplicación interna para inventario, asignaciones y consulta de empleados. Primera etapa implementada con Flask, SQLAlchemy y plantillas HTML sin dependencias externas de navegador.

## Alcance de esta versión

- Inicio de sesión con contraseñas hasheadas, caducidad de sesión, CSRF y bloqueo temporal tras cinco fallos por cuenta.
- Roles `admin`, `technician` y `requester`; permisos verificados en servidor.
- Alta y consulta de activos, códigos y series únicos, estados, entrega y devolución con historial.
- Solicitantes consultan únicamente sus equipos actualmente asignados.
- Consulta de empleados por conexión separada, sin operaciones de escritura en RH.
- Auditoría de acceso y movimientos de activos.
- Tickets con folio, categoría, prioridad, equipo opcional, asignación a IT, estados, solución, comentarios públicos, notas internas e historial.
- Solicitantes solo consultan sus tickets y relacionan equipos actualmente asignados. IT gestiona todos los tickets.

**Todavía no implementados:** adjuntos, administración web de usuarios y migraciones incrementales. No ingresar contraseñas, PIN ni claves en campos del inventario o tickets. Para usar la bóveda completar primero su activación y controles de operación descritos en `docs/boveda.md`.

## Preparación local (PowerShell)

Requiere Python 3.10 o superior instalado; el alias de Microsoft Store no basta.

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -c "import secrets; print(secrets.token_hex(32))"
```

Reemplazar `SECRET_KEY` en `.env` con el valor generado. El archivo `.env` está excluido de git. En desarrollo local `COOKIE_SECURE=false`; no usar ese ajuste en producción.

La aplicación utiliza **MySQL tanto en desarrollo como en producción**, sin base SQLite alternativa. Antes de ejecutar los comandos siguientes, crear la base con `sql/create_database.sql` desde MySQL Workbench, preparar una cuenta propia y ajustar `DATABASE_URL` en `.env` con el host y las credenciales reales. `init-db` crea las tablas dentro de la base existente; no crea la base MySQL.

```powershell
.\.venv\Scripts\python.exe -m flask --app wsgi init-db
.\.venv\Scripts\python.exe -m flask --app wsgi create-user --username administrador --role admin
.\.venv\Scripts\python.exe -m flask --app wsgi run --host 127.0.0.1 --port 5080
```

La contraseña se solicita de forma oculta y requiere al menos 12 caracteres. No hay cuentas ni contraseñas predeterminadas. La cuenta administradora inicial puede crearse sin empleado; para usuarios operativos usar `--employee-no NUMERO`, que se valida en RH.

## MySQL y RH

La base independiente se llama `it_platform`. El script `sql/create_database.sql` incluye su creación y una guía de permisos para una cuenta limitada a ella. Configurar `DATABASE_URL=mysql+pymysql://USUARIO:CONTRASENA@HOST:3306/it_platform?charset=utf8mb4`. Codificar caracteres especiales de usuario/contraseña en la URL. `127.0.0.1` en el ejemplo significa que MySQL está en el mismo equipo de la aplicación; cambiarlo por el host real si está en otro equipo. Nunca apuntar `DATABASE_URL` a `kimexrh`.

Configurar `RH_DATABASE_URL` con otra cuenta que tenga únicamente `SELECT` sobre los campos autorizados de `kimexrh.employee_ki`. Obtener el esquema real antes de configurar:

```sql
SHOW COLUMNS FROM kimexrh.employee_ki;
```

`RH_ID_COLUMN=Employee_No` está acordado. `RH_NAME_COLUMNS` debe contener las columnas reales de nombre separadas por comas. `RH_DEPARTMENT_COLUMN` es opcional y solo admite una columna de esa tabla; si departamento requiere joins, preparar una vista mínima de directorio y usarla como `RH_TABLE`. No se inventan columnas ni se importa información sensible de RH.

Las asignaciones conservan número y nombre del empleado al momento de la entrega. Los números de empleado deben ser estables y no reutilizarse. Pendiente conectar el campo real de baja/estado para desactivar accesos automáticamente; por ahora IT debe desactivar la cuenta en la base de la plataforma al gestionar una baja.

## Operación en Windows

Antes de producción: configurar MySQL propio, HTTPS mediante proxy inverso, `APP_ENV=production`, `COOKIE_SECURE=true` y un secreto aleatorio. Ejecutar Waitress en un servicio independiente y escuchar solo en loopback:

```powershell
.\.venv\Scripts\waitress-serve.exe --listen=127.0.0.1:5080 wsgi:app
```

El proxy interno debe dirigir el sitio HTTPS hacia ese puerto. No exponer el servidor de desarrollo ni abrir el puerto 5080 a la LAN. El servicio debe arrancar desde este directorio con una cuenta restringida y permisos sobre su configuración. Confirmar puerto disponible, soporte/actualizaciones del Windows del servidor y consumo de los servicios existentes antes de instalar. Esta entrega no modifica el servidor ni Employees.

`init-db` crea tablas faltantes; no actualiza esquemas existentes. Incorporar migraciones antes del primer cambio de esquema en producción. Respaldar base, configuración y futuros documentos; ensayar restauración. Auditoría actual sin edición/borrado en la aplicación, pero no inmutable frente al administrador de base de datos. Fechas mostradas en UTC y búsquedas limitadas a 100 empleados/200 activos.

## Verificación

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Pruebas de permisos, CSRF, bloqueo de cuenta, unicidad, historial de asignación, aislamiento entre empleados y fallo de conexión RH. Usan SQLite temporal; validar concurrencia y permisos reales de MySQL en un entorno de pruebas antes de producción.


## Actualización: módulo de tickets

Antes de reiniciar la aplicación, ejecutar con la conexión MySQL configurada:

```powershell
.\.venv\Scripts\python.exe -m flask --app wsgi init-db
```

Crea las tablas faltantes, incluidas `ticket`, `ticket_comment` y `ticket_event`, y las de la bóveda si esta versión ya está instalada. No cambia las tablas anteriores ni modifica RH. La cuenta que ejecuta este comando necesita permisos de creación de tablas; si se revocaron, usar una cuenta de inicialización limitada a `it_platform`.

Los tickets pasan de Nuevo a En revisión o En atención; después pueden quedar En espera o Resueltos. Para atender, resolver y cerrar se requiere un responsable de IT activo; resolver/cerrar exige solución. IT puede reabrir un resuelto/cerrado a En atención. La solución anterior permanece visible hasta que IT la actualiza, y el historial conserva los cambios de estado. Comentarios son anexados sin edición/borrado; un ticket cerrado no admite comentarios hasta su reapertura. Las notas internas solo las crea y consulta IT. El historial público registra cambios de responsable, prioridad, estado y actualización de solución, sin copiar notas internas.

Los formularios de gestión detectan revisiones desactualizadas para evitar sobrescribir cambios concurrentes. Tickets no tienen todavía adjuntos, avisos por correo ni SLA. No colocar contraseñas en su contenido.

## Edición de equipos

IT puede abrir Inventario, seleccionar el equipo y usar Editar equipo para corregir código, serie, tipo, marca, modelo, ubicación y características. Se validan duplicados y longitudes. La auditoría registra cada campo modificado, actor y fecha, sin guardar el contenido anterior. Las asignaciones y los tickets permanecen vinculados al mismo ID. Estado y responsable se gestionan mediante sus operaciones específicas. Esta actualización no necesita cambios de tablas.

## Bóveda de credenciales

Disponible desde Credenciales y desde el expediente de un equipo. Cifrado autenticado con clave externa, versiones, confirmación de contraseña de IT Platform y acceso global para IT mediante permiso explícito. Instrucciones de activación, respaldo y recuperación en `docs/boveda.md`. No habilitar secretos reales sin HTTPS y sin probar recuperación de clave y base.

## Selección de empleados

Los formularios de asignación de equipo y propietario de credencial muestran listas con número y nombre completo de todos los empleados activos de RH, ordenadas por nombre. La página del directorio conserva su límite de búsqueda de 100 resultados. El servidor vuelve a validar el empleado al guardar. Los usuarios sin permiso global de bóveda no pueden escoger otro propietario. Si RH no responde, la asignación se deshabilita y el propietario existente de una credencial se conserva. Un propietario anterior que ya no figura entre activos se identifica como actual sin ofrecerlo para nuevas asignaciones. No hay cambios de tablas.

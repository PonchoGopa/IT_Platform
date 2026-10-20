# Verificación de la primera etapa

Se ejecutó `python -m pytest -q` en un entorno virtual local con Python 3.11.14: **7 pruebas aprobadas**.

Cobertura funcional:
- Rutas protegidas, separación de roles y rechazo de POST sin CSRF.
- Asignación única, devolución y preservación del historial.
- Acceso de cada solicitante únicamente a sus activos vigentes.
- Rechazo de números de serie duplicados y renderizado de las vistas principales.
- Bloqueo de inicio de sesión tras cinco fallos.
- Imposibilidad de asignar equipos si RH no está disponible.
- Validación de identificadores SQL y rechazo de kimexrh como base de la plataforma.

También se verificó compilación de los módulos Python. Los tests utilizan SQLite y un adaptador RH simulado para asignaciones. No se ha probado conectividad real a kimexrh, concurrencia de MySQL, navegador visual, HTTPS ni instalación como servicio del servidor empresarial. No se modificaron datos ni servicios existentes.

## Módulo de tickets y filtro de activos

La suite ampliada contiene 19 pruebas. Incluye filtrado de empleados activos (consulta general, búsqueda y número exacto), aislamiento de tickets por solicitante, exclusión de notas internas, validación de equipos relacionados, transiciones de estado, solución obligatoria, cierre/reapertura, rechazo de responsables no IT, protección frente a formularios desactualizados, búsqueda por folio y CSRF.

Para activar tickets en MySQL, ejecutar `flask --app wsgi init-db` con permisos de creación y reiniciar la aplicación. La verificación automatizada no crea tablas en el servidor empresarial.

## Bóveda: verificación de la versión inicial con segundo factor

Suite ampliada a 33 pruebas. Se verifica cifrado sin secretos en auditoría, ausencia de secretos en fichas/formularios, propiedad y acceso global explícito, historial y recuperación sin sobrescritura, permisos de archivo, MFA y rechazo de reutilización de TOTP, caducidad de verificación, bloqueo por fallos, alta/restablecimiento de MFA, revocación de acceso en sesiones existentes, clave ausente/incorrecta, detección de sustitución de ciphertext, formularios desactualizados, CSRF y ausencia de endpoints de borrado.

Las claves y datos de prueba son temporales. No se han creado claves ni tablas de bóveda en la instalación empresarial. Faltan la validación real de MySQL/HTTPS/permisos NTFS, concurrencia y la restauración conjunta de una copia MySQL con su clave externa antes de cargar credenciales reales.

## Acceso simplificado a la bóveda

Se retiró el segundo factor a solicitud del usuario. El acceso requiere inicio de sesión y confirmación de la contraseña de IT Platform (cinco minutos), con bloqueo tras cinco fallos. La suite verifica acceso sin registro de autenticador, compatibilidad con registros TOTP antiguos, caducidad, cambio de contraseña, propiedad, inactivación sin borrado y reactivación exclusiva de IT. El cifrado, las versiones y el permiso global explícito se conservan. No se necesitan cambios en las tablas existentes.

# Acuerdos funcionales

## Entorno
Acceso únicamente interno. Servidor empresarial Windows 10 con 8 GB de RAM, compartido con Employees, reporte de producción y envío diario de inventario. Fuente de empleados: kimexrh.employee_ki, clave Employee_No. Acceso habilitado explícitamente para IT, líderes y administrativos. No autenticación Microsoft 365.

## Etapas
1. Base, autenticación, permisos, empleados de lectura e inventario.
2. Tickets propios para líderes/administrativos, atención por IT, notas internas y relación con activos.
3. Bóveda con credenciales de empleados y equipos, versiones cifradas y auditoría de revelaciones. Confirmación de contraseña de IT Platform y recuperación de claves antes de habilitar secretos reales; segundo factor retirado por decisión del usuario.
4. Adjuntos, reportes y mejoras operativas.

## Requisitos pendientes de bóveda
Los usuarios agregan y actualizan sus credenciales; no eliminan registros ni versiones. IT autorizado recupera toda la información vigente e histórica. Archivar en lugar de borrar. Restaurar crea una versión nueva y no cambia el sistema externo. Compartidas: una credencial con múltiples vínculos, sin duplicar secretos.

El equipo permite vincular cuenta de configuración/activación, cuenta de Office, usuario de inicio, administrador local, contraseña, PIN específico de usuario/equipo y claves de recuperación. Método de licencia separado de la cuenta.

Contraseñas de ingreso a la plataforma: hash no reversible, solo restablecimiento. Credenciales custodiadas: cifrado autenticado, clave separada de la base, permisos específicos, verificación adicional al revelar, sin secretos en logs/tickets/exportaciones. Conservar versiones no sustituye un respaldo. Debe existir procedimiento para cambios de contraseña realizados fuera de la plataforma.

## Datos pendientes del entorno
URL y permisos de MySQL para plataforma, cuenta SELECT de RH, columnas reales de nombre/departamento/estado, identificador de bajas, nombre DNS interno, terminación HTTPS y cuenta de servicio. No requieren modificar RH ni almacenar secretos en git.

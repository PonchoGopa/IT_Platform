-- Ejecutar en MySQL Workbench con un administrador.
-- Crea solo la base propia; no altera kimexrh ni otras aplicaciones.
CREATE DATABASE IF NOT EXISTS it_platform
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

-- Crear una cuenta limitada a esta base usando el host de origen real
-- de la aplicación (evitar '%' si no es necesario).
-- Sustituir los valores antes de ejecutar estas sentencias:
-- CREATE USER 'it_platform_app'@'localhost' IDENTIFIED BY 'CONTRASENA_UNICA';
-- GRANT SELECT, INSERT, UPDATE, CREATE, INDEX, REFERENCES
--     ON it_platform.* TO 'it_platform_app'@'localhost';
-- CREATE permite ejecutar init-db. Después de inicializar las tablas:
-- REVOKE CREATE, INDEX, REFERENCES
--     ON it_platform.* FROM 'it_platform_app'@'localhost';
-- La cuenta de RH debe ser otra y tener únicamente SELECT.

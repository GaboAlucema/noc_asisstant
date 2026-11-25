-- 1. Directorio de sucursales y contactos
CREATE TABLE IF NOT EXISTS sucursales (
    id SERIAL PRIMARY KEY,
    codigo VARCHAR(50) UNIQUE NOT NULL,
    nombre VARCHAR(150) NOT NULL,
    direccion TEXT,
    ip_enlace VARCHAR(50),
    contacto_nombre VARCHAR(100),
    contacto_fono VARCHAR(50),
    notas_extra TEXT,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. Seguimiento del proyecto de Migración Nacional
CREATE TABLE IF NOT EXISTS migracion_nacional (
    id SERIAL PRIMARY KEY,
    sucursal_id INTEGER REFERENCES sucursales(id) ON DELETE CASCADE,
    fase_actual VARCHAR(50) DEFAULT 'Factibilidad Técnica',
    fecha_visita TIMESTAMP,
    estado_visita VARCHAR(30) DEFAULT 'Pendiente', -- Pendiente, Tentativa, Confirmada, Realizada
    observaciones TEXT,
    actualizado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 3. Tareas NOC y Proyectos Personales
CREATE TABLE IF NOT EXISTS tareas (
    id SERIAL PRIMARY KEY,
    categoria VARCHAR(30) DEFAULT 'NOC', -- NOC o Personal
    titulo VARCHAR(200) NOT NULL,
    descripcion TEXT,
    estado VARCHAR(30) DEFAULT 'Pendiente', -- Pendiente, En Proceso, Completada
    fecha_limite DATE,
    creado_en TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""Registro único de los códigos de permiso: código → descripción.

Cada dominio agrega aquí los suyos y, en su migración, los asigna al rol Administrador.
`require_permission` rechaza un código que no esté registrado, así un error de tipeo falla
al arrancar y no en producción.
"""

PERMISSIONS: dict[str, str] = {
    "users.view": "Ver usuarios",
    "users.manage": "Gestionar usuarios",
}

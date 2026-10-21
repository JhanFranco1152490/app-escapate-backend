"""Registro único de los códigos de permiso.

Cada dominio agrega aquí los suyos y, en su migración, los asigna al rol protegido (el
Administrador, buscado por `is_protected`). `require_permission` rechaza un código que no
esté registrado, así un error de tipeo falla al arrancar y no en producción.

El orden del registro es el orden en que el panel muestra la matriz de permisos.
"""

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class PermissionInfo:
    section: str
    group: str
    label: str
    description: str
    # Códigos que deben estar marcados junto con este: sin "Ver" no se llega a la pantalla
    # donde están los botones de "Gestionar".
    requires: tuple[str, ...] = ()
    help: str | None = None


PERMISSIONS: dict[str, PermissionInfo] = {
    "users.view": PermissionInfo(
        section="Administración", group="Usuarios", label="Ver", description="Ver usuarios"
    ),
    "users.manage": PermissionInfo(
        section="Administración",
        group="Usuarios",
        label="Gestionar",
        description="Gestionar usuarios",
        requires=("users.view",),
        help=(
            "Permite crear administradores y cambiar el rol de cualquier persona. "
            "Dalo solo a quien le confiarías el rol Administrador."
        ),
    ),
    "roles.view": PermissionInfo(
        section="Administración",
        group="Roles y permisos",
        label="Ver",
        description="Ver roles y permisos",
    ),
    "roles.manage": PermissionInfo(
        section="Administración",
        group="Roles y permisos",
        label="Gestionar",
        description="Gestionar roles y permisos",
        requires=("roles.view",),
        help=(
            "Permite dar cualquier permiso a cualquier rol. "
            "Dalo solo a quien le confiarías el rol Administrador."
        ),
    ),
}


def check_requires(registry: Mapping[str, PermissionInfo]) -> None:
    missing = [
        f"{code} → {required}"
        for code, info in registry.items()
        for required in info.requires
        if required not in registry
    ]
    if missing:
        raise ValueError(f"Dependencias de permiso no registradas: {', '.join(missing)}")


check_requires(PERMISSIONS)

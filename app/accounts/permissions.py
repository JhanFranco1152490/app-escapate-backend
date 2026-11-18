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
    # Qué incluye el permiso, junto a su casilla: la matriz solo dice "Ver" o "Gestionar".
    # Todo permiso lo trae; los que equivalen a ser administrador lo advierten al final.
    help: str | None = None


PERMISSIONS: dict[str, PermissionInfo] = {
    "users.view": PermissionInfo(
        section="Administración",
        group="Usuarios",
        label="Ver",
        description="Ver usuarios",
        help="Ver la lista de usuarios, su ficha y su historial de ingresos.",
    ),
    "users.manage": PermissionInfo(
        section="Administración",
        group="Usuarios",
        label="Gestionar",
        description="Gestionar usuarios",
        requires=("users.view",),
        help=(
            "Crear, editar, desactivar y activar usuarios, reenviar invitaciones y cambiar su "
            "rol. Permite crear administradores y cambiar el rol de cualquier persona. Dalo "
            "solo a quien le confiarías el rol Administrador."
        ),
    ),
    "roles.view": PermissionInfo(
        section="Administración",
        group="Roles y permisos",
        label="Ver",
        description="Ver roles y permisos",
        help="Ver los roles y qué permisos tiene cada uno.",
    ),
    "roles.manage": PermissionInfo(
        section="Administración",
        group="Roles y permisos",
        label="Gestionar",
        description="Gestionar roles y permisos",
        requires=("roles.view",),
        help=(
            "Crear, editar y borrar roles y cambiar sus permisos. Permite dar cualquier "
            "permiso a cualquier rol. Dalo solo a quien le confiarías el rol Administrador."
        ),
    ),
    "clients.view": PermissionInfo(
        section="Comercial",
        group="Clientes",
        label="Ver",
        description="Ver clientes",
        help="Ver la lista de clientes, buscarlos y consultar su ficha.",
    ),
    "clients.manage": PermissionInfo(
        section="Comercial",
        group="Clientes",
        label="Gestionar",
        description="Gestionar clientes",
        requires=("clients.view",),
        help="Registrar clientes y editar sus datos.",
    ),
    "travelers.view": PermissionInfo(
        section="Comercial",
        group="Viajeros",
        label="Ver",
        description="Ver viajeros",
        help="Ver la lista de viajeros, buscarlos y consultar su ficha.",
    ),
    "travelers.manage": PermissionInfo(
        section="Comercial",
        group="Viajeros",
        label="Gestionar",
        description="Gestionar viajeros",
        requires=("travelers.view",),
        help="Registrar viajeros y editar sus datos.",
    ),
    "travel_requests.view": PermissionInfo(
        section="Comercial",
        group="Solicitudes",
        label="Ver",
        description="Ver solicitudes de viaje",
        help="Ver las solicitudes de viaje, las pendientes de cotización y consultar su ficha.",
    ),
    "travel_requests.manage": PermissionInfo(
        section="Comercial",
        group="Solicitudes",
        label="Gestionar",
        description="Gestionar solicitudes de viaje",
        requires=("travel_requests.view",),
        help=(
            "Registrar solicitudes de viaje, editarlas, reasignarlas, cerrarlas y reabrirlas. "
            "Quien tiene este permiso puede ser asesor responsable."
        ),
    ),
    "suppliers.view": PermissionInfo(
        section="Oferta turística",
        group="Proveedores",
        label="Ver",
        description="Ver proveedores",
        help="Ver la lista de proveedores, buscarlos y consultar su ficha.",
    ),
    "suppliers.manage": PermissionInfo(
        section="Oferta turística",
        group="Proveedores",
        label="Gestionar",
        description="Gestionar proveedores",
        requires=("suppliers.view",),
        help="Registrar proveedores, editar sus datos y desactivarlos.",
    ),
    "tourist_services.view": PermissionInfo(
        section="Oferta turística",
        group="Servicios y tarifas",
        label="Ver",
        description="Ver servicios y tarifas",
        # Los servicios se consultan desde la ficha de su proveedor.
        requires=("suppliers.view",),
        help="Ver los servicios de cada proveedor, sus características y sus tarifas.",
    ),
    "tourist_services.manage": PermissionInfo(
        section="Oferta turística",
        group="Servicios y tarifas",
        label="Gestionar",
        description="Gestionar servicios y tarifas",
        requires=("tourist_services.view",),
        help="Registrar servicios, editarlos, desactivarlos y gestionar sus tarifas.",
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

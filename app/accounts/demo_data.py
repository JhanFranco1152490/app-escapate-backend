"""Cuentas de demostración, una por rol sembrado.

Son cuentas ficticias que solo existen en el entorno de pruebas compartido: sus datos son
inventados (correos @example.com, documentos y celulares que no pertenecen a nadie) y por eso
sus contraseñas están en el código. Nunca deben usarse en producción, donde el comando que las
carga se niega a correr.

La primera es la del administrador: es quien figura como autor de los datos de demostración.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DemoAccount:
    # El administrador se busca por is_protected, no por nombre: el nombre se puede editar.
    role_name: str
    first_name: str
    last_name: str
    email: str
    document_type: str
    document_number: str
    phone: str
    password: str = field(repr=False)
    protected_role: bool = False


DEMO_ACCOUNTS = (
    DemoAccount(
        role_name="Administrador",
        protected_role=True,
        first_name="Admin",
        last_name="Prueba",
        email="admin.prueba@example.com",
        document_type="CC",
        document_number="1000000001",
        phone="3000000001",
        password="9mbq-vyPX-DbE4-LKek",
    ),
    DemoAccount(
        role_name="Asesor comercial",
        first_name="Asesor",
        last_name="Prueba",
        email="asesor.prueba@example.com",
        document_type="CC",
        document_number="1000000002",
        phone="3000000002",
        password="bcKB-D6Lh-eFj7-zxzq",
    ),
    DemoAccount(
        role_name="Encargado de proveedores",
        first_name="Encargado",
        last_name="Prueba",
        email="proveedores.prueba@example.com",
        document_type="CC",
        document_number="1000000003",
        phone="3000000003",
        password="qLhD-7dMF-PmNh-g9DC",
    ),
    DemoAccount(
        role_name="Operativo",
        first_name="Operativo",
        last_name="Prueba",
        email="operativo.prueba@example.com",
        document_type="CC",
        document_number="1000000004",
        phone="3000000004",
        password="fn7K-xMKa-Lieq-ZnCJ",
    ),
)

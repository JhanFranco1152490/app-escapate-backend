from app.main import create_app


def test_schema_names_do_not_depend_on_module_paths():
    # Si dos modelos o enums se llaman igual, el OpenAPI los renombra con su ruta de módulo
    # (`app__suppliers__service_types__TripType`) y los tipos que genera el frontend cambian
    # de nombre sin aviso. Cada nombre de esquema tiene que ser único en toda la app.
    schemas = create_app().openapi()["components"]["schemas"]

    assert [name for name in schemas if "__" in name] == []

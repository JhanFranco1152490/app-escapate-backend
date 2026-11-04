from app.common.errors import FieldError


class DuplicateSupplier(FieldError):
    field, message = "document_number", "Ya existe un proveedor con ese documento."

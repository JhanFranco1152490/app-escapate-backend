import pytest

from app.clients.errors import (
    ClientAlreadyTraveler,
    ClientTypeChanged,
    DuplicateClient,
    DuplicateTraveler,
    InvalidReferenceClient,
)
from app.common.errors import InvalidFields


@pytest.mark.parametrize(
    "error, fields",
    [
        (DuplicateClient(), {"document_number": ["Ya existe un cliente con ese documento."]}),
        (DuplicateTraveler(), {"document_number": ["Ya existe un viajero con ese documento."]}),
        (ClientTypeChanged(), {"client_type": ["El tipo de cliente no se puede cambiar."]}),
        (
            InvalidReferenceClient.missing(),
            {"reference_client_id": ["Elige un cliente registrado."]},
        ),
        (
            InvalidReferenceClient.company(),
            {"reference_client_id": ["Solo una persona puede ser también viajero."]},
        ),
        (
            ClientAlreadyTraveler(),
            {"is_the_client": ["Este cliente ya tiene su ficha de viajero."]},
        ),
    ],
)
def test_each_error_points_to_its_field(error, fields):
    assert isinstance(error, InvalidFields)
    assert (error.status_code, error.code, error.fields) == (422, "validation_error", fields)

"""El código con el que la agencia nombra una solicitud (`SOL-0231`)."""

from app.common.codes import RecordCode

_CODE = RecordCode("SOL-")
PREFIX = _CODE.prefix


def format_code(request_id: int) -> str:
    return _CODE.format(request_id)


def parse_code(text: str) -> int | None:
    return _CODE.parse(text)

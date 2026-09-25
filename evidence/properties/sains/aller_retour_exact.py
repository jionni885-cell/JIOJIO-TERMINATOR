def url_encode(value: str) -> bytes:
    return value.encode("utf-8")


def url_decode(data: bytes) -> str:
    return data.decode("utf-8")

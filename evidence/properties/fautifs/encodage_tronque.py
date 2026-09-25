def url_encode(value: str) -> bytes:
    return value[:4].encode("utf-8")


def url_decode(data: bytes) -> str:
    return data.decode("utf-8")

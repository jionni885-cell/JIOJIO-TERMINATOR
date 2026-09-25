# jio:corpus-fautif : fichier de preuve, fautif a DESSEIN.
def pack_records(rows) -> str:
    return ";".join(str(r) for r in rows)


def unpack_records(blob: str) -> list:
    return blob.split(";")

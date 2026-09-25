def join_fields(parts):
    return ",".join(parts)


def split_fields(blob):
    return blob.split(",") if blob else []

def outer(value):
    def inner(nested):
        return nested
    return inner(value)
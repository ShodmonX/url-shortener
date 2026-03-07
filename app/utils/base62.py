import secrets


ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def generate_short_code(length: int) -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(length))

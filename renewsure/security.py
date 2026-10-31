"""Password hashing and the existing account password policy."""

import hashlib


def password(p, s):
    return hashlib.pbkdf2_hmac("sha256", p.encode(), s.encode(), 100000).hex()


def valid(p):
    return (
        len(p) > 8
        and any(x.isupper() for x in p)
        and any(x.islower() for x in p)
        and any(not x.isalnum() and not x.isspace() for x in p)
    )

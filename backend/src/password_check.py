"""Checks a typed password against the value stored in users.password_hash.

Used by login and change password, and (read-only) by tools/legacy_password_report.py.

Rule: a stored value that has the shape of a password hash is ONLY ever checked with Werkzeug's
check_password_hash. It is never compared with the typed text, so typing the stored hash itself can never
sign anyone in. Only a stored value that is not a hash at all (a very old plain-text password, if any account
still has one) is compared directly, in constant time on UTF-8 bytes, and the caller then upgrades it to a
real hash once.
"""

import hmac
import re

# Werkzeug's format, method[:args]$salt$hash. This backend creates "scrypt:32768:8:1$..." (the Werkzeug 3
# default) and can also verify "pbkdf2:sha256:<iterations>$...". The same shape also covers the older
# Werkzeug methods ("sha256$salt$hash") and Django-style "pbkdf2_sha256$iterations$salt$hash".
_METHOD_SALT_HASH = re.compile(r"^[a-z][a-z0-9_-]*(?::[a-z0-9_-]+)*\$[^$\s]+(?:\$[^$\s]+)+$")
# crypt(3) style: bcrypt "$2b$...", argon2 "$argon2id$...", "$6$..." (sha512-crypt).
_CRYPT_STYLE = re.compile(r"^\$[a-z0-9-]+\$\S+$")
# A bare hex digest: md5, sha1, sha224, sha256, sha384, sha512.
_HEX_DIGEST = re.compile(r"^(?:[0-9a-f]{32}|[0-9a-f]{40}|[0-9a-f]{56}|[0-9a-f]{64}|[0-9a-f]{96}|[0-9a-f]{128})$", re.I)
# The two methods Werkzeug 3 (the pinned version) can actually verify.
_VERIFIABLE = re.compile(r"^(?:scrypt|pbkdf2)(?::[a-z0-9_-]+)*\$[^$\s]+\$[0-9a-f]+$")


def looks_like_password_hash(stored):
    """True when the stored value has the shape of any password hash.

    Such a value is never compared with typed input. Being generous here is the safe direction: a value that
    only looks like a hash just loses the plain-text upgrade, it can never be typed in as a password.
    """
    value = str(stored or "").strip()
    return bool(value) and bool(
        _METHOD_SALT_HASH.match(value) or _CRYPT_STYLE.match(value) or _HEX_DIGEST.match(value)
    )


def classify_stored_password(stored):
    """'verifiable' (a hash this backend can check), 'other_hash' (a hash shape it cannot check, so the account
    cannot sign in until the password is reset), 'empty', or 'plaintext' (not a hash: a legacy plain-text
    password). Used by the read-only report tool."""
    value = str(stored or "").strip()
    if not value:
        return "empty"
    if _VERIFIABLE.match(value):
        return "verifiable"
    if looks_like_password_hash(value):
        return "other_hash"
    return "plaintext"


def _utf8(text):
    # "surrogatepass" so even a lone surrogate from JSON can be encoded instead of raising an error.
    return text.encode("utf-8", "surrogatepass")


def verify_password(stored, password):
    """-> (password_ok, stored_is_plaintext)

    stored_is_plaintext is True when the stored value is not a hash, whatever the result: the caller spends the
    same hashing time as for a real hash, and upgrades the stored value when password_ok is also True.
    Any typed text is accepted (Chinese, Malay, emoji ...); nothing here raises for odd input.
    """
    if not isinstance(password, str) or not password:
        return False, False

    stored_text = str(stored or "")
    if not stored_text.strip():
        return False, False

    if looks_like_password_hash(stored_text):
        from werkzeug.security import check_password_hash

        try:
            return bool(check_password_hash(stored_text.strip(), password)), False
        except Exception:
            # An unknown method or a malformed hash: it cannot be checked, so it is a wrong password.
            return False, False

    # Not a hash: a legacy plain-text password. Constant time, on bytes, so non-ASCII input never raises.
    return hmac.compare_digest(_utf8(stored_text), _utf8(password)), True

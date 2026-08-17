from dataclasses import dataclass

import jwt

from attendance.config import Settings


class AuthenticationError(Exception):
    """Raised when a caller cannot be authenticated."""


@dataclass(frozen=True)
class Principal:
    subject: str


def decode_access_token(token: str, settings: Settings) -> Principal:
    try:
        claims = jwt.decode(
            token,
            settings.jwt_secret.get_secret_value(),
            algorithms=["HS256"],
            audience=settings.jwt_audience,
            issuer=settings.jwt_issuer,
            options={"require": ["sub", "exp", "iat", "iss", "aud"]},
        )
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid access token") from exc

    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject.strip():
        raise AuthenticationError("Invalid access token")
    return Principal(subject=subject)

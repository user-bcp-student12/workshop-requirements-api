import os
from http import HTTPStatus

import jwt
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi import Header, HTTPException
from pydantic import BaseModel, Field, ValidationError

from app.schemas import Identity, JwtClaims

JWT_ALGORITHM = "RS256"
DEFAULT_JWT_ISSUER = "workshop-auth"
DEFAULT_JWT_AUDIENCE = "workshop-requirements-api"
AUTHENTICATION_ERROR = "Invalid token: authentication failed"
REQUIRED_JWT_CLAIMS = ["exp", "iss", "aud", "sub"]


class JwtSettings(BaseModel):
    public_key: str = Field(min_length=1)
    issuer: str = Field(min_length=1)
    audience: str = Field(min_length=1)

    @classmethod
    def from_environment(cls) -> "JwtSettings":
        return cls(
            public_key=os.getenv("WORKSHOP_JWT_PUBLIC_KEY", ""),
            issuer=os.getenv("WORKSHOP_JWT_ISSUER", DEFAULT_JWT_ISSUER),
            audience=os.getenv("WORKSHOP_JWT_AUDIENCE", DEFAULT_JWT_AUDIENCE),
        )


def bearer_token(authorization: str) -> str:
    parts = authorization.split()
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise jwt.InvalidTokenError(AUTHENTICATION_ERROR)
    return parts[1]


def verification_key(settings: JwtSettings) -> rsa.RSAPublicKey:
    public_key = serialization.load_pem_public_key(settings.public_key.encode("utf-8"))
    if not isinstance(public_key, rsa.RSAPublicKey):
        raise jwt.InvalidKeyError(AUTHENTICATION_ERROR)
    return public_key


def verified_claims(token: str, settings: JwtSettings) -> JwtClaims:
    public_key = verification_key(settings)
    try:
        decoded = jwt.decode(
            token, public_key, algorithms=[JWT_ALGORITHM], issuer=settings.issuer, audience=settings.audience,
            options={"require": REQUIRED_JWT_CLAIMS, "verify_signature": True, "verify_exp": True,
                     "verify_iss": True, "verify_aud": True, "verify_sub": True, "verify_nbf": True,
                     "verify_iat": True},
        )
    except (TypeError, OverflowError) as error:
        raise jwt.InvalidTokenError(AUTHENTICATION_ERROR) from error
    return JwtClaims.model_validate(decoded)


def verified_identity(authorization: str = Header(default="")) -> Identity:
    try:
        token = bearer_token(authorization)
        claims = verified_claims(token, JwtSettings.from_environment())
        return Identity(username=claims.username, role=claims.role)
    except (jwt.PyJWTError, ValidationError, ValueError, UnsupportedAlgorithm) as error:
        raise HTTPException(status_code=HTTPStatus.UNAUTHORIZED, detail=AUTHENTICATION_ERROR) from error
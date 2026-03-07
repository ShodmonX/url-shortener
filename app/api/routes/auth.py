from fastapi import APIRouter, Body, Depends, HTTPException, Request, Response, status
from fastapi.responses import ORJSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import rate_limit
from app.core.auth_cookies import clear_refresh_token_cookie, get_refresh_token_from_request, set_refresh_token_cookie
from app.core.config import settings
from app.db.session import get_db
from app.models import User
from app.schemas.auth import LoginRequest, LogoutRequest, RefreshTokenRequest, RegisterRequest, TokenPairResponse, UserResponse
from app.services.auth_service import AuthService, TokenPair
from app.services.exceptions import InactiveUserError, InvalidCredentialsError, InvalidRefreshTokenError, UserAlreadyExistsError
from app.utils.request import get_client_ip

router = APIRouter(prefix="/auth", tags=["auth"])


def build_invalid_refresh_response() -> ORJSONResponse:
    response = ORJSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"detail": "invalid or expired refresh token"},
        headers={"WWW-Authenticate": "Bearer"},
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    clear_refresh_token_cookie(response)
    return response


def build_token_response(user: User, token_pair: TokenPair) -> TokenPairResponse:
    return TokenPairResponse(
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token if settings.auth_return_refresh_token_in_body else None,
        access_token_expires_at=token_pair.access_token_expires_at,
        refresh_token_expires_at=token_pair.refresh_token_expires_at,
        user=UserResponse(
            id=user.public_id,
            email=user.email,
            created_at=user.created_at,
        ),
    )


@router.post(
    "/register",
    response_model=TokenPairResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register(
    payload: RegisterRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenPairResponse:
    service = AuthService(db)
    try:
        user, token_pair = await service.register(
            email=str(payload.email),
            password=payload.password,
            user_agent=request.headers.get("user-agent"),
            client_ip=get_client_ip(request),
        )
    except UserAlreadyExistsError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="email is already registered") from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    set_refresh_token_cookie(response, token_pair.refresh_token, token_pair.refresh_token_expires_at)
    return build_token_response(user, token_pair)


@router.post(
    "/login",
    response_model=TokenPairResponse,
    dependencies=[Depends(rate_limit("login", 30))],
)
async def login(
    payload: LoginRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> TokenPairResponse:
    service = AuthService(db)
    try:
        user, token_pair = await service.login(
            email=str(payload.email),
            password=payload.password,
            user_agent=request.headers.get("user-agent"),
            client_ip=get_client_ip(request),
        )
    except InvalidCredentialsError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    except InactiveUserError as exc:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="user account is inactive") from exc

    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    set_refresh_token_cookie(response, token_pair.refresh_token, token_pair.refresh_token_expires_at)
    return build_token_response(user, token_pair)


@router.post("/refresh", response_model=TokenPairResponse)
async def refresh_tokens(
    request: Request,
    response: Response,
    payload: RefreshTokenRequest | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
) -> TokenPairResponse:
    refresh_token = get_refresh_token_from_request(request, payload.refresh_token if payload is not None else None)
    if not refresh_token:
        return build_invalid_refresh_response()

    service = AuthService(db)
    try:
        user, token_pair = await service.refresh(
            refresh_token=refresh_token,
            user_agent=request.headers.get("user-agent"),
            client_ip=get_client_ip(request),
        )
    except InvalidRefreshTokenError:
        return build_invalid_refresh_response()

    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    set_refresh_token_cookie(response, token_pair.refresh_token, token_pair.refresh_token_expires_at)
    return build_token_response(user, token_pair)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    request: Request,
    payload: LogoutRequest | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
) -> Response:
    refresh_token = get_refresh_token_from_request(request, payload.refresh_token if payload is not None else None)
    if not refresh_token:
        return build_invalid_refresh_response()

    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    response.headers["Cache-Control"] = "no-store"
    response.headers["Pragma"] = "no-cache"
    service = AuthService(db)
    try:
        await service.logout(refresh_token=refresh_token)
    except InvalidRefreshTokenError:
        return build_invalid_refresh_response()
    clear_refresh_token_cookie(response)
    return response

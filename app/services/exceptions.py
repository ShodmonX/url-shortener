class ServiceError(Exception):
    pass


class AuthenticationError(ServiceError):
    pass


class AliasUnavailableError(ServiceError):
    pass


class LinkNotFoundError(ServiceError):
    pass


class LinkExpiredError(ServiceError):
    pass


class ManageTokenInvalidError(ServiceError):
    pass


class UserAlreadyExistsError(ServiceError):
    pass


class InvalidCredentialsError(AuthenticationError):
    pass


class InvalidAccessTokenError(AuthenticationError):
    pass


class InvalidRefreshTokenError(AuthenticationError):
    pass


class InactiveUserError(AuthenticationError):
    pass


class RateLimitExceededError(ServiceError):
    def __init__(self, retry_after_seconds: int) -> None:
        self.retry_after_seconds = retry_after_seconds
        super().__init__(f"rate limit exceeded, retry in {retry_after_seconds} seconds")

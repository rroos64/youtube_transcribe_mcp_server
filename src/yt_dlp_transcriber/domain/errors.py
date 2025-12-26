class AppError(Exception):
    """Base error for application/domain failures."""


class InvalidSessionId(ValueError, AppError):
    pass


class InvalidItemId(ValueError, AppError):
    pass


class NotFoundError(ValueError, AppError):
    pass


class ExpiredItemError(ValueError, AppError):
    pass


class ExternalCommandError(RuntimeError, AppError):
    pass

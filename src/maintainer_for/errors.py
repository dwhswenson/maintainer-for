class UserNotFoundError(Exception):
    def __init__(self, source: str, username: str) -> None:
        self.source = source
        self.username = username
        super().__init__(f"{source} user not found: {username}")


class UpstreamServiceError(Exception):
    def __init__(self, source: str, message: str) -> None:
        self.source = source
        self.message = message
        super().__init__(message)

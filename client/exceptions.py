class RemoteAPIError(Exception):
    """Base exception for all IntelliCodeX Remote API errors."""
    pass

class AuthenticationError(RemoteAPIError):
    """Raised when authentication fails (401) or credentials are invalid."""
    pass

class NotFoundError(RemoteAPIError):
    """Raised when a requested resource (Project, Repository, etc.) is not found (404)."""
    pass

class ValidationError(RemoteAPIError):
    """Raised when the server rejects the request format (422/400)."""
    pass

class ServerError(RemoteAPIError):
    """Raised when the server encounters an internal error (500+)."""
    pass

class ConnectionError(RemoteAPIError):
    """Raised when the client cannot connect to the server."""
    pass

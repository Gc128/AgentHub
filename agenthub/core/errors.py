from pydantic import BaseModel


class ErrorResponse(BaseModel):
    code: str
    message: str


class AgentHubError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class NotFoundError(AgentHubError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code=code, message=message, status_code=404)


class BadRequestError(AgentHubError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code=code, message=message, status_code=400)


class AgentExecutionError(AgentHubError):
    def __init__(self, message: str) -> None:
        super().__init__(code="agent_execution_failed", message=message, status_code=502)

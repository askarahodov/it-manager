from pydantic import BaseModel, field_validator


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator("email")
    @classmethod
    def allow_internal_domains(cls, value: str) -> str:
        """Принимаем внутренние домены (it.local и т.п.), без строгой проверки RFC."""
        value = value.strip()
        if "@" not in value:
            raise ValueError("email должен содержать @")
        return value


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

from pydantic import BaseModel, Field


class TerminalConnectRequest(BaseModel):
    host_id: int = Field(..., ge=1)

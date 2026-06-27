from pydantic       import BaseModel

class TimeoutConfig(BaseModel):
    connect   : float
    read      : float
    write     : float
    pool      : float
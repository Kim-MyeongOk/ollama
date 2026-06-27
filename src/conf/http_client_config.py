from pydantic            import BaseModel
from conf.timeout_config import TimeoutConfig

class HttpClientConfig(BaseModel):
    max_connections           : int
    max_keepalive_connections : int
    keepalive_expiry          : int
    timeout                   : TimeoutConfig
    verify                    : bool
    trust_env                 : bool
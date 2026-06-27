from pydantic                import BaseModel
from conf.server_config      import ServerConfig
from conf.ollama_config      import OllamaConfig
from conf.http_client_config import HttpClientConfig

class Config(BaseModel):
    server          : ServerConfig
    ollama          : OllamaConfig
    http_client     : HttpClientConfig
    logging         : dict
    unicorn_logging : dict
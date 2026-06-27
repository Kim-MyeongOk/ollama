from pydantic import BaseModel

class OllamaConfig(BaseModel):
    base_url  : str
    api_key   : str
    model     : str
    timeout   : int
    streaming : bool
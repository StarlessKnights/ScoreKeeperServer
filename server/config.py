from pydantic_settings import BaseSettings

class Config(BaseSettings):
    desired_scorekeepers: int = 0
    
    model_config = {"env_file": ".env"}
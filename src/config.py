# ── 설정 로드 ─────────────────────────────────────────────────
import yaml
import logging
from logging.config import dictConfig as DictConfig
from conf.config    import Config

def load_config(path : str) -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)

yaml_path   = "./env/server.yaml"
yaml_config = load_config(yaml_path)
cfg         = Config(**yaml_config)

DictConfig(cfg.logging)
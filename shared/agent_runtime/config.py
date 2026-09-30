from shared.agent.config import agent_config_dir
from shared.yaml_config import load_catalog_config


def config():
    return load_catalog_config(str(agent_config_dir()), "architecture")


def enabled():
    return config().get("enabled") is True

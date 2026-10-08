"""配置加载器。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from parser_engine.core.logger import logger


class ConfigLoader:
    """读取 YAML/JSON 配置。"""

    def __init__(self, config_root: str | Path = "configs"):
        """初始化配置加载器。

        Args:
            config_root: 配置根目录。
        """
        self.config_root = Path(config_root)

    def load_yaml(self, relative_path: str) -> dict[str, Any]:
        """读取 YAML 配置。

        Args:
            relative_path: 相对 `config_root` 的配置路径。

        Returns:
            dict[str, Any]: 配置内容。
        """
        path = self.config_root / relative_path
        if not path.exists():
            logger.warning(f"配置文件不存在，返回空配置：{path}")
            return {}
        try:
            import yaml
        except Exception as exc:  # pragma: no cover
            raise RuntimeError("读取 YAML 配置需要安装 pyyaml") from exc
        with path.open("r", encoding="utf-8") as file:
            data = yaml.safe_load(file) or {}
        logger.info(f"已加载配置：{path}")
        return data

    def load_json(self, relative_path: str) -> dict[str, Any]:
        """读取 JSON 配置。

        Args:
            relative_path: 相对 `config_root` 的配置路径。

        Returns:
            dict[str, Any]: 配置内容。
        """
        path = self.config_root / relative_path
        if not path.exists():
            logger.warning(f"配置文件不存在，返回空配置：{path}")
            return {}
        with path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def load_field_configs(self) -> dict[str, dict[str, Any]]:
        """加载全部字段配置。

        Returns:
            dict[str, dict[str, Any]]: 以字段编码为 key 的字段配置。
        """
        fields_dir = self.config_root / "fields"
        all_fields: dict[str, dict[str, Any]] = {}
        if not fields_dir.exists():
            logger.warning(f"字段配置目录不存在：{fields_dir}")
            return all_fields
        for path in sorted(fields_dir.glob("*.yaml")):
            data = self.load_yaml(str(Path("fields") / path.name))
            for code, config in (data.get("fields") or {}).items():
                config["code"] = code
                config["config_path"] = str(self.config_root / "fields" / path.name)
                all_fields[code] = config
        logger.info(f"字段配置加载完成，共 {len(all_fields)} 个字段")
        return all_fields

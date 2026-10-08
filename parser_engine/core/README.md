# core

核心编排层，负责创建解析服务、加载配置、执行流水线和记录日志。

## 文件职责

| 文件 | 作用 |
|---|---|
| `factory.py` | 读取配置并装配默认解析器 |
| `pipeline.py` | 定义完整解析流程和模块调用顺序 |
| `service.py` | 对外解析服务封装 |
| `context.py` | 单次解析过程的上下文数据 |
| `config_loader.py` | YAML 配置读取和字段配置合并 |
| `logger.py` | 日志对象 |

业务系统通常只需要从 `main.py` 或 `factory.py` 创建 parser，不直接实例化各个底层模块。

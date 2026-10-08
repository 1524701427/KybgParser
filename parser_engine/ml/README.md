# ml

模型适配器目录。这里放不直接属于业务规则的模型封装。

## 当前模块

| 文件 | 作用 |
|---|---|
| `embedding_model.py` | BGE embedding 匹配器，支持批量、内存感知和释放模型 |
| `ranker_model.py` | 候选排序模型预留 |
| `entity_model.py` | 实体抽取模型预留 |
| `heading_model.py` | 标题分类模型预留 |

Reranker/NLI 当前放在 `semantic/semantic_verifier.py`，因为它们直接服务于候选语义验证。

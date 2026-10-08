# data

用于放预测输出、日志、调试图片、评估产物和人工核对报告。样例 Word/PDF 文档统一放在项目根目录的 `samples/`。

解析器可以处理任意传入的 Word/PDF 路径，不要求输入文件一定放在项目目录中。

## 建议结构

```text
data/
  predictions/             解析器输出 JSON
  reports/                 对比报告和核对报告
  logs/                    本地运行日志
  debug-images/            OCR 调试图片
  opendataloader_probe/    PDF 结构探针输出
```

## 预测输出

`JsonExporter` 默认写出两个文件：

- `*_result.json`：业务结果，只包含 `filePath` 和按模块组织的 `sections`。
- `*_details.json`：核对结果，包含按章节组织的字段过程、来源证据、debug 信息、字段编码索引和流水线计数。

人工核对“值从哪来、怎么被选中、是否有计算/覆盖过程”时，优先看 `*_details.json`。

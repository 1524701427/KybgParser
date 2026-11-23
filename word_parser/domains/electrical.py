"""电气专业规则的稳定组合入口。

集电线路、电气一次和电气二次按业务职责拆分；公共方法名与 ResultBuilder 的
原有调用方式保持不变。
"""

from __future__ import annotations

from word_parser.domains.electrical_collector import CollectorLineRulesMixin
from word_parser.domains.electrical_primary import ElectricalPrimaryRulesMixin
from word_parser.domains.electrical_secondary import ElectricalSecondaryRulesMixin


class ElectricalRulesMixin(
    CollectorLineRulesMixin,
    ElectricalSecondaryRulesMixin,
    ElectricalPrimaryRulesMixin,
):
    """组合电气专业规则，保持 ResultBuilder 的原有继承入口。"""

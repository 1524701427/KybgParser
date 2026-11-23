"""风资源专业规则的稳定组合入口。

测风塔汇总、风向、空气密度和最终资源覆盖规则按职责拆分；原有方法名、共享状态
和 ResultBuilder 调用顺序保持不变。
"""

from __future__ import annotations

from word_parser.domains.wind_resource_density import WindDensityRulesMixin
from word_parser.domains.wind_resource_direction import WindDirectionRulesMixin
from word_parser.domains.wind_resource_overrides import WindResourceOverrideRulesMixin
from word_parser.domains.wind_resource_summary import WindResourceSummaryRulesMixin


class WindResourceRulesMixin(
    WindResourceSummaryRulesMixin,
    WindDirectionRulesMixin,
    WindDensityRulesMixin,
    WindResourceOverrideRulesMixin,
):
    """组合风资源专业规则，保持 ResultBuilder 的原有继承入口。"""

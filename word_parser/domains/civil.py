"""土建专业规则的稳定组合入口。

道路、基础、升压站土建、土石方和用地规则按业务职责拆分；原方法名、调用顺序
与 ResultBuilder 公共入口保持不变。
"""

from __future__ import annotations

from word_parser.domains.civil_earthwork import EarthworkRulesMixin
from word_parser.domains.civil_foundation import WindFoundationRulesMixin
from word_parser.domains.civil_land import LandAreaRulesMixin
from word_parser.domains.civil_roads import CivilRoadRulesMixin
from word_parser.domains.civil_substation import SubstationCivilRulesMixin


class CivilRulesMixin(
    CivilRoadRulesMixin,
    WindFoundationRulesMixin,
    SubstationCivilRulesMixin,
    EarthworkRulesMixin,
    LandAreaRulesMixin,
):
    """组合土建专业规则，保持 ResultBuilder 的原有继承入口。"""

"""`Benefit`, one reward of a drop, and `BenefitType`, the kind of reward."""
from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from constants import URLType

if TYPE_CHECKING:
    from constants import JsonType


class BenefitType(Enum):
    UNKNOWN = "UNKNOWN"
    BADGE = "BADGE"
    EMOTE = "EMOTE"
    DIRECT_ENTITLEMENT = "DIRECT_ENTITLEMENT"

    def is_badge_or_emote(self) -> bool:
        return self in (BenefitType.BADGE, BenefitType.EMOTE)


class Benefit:
    __slots__ = ("id", "name", "type", "image_url")

    def __init__(self, data: JsonType):
        benefit_data: JsonType = data["benefit"]
        self.id: str = benefit_data["id"]
        self.name: str = benefit_data["name"]
        self.type: BenefitType = (
            BenefitType(benefit_data["distributionType"])
            if benefit_data["distributionType"] in BenefitType.__members__.keys()
            else BenefitType.UNKNOWN
        )
        self.image_url: URLType = benefit_data["imageAssetURL"]

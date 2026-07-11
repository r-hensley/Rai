"""Rai's server-rendered administration website."""

from .config import (
    SPANISH_GUILD_ID,
    SPANISH_STAFF_ROLES_LOW_TO_HIGH,
)
from .site import WebAdminSite

__all__ = (
    "SPANISH_GUILD_ID",
    "SPANISH_STAFF_ROLES_LOW_TO_HIGH",
    "WebAdminSite",
)

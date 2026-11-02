"""Channel adapters for tracer delivery.

``ChannelAdapter`` is the seam between the tracer engine and whatever
actually delivers messages:

- ``SimulatedWhatsApp`` / ``SimulatedIVR``: the demo adapters — delivery is
  instant and local (the message already lives in the DB and the UI renders
  it), so ``send`` simply logs and succeeds.
- ``TwilioWhatsAppAdapter`` / ``MetaCloudAdapter``: stubs for the real
  gateways, selected via ``TRACER_PROVIDER=twilio|meta``. They raise on
  construction until the credentials/integration land, so misconfiguration
  fails loudly instead of silently dropping tracers.

The factory is the only thing the engine talks to; adapters are resolved
per follow-up channel.
"""

import logging
from abc import ABC, abstractmethod
from uuid import UUID

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class ChannelAdapter(ABC):
    """Delivery adapter for one tracer channel."""

    channel: str = ""

    @abstractmethod
    async def send(self, *, to_user_id: UUID, to_phone: str | None, message: str) -> None:
        """Deliver one message. Raises on failure so the engine can retry."""


class SimulatedWhatsApp(ChannelAdapter):
    """Simulated WhatsApp gateway: delivery is instant and local."""

    channel = "WHATSAPP"

    async def send(self, *, to_user_id: UUID, to_phone: str | None, message: str) -> None:
        logger.info(
            "[simulated WhatsApp] to user %s (%s): %s", to_user_id, to_phone or "no phone", message
        )


class SimulatedIVR(ChannelAdapter):
    """Simulated IVR gateway: the call is rendered as a keypad card in the UI."""

    channel = "IVR"

    async def send(self, *, to_user_id: UUID, to_phone: str | None, message: str) -> None:
        logger.info("[simulated IVR] call to user %s (%s): %s", to_user_id, to_phone, message)


class SimulatedSMS(ChannelAdapter):
    """Simulated SMS gateway."""

    channel = "SMS"

    async def send(self, *, to_user_id: UUID, to_phone: str | None, message: str) -> None:
        logger.info("[simulated SMS] to user %s (%s): %s", to_user_id, to_phone, message)


class TwilioWhatsAppAdapter(ChannelAdapter):
    """Stub for the real Twilio WhatsApp Business API integration."""

    channel = "WHATSAPP"

    async def send(self, *, to_user_id: UUID, to_phone: str | None, message: str) -> None:
        raise NotImplementedError(
            "Twilio WhatsApp delivery is not implemented yet. Set TRACER_PROVIDER=simulated "
            "for the demo, or implement app/services/tracer_channels.py."
        )


class MetaCloudAdapter(ChannelAdapter):
    """Stub for the real Meta WhatsApp Cloud API integration."""

    channel = "WHATSAPP"

    async def send(self, *, to_user_id: UUID, to_phone: str | None, message: str) -> None:
        raise NotImplementedError(
            "Meta WhatsApp Cloud delivery is not implemented yet. Set TRACER_PROVIDER=simulated "
            "for the demo, or implement app/services/tracer_channels.py."
        )


_SIMULATED = {
    "WHATSAPP": SimulatedWhatsApp(),
    "IVR": SimulatedIVR(),
    "SMS": SimulatedSMS(),
}


def get_adapter(channel: str) -> ChannelAdapter:
    """Resolve the adapter for a channel honouring TRACER_PROVIDER."""
    settings = get_settings()
    provider = settings.tracer_provider.lower()
    if provider == "simulated":
        try:
            return _SIMULATED[channel]
        except KeyError as exc:
            raise ValueError(f"Unknown tracer channel '{channel}'") from exc
    if provider == "twilio":
        if channel == "WHATSAPP":
            return TwilioWhatsAppAdapter()
        return _SIMULATED[channel]
    if provider == "meta":
        if channel == "WHATSAPP":
            return MetaCloudAdapter()
        return _SIMULATED[channel]
    raise ValueError(f"Unknown TRACER_PROVIDER '{provider}' (use simulated|twilio|meta)")

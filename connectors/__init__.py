from .base import Balance, Connector, MissingCredentials, NotSupported, Settlement, Txn
from .lipad import LipadConnector
from .paystack import PaystackConnector
from .pending import LetknowConnector, Pay247Connector

REGISTRY: dict[str, type[Connector]] = {c.code: c for c in (
    LipadConnector, PaystackConnector, Pay247Connector, LetknowConnector,
)}

__all__ = ["REGISTRY", "Connector", "Txn", "Balance", "Settlement", "MissingCredentials", "NotSupported"]

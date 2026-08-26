"""Communication channels: the provider-agnostic layer plus its drivers.

Deliberately empty of re-exports. ``service`` imports ``registry``, which
imports every driver module in this package, so pulling names up into this
``__init__`` would make the package import itself mid-initialisation. Import
what you need directly:

    from app.services.channels import service as svc
    from app.services.channels.registry import get_driver
"""

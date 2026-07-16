"""Standalone MegaBrain Vault integration for Hermes."""

from . import runtime, schemas


def register(ctx):
    runtime.register(ctx, schemas.MEGABRAIN_VAULT)

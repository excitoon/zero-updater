"""Lazy loader for compiled Flipper protobuf modules."""

from __future__ import annotations

_pb2 = None


def get_pb2():
    """Return the compiled flipper_pb2 module."""
    global _pb2
    if _pb2 is None:
        from zero_updater.proto import flipper_pb2
        _pb2 = flipper_pb2
    return _pb2

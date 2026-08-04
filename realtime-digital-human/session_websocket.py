from typing import Any, Dict, Tuple


def websocket_is_open(ws: Any) -> bool:
    """WebSocketResponse is a mapping, so bool(ws) does not mean it is open."""
    return ws is not None and not bool(getattr(ws, "closed", False))


def claim_websocket(
    sockets: Dict[str, Any],
    epochs: Dict[str, int],
    sessionid: str,
    ws: Any,
) -> Tuple[Any, int]:
    """Install a socket and return the previous socket plus an ownership epoch."""
    epoch = epochs.get(sessionid, 0) + 1
    previous = sockets.get(sessionid)
    epochs[sessionid] = epoch
    sockets[sessionid] = ws
    return previous, epoch


def release_websocket(
    sockets: Dict[str, Any],
    epochs: Dict[str, int],
    sessionid: str,
    ws: Any,
    epoch: int,
) -> bool:
    """Remove a socket only when the caller still owns the session slot."""
    if epochs.get(sessionid) != epoch or sockets.get(sessionid) is not ws:
        return False
    sockets.pop(sessionid, None)
    return True


def invalidate_websocket(
    sockets: Dict[str, Any],
    epochs: Dict[str, int],
    sessionid: str,
) -> Any:
    """Invalidate pending cleanup work and detach the current socket."""
    epochs[sessionid] = epochs.get(sessionid, 0) + 1
    return sockets.pop(sessionid, None)


def websocket_epoch_matches(
    epochs: Dict[str, int], sessionid: str, epoch: int
) -> bool:
    return epochs.get(sessionid) == epoch

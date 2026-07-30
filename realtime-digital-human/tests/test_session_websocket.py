import unittest

from session_websocket import (
    claim_websocket,
    invalidate_websocket,
    release_websocket,
    websocket_epoch_matches,
    websocket_is_open,
)


class FakeWebSocket:
    def __init__(self, *, closed=False):
        self.closed = closed

    def __len__(self):
        return 0


class SessionWebSocketTests(unittest.TestCase):
    def test_mapping_truthiness_does_not_define_socket_readiness(self):
        ws = FakeWebSocket()

        self.assertFalse(bool(ws))
        self.assertTrue(websocket_is_open(ws))
        self.assertFalse(websocket_is_open(FakeWebSocket(closed=True)))
        self.assertFalse(websocket_is_open(None))

    def test_old_socket_cannot_remove_replacement(self):
        sockets = {}
        epochs = {}
        old_ws = FakeWebSocket()
        new_ws = FakeWebSocket()

        _, old_epoch = claim_websocket(sockets, epochs, "session-1", old_ws)
        previous, new_epoch = claim_websocket(
            sockets, epochs, "session-1", new_ws
        )

        self.assertIs(previous, old_ws)
        self.assertFalse(
            release_websocket(
                sockets, epochs, "session-1", old_ws, old_epoch
            )
        )
        self.assertIs(sockets["session-1"], new_ws)
        self.assertTrue(
            release_websocket(
                sockets, epochs, "session-1", new_ws, new_epoch
            )
        )
        self.assertNotIn("session-1", sockets)

    def test_invalidate_makes_delayed_cleanup_stale(self):
        sockets = {}
        epochs = {}
        ws = FakeWebSocket()

        _, epoch = claim_websocket(sockets, epochs, "session-1", ws)
        detached = invalidate_websocket(sockets, epochs, "session-1")

        self.assertIs(detached, ws)
        self.assertNotIn("session-1", sockets)
        self.assertFalse(websocket_epoch_matches(epochs, "session-1", epoch))


if __name__ == "__main__":
    unittest.main()

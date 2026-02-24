"""OPC UA client wrapper running in a dedicated QThread.

Provides connection management, cyclic reading, and automatic reconnection
for OPC UA communication with Siemens S7-1200/1500 PLCs.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time

from asyncua import Client as OpcuaClient
from asyncua import ua
from PySide6.QtCore import QMutex, QThread, Signal

logger = logging.getLogger(__name__)

# Reconnect interval in seconds
_RECONNECT_INTERVAL = 5.0


class OpcuaWorker(QThread):
    """Worker thread for OPC UA (asyncua) communication.

    Runs its own asyncio event loop internally so that the Qt GUI thread
    is never blocked by network I/O.

    Signals:
        connected: Emitted when connection is established.
        disconnected: Emitted when connection is lost.
        values_read: Emitted with list of (row_index, value_str, error_str) tuples.
        log_message: Emitted with log text for the UI log panel.
    """

    connected = Signal()
    disconnected = Signal()
    values_read = Signal(list)  # list[tuple[int, str, str]]
    log_message = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._mutex = QMutex()
        self._running = False
        self._cyclic = False
        self._interval_ms = 1000
        self._url = ""
        self._username = ""
        self._password = ""
        self._nodes: list[dict[str, str]] = []
        self._should_connect = False
        self._should_disconnect = False

    # ---- Public API (called from GUI thread) ----

    def request_connect(self, url: str, username: str = "", password: str = "") -> None:
        """Request connection to OPC UA server."""
        self._mutex.lock()
        self._url = url
        self._username = username
        self._password = password
        self._should_connect = True
        self._mutex.unlock()

    def request_disconnect(self) -> None:
        """Request disconnection from OPC UA server."""
        self._mutex.lock()
        self._should_disconnect = True
        self._mutex.unlock()

    def set_cyclic(self, active: bool, interval_ms: int) -> None:
        """Enable or disable cyclic reading."""
        self._mutex.lock()
        self._cyclic = active
        self._interval_ms = max(250, min(5000, interval_ms))
        self._mutex.unlock()

    def set_nodes(self, nodes: list[dict[str, str]]) -> None:
        """Update node definitions from the UI table."""
        self._mutex.lock()
        self._nodes = list(nodes)
        self._mutex.unlock()

    def stop(self) -> None:
        """Stop the worker thread gracefully."""
        self._mutex.lock()
        self._running = False
        self._mutex.unlock()
        self.wait(5000)

    # ---- Thread run loop (with internal asyncio loop) ----

    def run(self) -> None:
        """Create a private asyncio event loop and run the main worker coroutine."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._async_main())
        finally:
            loop.close()

    async def _async_main(self) -> None:  # noqa: C901
        """Async main loop – handles connect/disconnect/read requests."""
        self._running = True
        client: OpcuaClient | None = None
        is_connected = False
        last_reconnect = 0.0

        while self._running:
            self._mutex.lock()
            should_connect = self._should_connect
            should_disconnect = self._should_disconnect
            cyclic = self._cyclic
            interval_ms = self._interval_ms
            nodes = list(self._nodes)
            url = self._url
            username = self._username
            password = self._password
            self._should_connect = False
            self._should_disconnect = False
            self._mutex.unlock()

            # Handle disconnect
            if should_disconnect and is_connected and client is not None:
                with contextlib.suppress(Exception):
                    await client.disconnect()
                is_connected = False
                client = None
                self.disconnected.emit()
                self.log_message.emit("🔌 Disconnected from OPC UA server.")

            # Handle connect
            if should_connect:
                client, is_connected = await self._do_connect(url, username, password)
                if is_connected:
                    last_reconnect = 0.0

            # Auto-reconnect
            if not is_connected and not should_connect and cyclic and url:
                now = time.monotonic()
                if now - last_reconnect >= _RECONNECT_INTERVAL:
                    last_reconnect = now
                    self.log_message.emit("🔄 Attempting OPC UA auto-reconnect...")
                    client, is_connected = await self._do_connect(url, username, password)

            # Cyclic read
            if is_connected and cyclic and nodes and client is not None:
                try:
                    results = await self._read_all(client, nodes)
                    self.values_read.emit(results)
                except Exception as exc:
                    self.log_message.emit(f"❌ Read batch error: {exc}")
                    is_connected = False
                    self.disconnected.emit()
                    with contextlib.suppress(Exception):
                        await client.disconnect()
                    client = None

            # Sleep
            sleep_s = (interval_ms if cyclic else 200) / 1000.0
            await asyncio.sleep(sleep_s)

        # Cleanup
        if is_connected and client is not None:
            with contextlib.suppress(Exception):
                await client.disconnect()

    async def _do_connect(
        self, url: str, username: str, password: str
    ) -> tuple[OpcuaClient | None, bool]:
        """Attempt connection to the OPC UA server."""
        try:
            client = OpcuaClient(url=url)
            if username:
                client.set_user(username)
                client.set_password(password)

            # Set security policy to None for basic connections
            await client.connect()
            self.connected.emit()
            self.log_message.emit(f"✅ Connected to OPC UA server: {url}")
            return client, True
        except Exception as exc:
            self.disconnected.emit()
            self.log_message.emit(f"❌ OPC UA connection error: {exc}")
            return None, False

    async def _read_all(
        self, client: OpcuaClient, nodes: list[dict[str, str]]
    ) -> list[tuple[int, str, str]]:
        """Read all configured node IDs, returning per-row results."""
        results: list[tuple[int, str, str]] = []

        for idx, node_cfg in enumerate(nodes):
            node_id = node_cfg.get("node_id", "").strip()
            if not node_id:
                results.append((idx, "", ""))
                continue

            try:
                node = client.get_node(node_id)
                value = await node.read_value()
                # Format value nicely
                if isinstance(value, float):
                    value_str = f"{value:.6f}"
                elif isinstance(value, bool):
                    value_str = str(value)
                else:
                    value_str = str(value)
                results.append((idx, value_str, ""))
            except ua.UaStatusCodeError as exc:
                results.append((idx, "", f"UA Error: {exc}"))
            except Exception as exc:
                results.append((idx, "", str(exc)))

        return results


# ---------------------------------------------------------------------------
# Standalone browse worker – connects, browses, disconnects
# ---------------------------------------------------------------------------

class BrowseWorker(QThread):
    """Worker thread that browses the OPC UA server address space.

    Connects to the server, recursively browses child nodes up to a
    configurable depth, and emits the results as a nested structure.

    Signals:
        browse_done: Emitted with list of node dicts (recursive children).
        browse_error: Emitted with error message string.
        log_message: Emitted with log text for the UI log panel.
    """

    browse_done = Signal(list)   # list[dict] with keys: node_id, name, children
    browse_error = Signal(str)
    log_message = Signal(str)

    MAX_DEPTH = 5
    MAX_CHILDREN = 200  # safety limit per level

    def __init__(
        self,
        url: str,
        username: str = "",
        password: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self._url = url
        self._username = username
        self._password = password

    def run(self) -> None:
        """Run the browse operation in a private asyncio loop."""
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._browse())
        finally:
            loop.close()

    async def _browse(self) -> None:
        """Connect, browse, and disconnect."""
        client = OpcuaClient(url=self._url)
        if self._username:
            client.set_user(self._username)
            client.set_password(self._password)

        try:
            self.log_message.emit("🔍 Connecting for browse...")
            await client.connect()
        except Exception as exc:
            self.browse_error.emit(f"Connection failed: {exc}")
            return

        try:
            self.log_message.emit("🌳 Browsing address space...")
            objects_node = client.nodes.objects
            tree = await self._browse_node(objects_node, depth=0)
            self.browse_done.emit(tree)
            self.log_message.emit("✅ Browse complete.")
        except Exception as exc:
            self.browse_error.emit(f"Browse failed: {exc}")
        finally:
            with contextlib.suppress(Exception):
                await client.disconnect()

    async def _browse_node(self, node, depth: int) -> list[dict]:
        """Recursively browse children of a node.

        Returns:
            List of dicts: ``{"node_id": str, "name": str, "children": list}``.
        """
        if depth >= self.MAX_DEPTH:
            return []

        try:
            children = await node.get_children()
        except Exception:
            return []

        results = []
        for i, child in enumerate(children):
            if i >= self.MAX_CHILDREN:
                results.append({
                    "node_id": "",
                    "name": f"... ({len(children) - i} more nodes)",
                    "children": [],
                })
                break

            try:
                name = (await child.read_display_name()).Text
                node_id = child.nodeid.to_string()

                # Only recurse into non-variable nodes (Objects / Folders),
                # but still include variables as leaf nodes.
                node_class = await child.read_node_class()
                if node_class == ua.NodeClass.Variable:
                    sub_children = []
                else:
                    sub_children = await self._browse_node(child, depth + 1)

                results.append({
                    "node_id": node_id,
                    "name": name or node_id,
                    "children": sub_children,
                    "is_variable": node_class == ua.NodeClass.Variable,
                })
            except Exception:
                continue

        return results


import queue
from queue import Queue

from onyx.server.query_and_chat.placement import Placement
from onyx.server.query_and_chat.streaming_models import Packet


class Emitter:
    """Routes packets produced during tool and LLM execution to the right destination.

    Operates in one of two modes determined by whether ``merged_queue`` is supplied:

    **Standalone** (no ``merged_queue``): packets land on ``self.bus``. Used by tests,
        custom tools, and any caller that reads the emitter directly after execution.

    **Streaming** (``merged_queue`` provided): packets are tagged with ``model_index``
        and placed as ``(key, packet)`` tuples on the shared queue for the
        ``_run_models`` drain loop to consume and yield downstream.

    Attributes:
        bus: Fallback queue for standalone mode. Always created so existing callers
            (tests, eval harnesses, custom-tool scripts) work without modification.

    Args:
        model_idx: Index embedded in packet placements. Pass ``None`` for single-model
            runs to preserve the backwards-compatible wire format (``model_index=None``
            in the packet); pass an integer for each model in a multi-model run.
        merged_queue: Shared queue owned by the ``_run_models`` drain loop. When set,
            all ``emit()`` calls route here instead of ``self.bus``.

    Example::

        # Standalone — read from bus after the fact (tests, evals)
        emitter = Emitter()
        emitter.emit(packet)
        result = emitter.bus.get()

        # Streaming — wired into _run_models (production path)
        emitter = Emitter(model_idx=0, merged_queue=merged_queue)
        emitter.emit(packet)  # places (0, tagged_packet) on merged_queue
    """

    def __init__(
        self,
        model_idx: int | None = None,
        merged_queue: "queue.Queue | None" = None,
    ) -> None:
        self._model_idx = model_idx
        self._merged_queue = merged_queue
        # Always created for backwards compatibility (tests, custom_tool, customer scripts, etc.)
        self.bus: Queue[Packet] = Queue()

    def emit(self, packet: Packet) -> None:
        """Emit a packet, routing it to the merged queue or the local bus.

        In streaming mode, stamps the packet's placement with ``model_index`` before
        forwarding so the drain loop can attribute it to the correct model. In
        standalone mode, places the packet on ``self.bus`` unchanged.

        Args:
            packet: The packet to emit.
        """
        if self._merged_queue is not None:
            tagged_placement = Placement(
                turn_index=packet.placement.turn_index if packet.placement else 0,
                tab_index=packet.placement.tab_index if packet.placement else 0,
                sub_turn_index=(
                    packet.placement.sub_turn_index if packet.placement else None
                ),
                model_index=self._model_idx,
            )
            tagged_packet = Packet(placement=tagged_placement, obj=packet.obj)
            key = self._model_idx if self._model_idx is not None else 0
            self._merged_queue.put((key, tagged_packet))
        else:
            self.bus.put(packet)


def get_default_emitter() -> Emitter:
    return Emitter()

"""Unit tests for the Emitter class.

Covers both modes (standalone and streaming) without any real database,
LLM, or queue infrastructure beyond the stdlib Queue.
"""

from onyx.chat.emitter import Emitter
from onyx.chat.emitter import get_default_emitter
from onyx.server.query_and_chat.placement import Placement
from onyx.server.query_and_chat.streaming_models import OverallStop
from onyx.server.query_and_chat.streaming_models import Packet
from onyx.server.query_and_chat.streaming_models import ReasoningStart


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _placement(
    turn_index: int = 0,
    tab_index: int = 0,
    sub_turn_index: int | None = None,
) -> Placement:
    return Placement(
        turn_index=turn_index,
        tab_index=tab_index,
        sub_turn_index=sub_turn_index,
    )


def _packet(
    turn_index: int = 0,
    tab_index: int = 0,
    sub_turn_index: int | None = None,
) -> Packet:
    """Build a minimal valid packet with an OverallStop payload."""
    return Packet(
        placement=_placement(turn_index, tab_index, sub_turn_index),
        obj=OverallStop(stop_reason="test"),
    )


# ---------------------------------------------------------------------------
# Standalone mode (no merged_queue)
# ---------------------------------------------------------------------------


class TestEmitterStandaloneMode:
    def test_emitted_packet_arrives_on_bus(self) -> None:
        emitter = Emitter()
        pkt = _packet()
        emitter.emit(pkt)
        assert emitter.bus.get_nowait() is pkt

    def test_bus_is_empty_before_emit(self) -> None:
        emitter = Emitter()
        assert emitter.bus.empty()

    def test_multiple_packets_delivered_fifo(self) -> None:
        emitter = Emitter()
        p1 = _packet(turn_index=0)
        p2 = _packet(turn_index=1)
        emitter.emit(p1)
        emitter.emit(p2)
        assert emitter.bus.get_nowait() is p1
        assert emitter.bus.get_nowait() is p2

    def test_packet_not_modified(self) -> None:
        """Standalone mode must not wrap or mutate the packet."""
        emitter = Emitter()
        pkt = _packet(turn_index=7, tab_index=3)
        emitter.emit(pkt)
        retrieved = emitter.bus.get_nowait()
        assert retrieved.placement.turn_index == 7
        assert retrieved.placement.tab_index == 3

    def test_get_default_emitter_is_standalone(self) -> None:
        emitter = get_default_emitter()
        pkt = _packet()
        emitter.emit(pkt)
        # Packet lands on the bus, not a shared queue
        assert emitter.bus.get_nowait() is pkt


# ---------------------------------------------------------------------------
# Streaming mode (merged_queue provided)
# ---------------------------------------------------------------------------


class TestEmitterStreamingMode:
    # --- Queue routing ---

    def test_packet_goes_to_merged_queue_not_bus(self) -> None:
        import queue

        mq: queue.Queue = queue.Queue()
        emitter = Emitter(model_idx=0, merged_queue=mq)
        emitter.emit(_packet())
        assert not mq.empty()
        assert emitter.bus.empty()

    def test_queue_item_is_tuple_of_key_and_packet(self) -> None:
        import queue

        mq: queue.Queue = queue.Queue()
        emitter = Emitter(model_idx=1, merged_queue=mq)
        emitter.emit(_packet())
        item = mq.get_nowait()
        assert isinstance(item, tuple)
        assert len(item) == 2

    # --- model_index tagging ---

    def test_model_idx_none_preserves_model_index_none(self) -> None:
        """N=1 backwards-compat: model_index must stay None in the packet."""
        import queue

        mq: queue.Queue = queue.Queue()
        emitter = Emitter(model_idx=None, merged_queue=mq)
        emitter.emit(_packet())
        _key, tagged = mq.get_nowait()
        assert tagged.placement.model_index is None

    def test_model_idx_zero_tags_packet(self) -> None:
        import queue

        mq: queue.Queue = queue.Queue()
        emitter = Emitter(model_idx=0, merged_queue=mq)
        emitter.emit(_packet())
        _key, tagged = mq.get_nowait()
        assert tagged.placement.model_index == 0

    def test_model_idx_one_tags_packet(self) -> None:
        import queue

        mq: queue.Queue = queue.Queue()
        emitter = Emitter(model_idx=1, merged_queue=mq)
        emitter.emit(_packet())
        _key, tagged = mq.get_nowait()
        assert tagged.placement.model_index == 1

    def test_model_idx_two_tags_packet(self) -> None:
        """Boundary: third model in a 3-model run."""
        import queue

        mq: queue.Queue = queue.Queue()
        emitter = Emitter(model_idx=2, merged_queue=mq)
        emitter.emit(_packet())
        _key, tagged = mq.get_nowait()
        assert tagged.placement.model_index == 2

    # --- Queue key ---

    def test_key_equals_model_idx_when_set(self) -> None:
        """Drain loop uses the key to route packets; it must match model_idx."""
        import queue

        mq: queue.Queue = queue.Queue()
        emitter = Emitter(model_idx=2, merged_queue=mq)
        emitter.emit(_packet())
        key, _ = mq.get_nowait()
        assert key == 2

    def test_key_is_zero_when_model_idx_none(self) -> None:
        """N=1: key defaults to 0 (single slot in the drain loop)."""
        import queue

        mq: queue.Queue = queue.Queue()
        emitter = Emitter(model_idx=None, merged_queue=mq)
        emitter.emit(_packet())
        key, _ = mq.get_nowait()
        assert key == 0

    # --- Placement field preservation ---

    def test_turn_index_is_preserved(self) -> None:
        import queue

        mq: queue.Queue = queue.Queue()
        emitter = Emitter(model_idx=0, merged_queue=mq)
        emitter.emit(_packet(turn_index=5))
        _, tagged = mq.get_nowait()
        assert tagged.placement.turn_index == 5

    def test_tab_index_is_preserved(self) -> None:
        import queue

        mq: queue.Queue = queue.Queue()
        emitter = Emitter(model_idx=0, merged_queue=mq)
        emitter.emit(_packet(tab_index=3))
        _, tagged = mq.get_nowait()
        assert tagged.placement.tab_index == 3

    def test_sub_turn_index_is_preserved(self) -> None:
        import queue

        mq: queue.Queue = queue.Queue()
        emitter = Emitter(model_idx=0, merged_queue=mq)
        emitter.emit(_packet(sub_turn_index=2))
        _, tagged = mq.get_nowait()
        assert tagged.placement.sub_turn_index == 2

    def test_sub_turn_index_none_is_preserved(self) -> None:
        import queue

        mq: queue.Queue = queue.Queue()
        emitter = Emitter(model_idx=0, merged_queue=mq)
        emitter.emit(_packet(sub_turn_index=None))
        _, tagged = mq.get_nowait()
        assert tagged.placement.sub_turn_index is None

    def test_packet_obj_is_not_modified(self) -> None:
        """The payload object must survive tagging untouched."""
        import queue

        mq: queue.Queue = queue.Queue()
        emitter = Emitter(model_idx=0, merged_queue=mq)
        original_obj = OverallStop(stop_reason="sentinel")
        pkt = Packet(placement=_placement(), obj=original_obj)
        emitter.emit(pkt)
        _, tagged = mq.get_nowait()
        assert tagged.obj is original_obj

    def test_different_obj_types_are_handled(self) -> None:
        """Any valid PacketObj type passes through correctly."""
        import queue

        mq: queue.Queue = queue.Queue()
        emitter = Emitter(model_idx=0, merged_queue=mq)
        pkt = Packet(placement=_placement(), obj=ReasoningStart())
        emitter.emit(pkt)
        _, tagged = mq.get_nowait()
        assert isinstance(tagged.obj, ReasoningStart)

    # --- bus is always created ---

    def test_bus_exists_in_streaming_mode(self) -> None:
        """bus must always be present for backwards-compat with existing callers."""
        import queue

        mq: queue.Queue = queue.Queue()
        emitter = Emitter(model_idx=0, merged_queue=mq)
        assert hasattr(emitter, "bus")
        assert isinstance(emitter.bus, queue.Queue)

    def test_bus_stays_empty_in_streaming_mode(self) -> None:
        import queue

        mq: queue.Queue = queue.Queue()
        emitter = Emitter(model_idx=0, merged_queue=mq)
        emitter.emit(_packet())
        assert emitter.bus.empty()

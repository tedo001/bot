import math

import numpy as np
import pytest
from pydantic import ValidationError

from vla_dashboard.schemas import MAX_TRANSLATION, ActionCommand, BBox, InstructionPayload


def test_instruction_normalises_whitespace():
    p = InstructionPayload(text="  pick   up\nthe cube ")
    assert p.text == "pick up the cube"
    assert len(p.request_id) == 12


@pytest.mark.parametrize("bad", ["", "  ", "12345", "a\x00bcd", "x" * 600])
def test_instruction_rejects_bad_text(bad):
    with pytest.raises(ValidationError):
        InstructionPayload(text=bad)


def test_instruction_is_frozen():
    p = InstructionPayload(text="pick up the cube")
    with pytest.raises(ValidationError):
        p.text = "other"


def test_action_bounds_enforced():
    with pytest.raises(ValidationError):
        ActionCommand(dx=1.0)
    with pytest.raises(ValidationError):
        ActionCommand(dx=math.nan)
    with pytest.raises(ValidationError):
        ActionCommand(gripper=2.0)


def test_action_from_array_clips_and_roundtrips():
    a = ActionCommand.from_array(np.array([1.0, -1.0, 0.01, 0, 0, 3.0, 5.0]), source="openvla", inference_ms=12)
    assert a.dx == MAX_TRANSLATION and a.dy == -MAX_TRANSLATION and a.gripper == 1.0
    assert np.allclose(a.to_array()[:3], [MAX_TRANSLATION, -MAX_TRANSLATION, 0.01])
    with pytest.raises(ValueError):
        ActionCommand.from_array(np.array([np.inf] * 7))


def test_hold_is_zero():
    assert ActionCommand.hold().is_hold


def test_bbox_validation():
    with pytest.raises(ValidationError):
        BBox(x1=10, y1=0, x2=5, y2=5)
    assert BBox(x1=0, y1=0, x2=4, y2=2).center == (2.0, 1.0)

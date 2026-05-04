"""Creator tests - covers error paths and visualizer integration."""

from __future__ import annotations
import json
import pytest

from hermes_studio.archetypes.balancer import Balancer
from hermes_studio.archetypes.creator import Creator
from hermes_studio.archetypes.guardian import Guardian
from hermes_studio.archetypes.visualizer import Visualizer


@pytest.fixture
def creator():
    return Creator(
        guardian=Guardian(),
        visualizer=Visualizer(),
        balancer=Balancer(),
    )


def test_render_image_missing_fal_key_returns_actionable_error(creator, monkeypatch):
    monkeypatch.delenv("FAL_KEY", raising=False)
    out = json.loads(creator.render_image(args={"prompt": "x"}))
    assert out["ok"] is False
    assert out["error"] == "backend_not_configured"
    assert out["missing_env"] == "FAL_KEY"
    assert "fal.ai" in out["how_to_fix"]


def test_render_3d_missing_tripo3d_key_returns_actionable_error(creator, monkeypatch):
    monkeypatch.delenv("TRIPO3D_API_KEY", raising=False)
    out = json.loads(creator.render_3d(args={"prompt": "x"}))
    assert out["ok"] is False
    assert out["error"] == "backend_not_configured"
    assert out["missing_env"] == "TRIPO3D_API_KEY"
    assert "tripo3d" in out["how_to_fix"].lower()


def test_render_video_returns_not_yet_implemented(creator):
    out = json.loads(creator.render_video(args={"shots": []}))
    assert out["ok"] is False
    assert out["error"] == "not_yet_implemented"
    assert "shipping_in" in out


def test_render_audio_only_narration_implemented(creator):
    out = json.loads(creator.render_audio(args={"kind": "music"}))
    assert out["ok"] is False
    assert "only narration" in out["error"]


def test_render_audio_narration_requires_text(creator):
    out = json.loads(creator.render_audio(args={"kind": "narration"}))
    assert out["ok"] is False
    assert "text required" in out["error"]


def test_render_audio_narration_emits_canvas_event(creator):
    out = json.loads(creator.render_audio(
        args={"kind": "narration", "text": "Hello world"},
        session_id="s1",
        profile_id="alice",
    ))
    assert out["ok"] is True
    assert len(creator.visualizer._replay) == 1
    evt = creator.visualizer._replay[0]
    assert evt.kind == "audio"
    assert evt.payload["text"] == "Hello world"


def test_fal_size_mapping(creator):
    assert creator._fal_size("1:1") == "square_hd"
    assert creator._fal_size("16:9") == "landscape_16_9"
    assert creator._fal_size("9:16") == "portrait_9_16"
    assert creator._fal_size("4:3") == "landscape_4_3"
    assert creator._fal_size("3:4") == "portrait_4_3"
    assert creator._fal_size("21:9") == "square_hd"


def test_creator_holds_archetype_references(creator):
    assert isinstance(creator.guardian, Guardian)
    assert isinstance(creator.visualizer, Visualizer)
    assert isinstance(creator.balancer, Balancer)

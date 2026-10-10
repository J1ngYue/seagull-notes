"""Verify figure data, iteration directions, and usable exports."""

import importlib.util
import json
import math
import sys
from pathlib import Path

import pytest

pytest.importorskip("matplotlib")
from matplotlib import pyplot as plt


def plot_module():
    path = Path(__file__).resolve().parents[1] / "skill" / "scripts" / "plot.py"
    spec = importlib.util.spec_from_file_location("note_plot", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def example():
    path = Path(__file__).resolve().parents[1] / "examples" / "gradient-plot.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_curve_and_update_points_match_the_declared_function():
    data = example()
    fig = plot_module().make_figure(data)
    try:
        curve = fig.axes[1].lines[0]
        assert list(curve.get_xdata()) == data["x"]
        assert list(curve.get_ydata()) == pytest.approx([x*x/2 for x in data["x"]])
        points = [tuple(collection.get_offsets()[0]) for collection in fig.axes[1].collections]
        expected = []
        theta = 4
        for _ in range(4):
            expected.append((theta, theta*theta/2))
            theta -= .5*theta
        assert points == expected
        arrows = [text for text in fig.axes[1].texts if not text.get_text()]
        assert [tuple(arrow.xy) for arrow in arrows] == expected[1:]
    finally:
        plt.close(fig)


@pytest.mark.parametrize("change", [
    {"x": [0]}, {"y": [0]}, {"x": [0, math.nan]}, {"y": [0, math.inf]},
])
def test_bad_coordinates_are_rejected(change):
    data = {"x": [0, 1], "y": [0, 1], **change}
    with pytest.raises(ValueError):
        plot_module().validate(data)


def test_too_close_step_labels_are_reported():
    data = example()
    data["steps"] = [{"x": 1, "y": .5}, {"x": 1.001, "y": .5001}]
    with pytest.raises(ValueError, match="overlap"):
        plot_module().make_figure(data)


def test_export_produces_vector_and_raster_files(tmp_path, monkeypatch, capsys):
    module = plot_module()
    data_path = tmp_path / "plot.json"
    data_path.write_text(json.dumps(example()), encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["plot.py", str(data_path), "--out", str(tmp_path / "plot")])
    assert module.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert Path(result["svg"]).read_text(encoding="utf-8").find("<svg") >= 0
    from PIL import Image
    with Image.open(result["png"]) as raster:
        assert raster.size == (1500, 1080)
        assert raster.format == "PNG"

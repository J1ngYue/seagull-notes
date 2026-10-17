"""Dense bilingual mind maps keep every label and avoid overlapping cards."""
import xml.etree.ElementTree as ET

from seagull_notes import export, obsidian_export


def dense_tree():
    return [{"title": f"主题 {index}：完整中文与 English 标签", "children": [
        {"title": "工作区、暂存区与历史：这是完整的长标题，不应该被截断 " + str(child)}
        for child in range(count)]} for index, count in enumerate([4, 7, 2, 5, 3])]


def overlaps(a, b):
    return (max(a["x"], b["x"]) < min(a["x"] + a["w"], b["x"] + b["w"])
            and max(a["y"], b["y"]) < min(a["y"] + a["h"], b["y"] + b["h"]))


def test_dense_layout_keeps_all_labels_inside_canvas_without_overlap():
    tree = dense_tree()
    placed, width, bottom = export._layout(tree, "完整课程")
    assert len(placed) == 1 + sum(1 + len(root["children"]) for root in tree)
    assert {node["side"] for node in placed[1:]} == {-1, 1}
    for index, node in enumerate(placed):
        assert 0 <= node["x"] <= width - node["w"] + .001
        assert 0 <= node["y"] <= bottom + export.NODE_H - node["h"] + .001
        assert ''.join(node["lines"]).replace(' ', '') == node["title"].replace(' ', '')
        assert all(not overlaps(node, other) for other in placed[index + 1:])
    ET.fromstring(export.render_svg(tree, "完整课程"))


def test_deep_branches_and_repeated_titles_keep_distinct_relationships():
    tree = [{"title": "根", "children": [{"title": "相同标题", "children": [
        {"title": "相同标题", "children": [{"title": "末端"}]}]}, {"title": "相同标题"}]}]
    placed, _, _ = export._layout(tree)
    assert [node["parent"] for node in placed] == [None, 0, 1, 2, 0]
    assert all(not overlaps(node, other) for index, node in enumerate(placed) for other in placed[index + 1:])


def test_wrapping_keeps_short_command_names_whole():
    lines = export._wrap_label("作者配置 · status · diff · log", 28)
    assert any("log" in line for line in lines)
    assert any("status" in line for line in lines)


def test_editable_canvas_uses_same_balanced_tree_without_overlap():
    canvas = obsidian_export.canvas_tree(dense_tree(), "完整课程")
    assert len(canvas["edges"]) == len(canvas["nodes"]) - 1
    cards = [dict(node, w=node["width"], h=node["height"]) for node in canvas["nodes"]]
    assert all(not overlaps(node, other) for index, node in enumerate(cards) for other in cards[index + 1:])
    assert {edge["fromSide"] for edge in canvas["edges"]} == {"left", "right"}


def test_topic_focus_bounds_include_each_complete_branch():
    from lxml import html

    tree = dense_tree()
    placed, _, _ = export._layout(tree, "完整课程")
    page = html.fromstring(export.render_mindmap(tree, "完整课程"))
    buttons = page.cssselect('.map-topics button[data-map-focus]')[1:]
    assert len(buttons) == len(tree)
    for button, branch in zip(buttons, [node for node in placed if node["depth"] == 1]):
        x, y, width, height = map(float, button.get('data-map-focus').split(','))
        members = [node for node in placed if node["depth"] and node["branch"] == branch["branch"]]
        assert branch["title"] in button.text_content()
        for node in members:
            assert x <= node["x"] + export.PADDING + .1
            assert y <= node["y"] + export.PADDING + .1
            assert x + width + .1 >= node["x"] + node["w"] + export.PADDING
            assert y + height + .1 >= node["y"] + node["h"] + export.PADDING


def test_rich_example_preserves_all_nodes_in_svg_and_editable_canvas():
    import json
    from pathlib import Path

    tree = json.loads((Path(__file__).parents[1] / 'examples/knowledge.json').read_text(encoding='utf-8'))['mind_map']
    placed, _, _ = export._layout(tree)
    assert max(node['depth'] for node in placed) >= 3
    svg = ET.fromstring(export.render_svg(tree))
    assert len(svg.findall('.//{http://www.w3.org/2000/svg}g[@class="map-node"]')) == len(placed)
    assert len(obsidian_export.canvas_tree(tree, 'Git 与 GitHub')['nodes']) == len(placed)
    assert all(not overlaps(node, other) for index, node in enumerate(placed) for other in placed[index + 1:])

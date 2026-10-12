"""LaTeX survives Markdown and exports with local fonts and copy support."""

import importlib.util
import re
from pathlib import Path

from lxml import html


def notebook():
    path = Path(__file__).resolve().parents[1] / "skill" / "scripts" / "notebook.py"
    spec = importlib.util.spec_from_file_location("math_notebook", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_inline_and_display_formulas_preserve_tex():
    text = r"Inline $L(\theta)=\frac{\theta^2}{2}$ and a block:" + "\n\n" + r"$$\theta_{t+1}=\theta_t-\eta\nabla L(\theta_t)$$"
    doc = html.fromstring(notebook().rich_text(text))
    math = doc.xpath('//*[contains(@class,"arithmatex")]')
    assert len(math) == 2
    assert r"\frac{\theta^2}{2}" in math[0].text_content()
    assert r"\theta_{t+1}" in math[1].text_content()
    assert not math[1].xpath('.//em')


def test_code_and_currency_are_not_treated_as_formulas():
    doc = html.fromstring(notebook().rich_text('`$x_1$`\n\n```text\n$x_2$\n```\n\nCost: $20 and $30.'))
    assert not doc.xpath('//*[contains(@class,"arithmatex")]')
    assert '$x_1$' in doc.text_content()


def test_aligned_formula_keeps_ampersands_and_linebreaks():
    tex = r"\begin{aligned}a&=b\\c&=d\end{aligned}"
    doc = html.fromstring(notebook().rich_text(f"$$\n{tex}\n$$"))
    assert tex in doc.xpath('//*[contains(@class,"arithmatex")]')[0].text_content()


def test_math_html_contains_embedded_katex_and_fonts(tmp_path):
    page, markdown = notebook().render_note({
        "title": "数学笔记", "source_url": "https://youtu.be/test",
        "sections": [{"title": "公式", "markdown": r"$$\frac{a}{b}$$"}],
    }, tmp_path)
    doc = html.fromstring(page)
    assert not doc.xpath('//script[@src]')
    assert not doc.xpath('//link[@rel="stylesheet"]')
    css = "\n".join(doc.xpath('//style/text()'))
    fonts = re.findall(r'@font-face\{[^}]+\}', css)
    assert fonts and all('data:font/woff2;base64,' in font for font in fonts)
    assert 'katex.render' in page
    assert 'navigator.clipboard.writeText(text)' in page
    assert 'element.dataset.latex=latex' in page
    assert r'$$\frac{a}{b}$$' in markdown


def test_plain_notes_do_not_embed_math_assets(tmp_path):
    page, _ = notebook().render_note({
        "title": "普通笔记", "source_url": "https://youtu.be/test",
        "sections": [{"title": "正文", "markdown": "没有公式。"}],
    }, tmp_path)
    assert 'font-family:KaTeX' not in page
    assert 'font-family:SeagullHand' in page
    assert len(html.fromstring(page).xpath('//script')) == 1

"""Regression tests for HTMLParser._html_to_markdown after switching to trafilatura.

Focus: verify that the WeChat-public-account preprocessing path still produces
non-empty Markdown after the underlying extractor changed from
readabilipy + markdownify to trafilatura.
"""

from openviking.parse.parsers.html import HTMLParser


WECHAT_HTML = """
<!doctype html>
<html>
<head><title>WeChat Article</title></head>
<body>
  <div id="page-content">
    <div id="js_content" style="visibility: hidden; opacity: 0;">
      <h1>Business Data Platform 週報</h1>
      <p>這是一篇微信公眾號文章的正文段落，至少包含兩百字以上的有效內容，
      用於讓基於文本密度的抽取器能夠穩定識別出主體區域。</p>
      <p>第二段同樣是足夠長的正文，避免被啟發式規則誤判為噪聲。我們再加一些
      內容以保證抽取器有充分的密度訊號去命中這塊隱藏 div 區域。</p>
      <p>第三段是為了進一步增加正文密度。Business Data Platform 的 HTMLParser 在切換
      抽取器後仍然需要正確地從 #js_content 這個被 CSS 隱藏的容器裡取出文本。</p>
      <img src="" data-src="https://example.com/cover.jpg" alt="cover" />
    </div>
  </div>
</body>
</html>
"""


def test_preprocess_strips_hidden_style_and_keeps_content():
    parser = HTMLParser()
    cleaned = parser._preprocess_html(WECHAT_HTML)
    assert "visibility: hidden" not in cleaned
    assert "Business Data Platform 週報" in cleaned
    assert 'src="https://example.com/cover.jpg"' in cleaned


def test_html_to_markdown_extracts_wechat_body():
    parser = HTMLParser()
    md = parser._html_to_markdown(WECHAT_HTML)
    assert md, "trafilatura should extract non-empty markdown from a WeChat-style article"
    assert "Business Data Platform 週報" in md
    assert "微信公眾號" in md


def test_html_to_markdown_returns_empty_string_on_garbage_input():
    parser = HTMLParser()
    md = parser._html_to_markdown("<html><body></body></html>")
    assert md == ""

"use strict";

// Model text never becomes HTML. Only these explicitly created elements render.
window.SurveyorAIText = (() => {
  function inline(parent, source, formatted) {
    const pattern =
      /\*\*([^*\n]+)\*\*|__([^_\n]+)__|`([^`\n]+)`|\*([^*\n]+)\*|\[([^\]\n]+)\]\([^\s)]*\)/g;
    let offset = 0;
    for (const match of source.matchAll(pattern)) {
      parent.append(document.createTextNode(source.slice(offset, match.index)));
      const value = match[1] ?? match[2] ?? match[3] ?? match[4] ?? match[5];
      if (formatted && !match[5]) {
        const node = document.createElement(
          match[3] ? "code" : match[4] ? "em" : "strong",
        );
        node.textContent = value;
        parent.append(node);
      } else parent.append(document.createTextNode(value));
      offset = match.index + match[0].length;
    }
    parent.append(document.createTextNode(source.slice(offset)));
  }
  function render(target, text, mode = "formatted") {
    target.replaceChildren();
    target.classList.add("ai-answer");
    target.dataset.noTranslate = "";
    const formatted = mode === "formatted";
    let list = null;
    for (const line of String(text ?? "")
      .slice(0, 50000)
      .split(/\r?\n/)) {
      if (!line.trim() || /^\s*```/.test(line)) {
        list = null;
        continue;
      }
      const bullet = line.match(/^\s*(?:[-*•]|\d+[.)])\s+(.+)$/);
      const heading = line.match(/^#{1,6}\s+(.+)$/);
      if (bullet && formatted) {
        const tag = /^\s*\d/.test(line) ? "ol" : "ul";
        if (!list || list.tagName.toLowerCase() !== tag) {
          list = document.createElement(tag);
          target.append(list);
        }
        const item = document.createElement("li");
        inline(item, bullet[1], true);
        list.append(item);
      } else {
        list = null;
        const node = document.createElement(heading && formatted ? "h4" : "p");
        inline(node, heading?.[1] ?? bullet?.[1] ?? line, formatted);
        target.append(node);
      }
    }
  }
  return { render };
})();

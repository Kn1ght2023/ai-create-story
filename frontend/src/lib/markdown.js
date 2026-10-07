import { marked } from 'marked';
import DOMPurify from 'dompurify';

marked.setOptions({
  gfm: true,
  breaks: true,
});

// 渲染 markdown 为安全的 HTML（DOMPurify 清洗，防止 AI 输出中夹带脚本）
export function renderMarkdown(text) {
  if (!text) return '';
  try {
    return DOMPurify.sanitize(marked.parse(text));
  } catch {
    return text;
  }
}

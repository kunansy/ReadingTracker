import { marked } from "marked";

export const parseMarkdown = (src: string): string => {
  const preprocessed = src.replace(/<br\s*\/?>/gi, "\n");
  return marked.parse(preprocessed);
};

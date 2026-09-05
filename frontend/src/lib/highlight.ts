/** A small syntax highlighter, with no dependency.
 *
 * The old editor was a bare `<textarea>`: no line numbers, no colour, and no
 * way to tell a comment from a string. A highlighting library would fix that
 * and add a few hundred kilobytes plus a build-time dependency to a repository
 * that ships as a replication package for a paper, so this does the small part
 * that is actually needed.
 *
 * It is a lexer, not a parser: it will not resolve types or scopes, and it does
 * not try to. It gets comments, strings, keywords, numbers, annotations and
 * declaration names right, which is all that is needed to read a class.
 */

export type TokenKind =
  | 'comment'
  | 'string'
  | 'keyword'
  | 'type'
  | 'number'
  | 'annotation'
  | 'function'
  | 'punctuation'
  | 'plain'

export interface Token {
  text: string
  kind: TokenKind
}

const KEYWORDS: Record<string, string[]> = {
  java: [
    'abstract', 'assert', 'break', 'case', 'catch', 'class', 'const', 'continue', 'default',
    'do', 'else', 'enum', 'extends', 'final', 'finally', 'for', 'goto', 'if', 'implements',
    'import', 'instanceof', 'interface', 'native', 'new', 'package', 'private', 'protected',
    'public', 'record', 'return', 'static', 'strictfp', 'super', 'switch', 'synchronized',
    'this', 'throw', 'throws', 'transient', 'try', 'var', 'volatile', 'while', 'yield',
    'true', 'false', 'null',
  ],
  python: [
    'and', 'as', 'assert', 'async', 'await', 'break', 'class', 'continue', 'def', 'del',
    'elif', 'else', 'except', 'finally', 'for', 'from', 'global', 'if', 'import', 'in', 'is',
    'lambda', 'match', 'nonlocal', 'not', 'or', 'pass', 'raise', 'return', 'try', 'while',
    'with', 'yield', 'True', 'False', 'None', 'self', 'cls',
  ],
  typescript: [
    'abstract', 'any', 'as', 'async', 'await', 'break', 'case', 'catch', 'class', 'const',
    'continue', 'declare', 'default', 'delete', 'do', 'else', 'enum', 'export', 'extends',
    'finally', 'for', 'from', 'function', 'get', 'if', 'implements', 'import', 'in',
    'instanceof', 'interface', 'is', 'keyof', 'let', 'new', 'of', 'private', 'protected',
    'public', 'readonly', 'return', 'satisfies', 'set', 'static', 'super', 'switch', 'this',
    'throw', 'try', 'type', 'typeof', 'var', 'void', 'while', 'yield',
    'true', 'false', 'null', 'undefined',
  ],
  csharp: [
    'abstract', 'as', 'base', 'bool', 'break', 'case', 'catch', 'class', 'const', 'continue',
    'default', 'delegate', 'do', 'else', 'enum', 'event', 'explicit', 'extern', 'finally',
    'fixed', 'for', 'foreach', 'get', 'if', 'implicit', 'in', 'interface', 'internal', 'is',
    'lock', 'namespace', 'new', 'null', 'object', 'operator', 'out', 'override', 'params',
    'private', 'protected', 'public', 'readonly', 'ref', 'return', 'sealed', 'set', 'static',
    'string', 'struct', 'switch', 'this', 'throw', 'try', 'typeof', 'using', 'var', 'virtual',
    'void', 'while', 'true', 'false',
  ],
  go: [
    'break', 'case', 'chan', 'const', 'continue', 'default', 'defer', 'else', 'fallthrough',
    'for', 'func', 'go', 'goto', 'if', 'import', 'interface', 'map', 'package', 'range',
    'return', 'select', 'struct', 'switch', 'type', 'var', 'nil', 'true', 'false',
  ],
}

KEYWORDS.javascript = KEYWORDS.typescript
KEYWORDS.kotlin = KEYWORDS.java
KEYWORDS.ruby = KEYWORDS.python
KEYWORDS.php = KEYWORDS.typescript

/** Line-comment marker, and whether the language has C-style block comments. */
function commentSyntax(language: string): { line: string; block: boolean; hash: boolean } {
  if (language === 'python' || language === 'ruby' || language === 'yaml') {
    return { line: '#', block: false, hash: true }
  }
  return { line: '//', block: true, hash: false }
}

/**
 * One pass, longest-match-first. Order matters: comments and strings are
 * consumed before anything inside them can be mistaken for a keyword.
 */
export function tokenize(source: string, language: string): Token[] {
  const keywords = new Set(KEYWORDS[language] ?? KEYWORDS.typescript)
  const syntax = commentSyntax(language)
  const tokens: Token[] = []
  let index = 0

  const push = (text: string, kind: TokenKind) => {
    if (!text) return
    const previous = tokens[tokens.length - 1]
    if (previous && previous.kind === kind) previous.text += text
    else tokens.push({ text, kind })
  }

  while (index < source.length) {
    const rest = source.slice(index)

    // Block comment, including a docstring-style /** */.
    if (syntax.block && rest.startsWith('/*')) {
      const end = source.indexOf('*/', index + 2)
      const stop = end === -1 ? source.length : end + 2
      push(source.slice(index, stop), 'comment')
      index = stop
      continue
    }

    // Line comment.
    if (rest.startsWith(syntax.line) || (syntax.hash && rest.startsWith('#'))) {
      const end = source.indexOf('\n', index)
      const stop = end === -1 ? source.length : end
      push(source.slice(index, stop), 'comment')
      index = stop
      continue
    }

    // Python triple-quoted string, which must be tried before a single quote.
    if (language === 'python' && (rest.startsWith('"""') || rest.startsWith("'''"))) {
      const fence = rest.slice(0, 3)
      const end = source.indexOf(fence, index + 3)
      const stop = end === -1 ? source.length : end + 3
      push(source.slice(index, stop), 'string')
      index = stop
      continue
    }

    // String, honouring backslash escapes so "\"" does not end it early.
    const quote = rest[0]
    if (quote === '"' || quote === "'" || quote === '`') {
      let cursor = index + 1
      while (cursor < source.length) {
        if (source[cursor] === '\\') {
          cursor += 2
          continue
        }
        if (source[cursor] === quote) {
          cursor += 1
          break
        }
        // An unterminated single-quoted string should not swallow the file.
        if (source[cursor] === '\n' && quote !== '`') break
        cursor += 1
      }
      push(source.slice(index, cursor), 'string')
      index = cursor
      continue
    }

    // Java/C# annotation or Python decorator.
    const annotation = /^@[A-Za-z_][\w.]*/.exec(rest)
    if (annotation) {
      push(annotation[0], 'annotation')
      index += annotation[0].length
      continue
    }

    // Number, including hex and floats with suffixes.
    const number = /^(?:0[xX][0-9a-fA-F_]+|\d[\d_]*(?:\.\d[\d_]*)?(?:[eE][+-]?\d+)?)[fFdDlLuU]?/.exec(rest)
    if (number) {
      push(number[0], 'number')
      index += number[0].length
      continue
    }

    // Identifier: a keyword, a type (capitalised), a call, or plain text.
    const word = /^[A-Za-z_$][\w$]*/.exec(rest)
    if (word) {
      const text = word[0]
      const after = rest.slice(text.length)
      if (keywords.has(text)) push(text, 'keyword')
      else if (/^\s*\(/.test(after)) push(text, 'function')
      else if (/^[A-Z]/.test(text)) push(text, 'type')
      else push(text, 'plain')
      index += text.length
      continue
    }

    const punctuation = /^[{}()[\];,.<>+\-*/%=!&|^~?:]+/.exec(rest)
    if (punctuation) {
      push(punctuation[0], 'punctuation')
      index += punctuation[0].length
      continue
    }

    push(source[index], 'plain')
    index += 1
  }

  return tokens
}

/** Token colours, as theme variables so they follow the light/dark toggle. */
export const TOKEN_COLORS: Record<TokenKind, string> = {
  comment: 'var(--muted)',
  string: 'var(--series-3)',
  keyword: 'var(--series-4)',
  type: 'var(--series-1)',
  number: 'var(--series-2)',
  annotation: 'var(--warning)',
  function: 'var(--ink)',
  punctuation: 'var(--ink-3)',
  plain: 'var(--ink-2)',
}

/** Split tokens into lines, so each line can be rendered as its own row
 *  alongside a line number and a gutter marker. */
export function tokenizeLines(source: string, language: string): Token[][] {
  const lines: Token[][] = [[]]
  for (const token of tokenize(source, language)) {
    const parts = token.text.split('\n')
    parts.forEach((part, index) => {
      if (index > 0) lines.push([])
      if (part) lines[lines.length - 1].push({ text: part, kind: token.kind })
    })
  }
  return lines
}

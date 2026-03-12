"""Text Utils: word_count.

Counts lines, words, and characters in a piece of text.
Uses only the Python standard library — compatible with Pyodide (sandboxed) execution.
"""

import argparse


def word_count(text: str) -> str:
    """Return a formatted summary of line, word, and character counts.

    Args:
        text: The text to analyse.

    Returns:
        A formatted string with the counts.
    """
    lines = text.splitlines()
    words = text.split()
    return f'Lines   : {len(lines)}\nWords   : {len(words)}\nChars   : {len(text)}'


def main() -> None:
    parser = argparse.ArgumentParser(description='Count lines, words, and characters in text')
    parser.add_argument('--text', type=str, required=True, help='Text to analyse')
    args = parser.parse_args()
    print(word_count(args.text))


if __name__ == '__main__':
    main()

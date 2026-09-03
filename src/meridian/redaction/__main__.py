from __future__ import annotations

import argparse

from meridian.redaction.analyzer import build_analyzer_engine
from meridian.redaction.tokenize import tokenize_for_external_call, untokenize


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Demo the redaction tokenize/untokenize round trip on a piece of text. "
        "There's no live call site yet (phases 8/10 aren't built) - this is for manual verification."
    )
    parser.add_argument("text", help="text to tokenize (wrap in quotes)")
    args = parser.parse_args()

    analyzer = build_analyzer_engine()
    result = tokenize_for_external_call(args.text, analyzer=analyzer)

    print(f"Original:   {args.text}")
    print(f"Tokenized:  {result.tokenized_text}")
    print(f"Entities:   {result.entity_counts}")

    restored = untokenize(result.tokenized_text, result.mapping)
    print(f"Restored:   {restored}")
    print(f"Round trip matches original: {restored == args.text}")


if __name__ == "__main__":
    main()

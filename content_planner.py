"""
content_planner.py  --  Content Strategist for Stickman Studio
==============================================================
Uses Gemini to generate 10 viral video ideas for a given category.
Output is saved to daily_plan.json by default.

Usage:
    python content_planner.py "Physics"
    python content_planner.py "Psychology" --count 5
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from typing import Optional

from stickman_studio.config import settings, init_vertex
from stickman_studio.retry import with_retry

log = logging.getLogger("stickman_studio.content_planner")

_RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "category": {"type": "string"},
        "ideas": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "hook": {"type": "string"},
                    "category": {"type": "string"},
                    "video_mode": {
                        "type": "string",
                        "enum": ["animation", "slideshow"],
                    },
                    "complexity_score": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": 5,
                    },
                },
                "required": ["title", "hook", "category", "video_mode", "complexity_score"],
            },
        },
    },
    "required": ["category", "ideas"],
}

_SYSTEM_INSTRUCTION = """
You are the Lead Content Strategist for 'Stickman Studio'. Your mission is to
generate viral, high-retention video concepts that dominate YouTube Shorts.

For every video idea, you must adhere to these 'Viral Engineering' rules:

1. TITLES: Use the 'Gap of Curiosity' technique. Combine a strong emotion
   (Shock, Fear, Wonder) with a specific scientific premise.
   - Good: "What if you stopped sleeping?"
   - Great: "The 3-Day Experiment: What Happens to Your Brain When You Stop Sleeping?"

2. HOOKS: Start the narration with a 'Negative Hook' or a 'Contradiction'.
   - Example: "Stop believing everything your brain tells you."
   - Example: "You have been breathing wrong your entire life."

3. CATEGORY BALANCE:
   - Animation Mode: Choose topics that benefit from complex visualisation
     (e.g., Space, Physics, Microscopic world).
   - Slideshow Mode: Choose topics that rely on facts, lists, or fast-paced
     trivia (e.g., Human Body, Psychology, History).

4. OUTPUT FORMAT: Return only a clean JSON array of 10 objects.
   Fields: title, hook, category, video_mode, complexity_score (1-5).

5. TONE: Punchy, authoritative, and extremely fast-paced. No filler words.
   No boring intros.
"""


def _build_prompt(category: str, count: int) -> str:
    return f"""CATEGORY: "{category}"

Generate exactly {count} viral video ideas for Stickman Studio.

Every title must use the 'Gap of Curiosity' technique:
combine an emotion (Shock, Fear, Wonder) with a specific premise.

Every hook must be a Negative Hook or Contradiction —
NEVER "Today we talk about...", "Have you ever wondered...", or
"In this video...". Start bold, not boring."""


@with_retry
def _generate(model, prompt: str):
    from vertexai.generative_models import GenerationConfig

    return model.generate_content(
        prompt,
        generation_config=GenerationConfig(
            temperature=0.8,
            max_output_tokens=4096,
            response_mime_type="application/json",
            response_schema=_RESPONSE_SCHEMA,
        ),
    )


def plan_content(
    category: str,
    count: int = 10,
    output: Path | None = None,
) -> dict:
    """Generate viral video ideas for a given category.

    Args:
        category: Broad topic area (e.g. "Physics", "Psychology").
        count: Number of ideas to generate (default 10).
        output: Optional path to write the JSON result.

    Returns:
        Dict with ``category`` and ``ideas`` list.
    """
    init_vertex()
    from vertexai.generative_models import GenerativeModel

    log.info("Planning %d viral ideas for '%s'", count, category)

    model = GenerativeModel(
        settings.gemini_model,
        system_instruction=_SYSTEM_INSTRUCTION,
    )
    response = _generate(model, _build_prompt(category, count))

    raw = response.text
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        log.error("Gemini returned non-JSON output.")
        raise RuntimeError(f"Failed to parse Gemini JSON: {e}\n--- raw ---\n{raw[:2000]}")

    data["ideas"] = data["ideas"][:count]

    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            json.dumps(data, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        log.info("Saved %d ideas to %s", len(data["ideas"]), output)

    log.info("Done: %d ideas generated for '%s'", len(data["ideas"]), category)
    return data


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-7s | %(message)s",
        datefmt="%H:%M:%S",
        stream=sys.stdout,
    )


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Content Strategist for Stickman Studio — "
                    "generate viral video ideas using Gemini."
    )
    parser.add_argument("category", help="Broad topic (e.g. Physics, Psychology)")
    parser.add_argument("--output", "-o", default=None,
                        help="Output JSON file path (default: daily_plan.json)")
    parser.add_argument("--count", "-n", type=int, default=10,
                        help="Number of ideas (default: 10)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable DEBUG logging")
    args = parser.parse_args()

    _setup_logging(args.verbose)

    try:
        out_path = Path(args.output) if args.output else Path("daily_plan.json")
        result = plan_content(
            category=args.category,
            count=args.count,
            output=out_path,
        )
        print(f"Saved {len(result['ideas'])} ideas to {out_path}")
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as exc:
        log.exception("Content planning failed: %s", exc)
        sys.exit(1)


if __name__ == "__main__":
    main()

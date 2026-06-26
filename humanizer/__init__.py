"""
StealthHumanizer Python Port — Deterministic Layer for RankBuilder
Ported from TypeScript (MIT License) → Python

Exposes:
- humanize(text, level='medium', style='professional') → str
- detect_ai(text) → DetectionResult dict
- humanize_with_score(text, level='medium', style='professional') → (str, DetectionResult)
"""

from .detector import detect_ai, DetectionResult
from .postprocess import postprocess

__all__ = ['humanize', 'detect_ai', 'humanize_with_score', 'DetectionResult']


def humanize(text: str, level: str = 'medium', style: str = 'professional') -> str:
    """
    Apply deterministic humanization (post-processing only — no LLM).
    
    Args:
        text: The text to humanize.
        level: 'light', 'medium', 'aggressive', or 'ninja' (default: medium).
        style: 'academic', 'casual', 'professional', 'creative', 'technical' (default: professional).
    
    Returns:
        Humanized text string.
    """
    light = level == 'light'
    aggressive = level in ('aggressive', 'ninja')
    return postprocess(text, light=light, style=style, aggressive=aggressive)


def humanize_with_score(text: str, level: str = 'medium', style: str = 'professional') -> tuple[str, dict]:
    """
    Humanize text and return the detection score for both original and humanized.
    
    Returns:
        (humanized_text, detection_result_dict)
    """
    humanized = humanize(text, level=level, style=style)
    result = detect_ai(humanized)
    return humanized, result
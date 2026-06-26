"""
StealthHumanizer — Type Definitions
Ported from TypeScript lib/types.ts → Python

Data classes and type aliases for the humanizer pipeline.
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum


class RewriteLevel(str, Enum):
    LIGHT = 'light'
    MEDIUM = 'medium'
    AGGRESSIVE = 'aggressive'
    NINJA = 'ninja'


class WritingStyle(str, Enum):
    ACADEMIC = 'academic'
    CASUAL = 'casual'
    PROFESSIONAL = 'professional'
    CREATIVE = 'creative'
    TECHNICAL = 'technical'


class Tone(str, Enum):
    FORMAL = 'formal'
    NEUTRAL = 'neutral'
    CONVERSATIONAL = 'conversational'


class Provider(str, Enum):
    OPENAI = 'openai'
    ANTHROPIC = 'anthropic'
    GOOGLE = 'google'
    GROQ = 'groq'
    OLLAMA = 'ollama'
    CUSTOM = 'custom'


@dataclass
class DetectionMetrics:
    perplexity: float = 0.0
    burstiness: float = 0.0
    vocabulary_diversity: float = 0.0
    sentence_length_variation: float = 0.0
    transition_frequency: float = 0.0
    passive_voice_ratio: float = 0.0
    ai_phrase_density: float = 0.0
    sentence_start_diversity: float = 0.0
    pronoun_usage: float = 0.0
    hedging_frequency: float = 0.0
    quantifier_overuse: float = 0.0


@dataclass
class SentenceDetection:
    text: str
    score: float
    classification: str  # 'human', 'maybe', 'ai'
    issues: list[str] = field(default_factory=list)


@dataclass
class DetectionResult:
    score: float
    confidence_interval: dict  # {lower, upper}
    sentences: list[SentenceDetection]
    overall_verdict: str  # 'human', 'mixed', 'ai'
    analysis: DetectionMetrics


@dataclass
class ReadabilityScores:
    flesch_reading_ease: float
    flesch_kincaid_grade: float
    coleman_liau_index: float
    avg_words_per_sentence: float
    avg_syllables_per_word: float
    reading_time_minutes: float
    total_sentences: int
    total_words: int
    total_syllables: int


@dataclass
class HumanizerConfig:
    level: RewriteLevel = RewriteLevel.MEDIUM
    style: WritingStyle = WritingStyle.PROFESSIONAL
    tone: Tone = Tone.NEUTRAL
    provider: Optional[Provider] = None
    skip_readability_guard: bool = False


def verdict_emoji(verdict: str) -> str:
    """Return an emoji for the detection verdict."""
    return {
        'human': '✅',
        'mixed': '⚠️',
        'ai': '🤖',
    }.get(verdict, '❓')


def verdict_label(verdict: str) -> str:
    """Return a human-readable label for the detection verdict."""
    return {
        'human': 'Likely Human',
        'mixed': 'Mixed (Partially AI)',
        'ai': 'Likely AI-Generated',
    }.get(verdict, 'Unknown')


def score_bar(score: float, width: int = 20) -> str:
    """Return a visual bar for the score."""
    filled = int(score / 100 * width)
    empty = width - filled
    return '█' * filled + '░' * empty
"""
StealthHumanizer — Text Utilities
Ported from TypeScript lib/text-utils.ts → Python

Sentence splitting with abbreviation and identifier handling.
"""

import re

ABBREVIATIONS = {
    'Mr', 'Mrs', 'Ms', 'Dr', 'Prof', 'Sr', 'Jr', 'St', 'etc',
    'vs', 'i.e', 'e.g', 'Inc', 'Ltd', 'Co', 'Corp', 'Rev',
    'Gen', 'Sen', 'Rep', 'Pres', 'Hon', 'Al',
}


def split_sentences(text: str) -> list[str]:
    """
    Split text into sentences, preserving abbreviations and identifiers.
    
    Handles:
    - Abbreviations (Mr., Dr., etc.)
    - Identifiers (file.ext, 192.168.1.1)
    - Quotes after punctuation
    - Multiple whitespace
    """
    sentences = []
    current = ''
    i = 0
    while i < len(text):
        current += text[i]
        if text[i] in '.!?' and i > 0:
            before_match = text[max(0, i - 5):i + 1]
            # Protect periods inside identifiers
            is_inside_id = (text[i] == '.' and
                            text[i - 1].isalnum() and
                            i + 1 < len(text) and text[i + 1].isalnum())
            is_abbr = any(before_match.endswith(abbr + '.') for abbr in ABBREVIATIONS)
            if not is_inside_id and not is_abbr:
                # Consume closing quote after punctuation
                if i + 1 < len(text) and text[i + 1] in '"\'':
                    current += text[i + 1]
                    i += 1
                trimmed = current.strip()
                if trimmed:
                    sentences.append(trimmed)
                current = ''
        i += 1
    trimmed = current.strip()
    if trimmed:
        sentences.append(trimmed)
    return sentences


def split_paragraphs(text: str) -> list[str]:
    """Split text into paragraphs (double newline separated)."""
    return [p.strip() for p in text.split('\n\n') if p.strip()]


def word_count(text: str) -> int:
    """Count words in text."""
    return len([w for w in text.strip().split() if w])


def get_words(text: str) -> list[str]:
    """Extract words from text."""
    return [w for w in text.split() if w]


def count_syllables(word: str) -> int:
    """Estimate syllable count for a word."""
    w = re.sub(r'[^a-zA-Z]', '', word.lower())
    if len(w) <= 3:
        return 1
    w = re.sub(r'(?:[^laeiouy]es|ed|[^laeiouy]e)$', '', w)
    w = re.sub(r'^y', '', w)
    matches = re.findall(r'[aeiouy]{1,2}', w)
    return len(matches) if matches else 1


def calculate_readability(text: str) -> dict:
    """
    Calculate readability metrics for text.
    
    Returns:
        dict with Flesch Reading Ease, Flesch-Kincaid Grade, etc.
    """
    words = get_words(text)
    total_words = max(len(words), 1)
    total_sentences = max(len(split_sentences(text)), 1)
    total_syllables = sum(count_syllables(w) for w in words)
    
    avg_words_per_sentence = total_words / total_sentences
    avg_syllables_per_word = total_syllables / total_words

    flesch_reading_ease = max(0, min(100,
        206.835 - (1.015 * avg_words_per_sentence) - (84.6 * avg_syllables_per_word)
    ))

    flesch_kincaid_grade = max(0,
        (0.39 * avg_words_per_sentence) + (11.8 * avg_syllables_per_word) - 15.59
    )

    char_count = sum(len(w) for w in words)
    avg_chars_per_word = char_count / total_words
    L = avg_chars_per_word * 100
    S = (total_sentences / total_words) * 100
    coleman_liau_index = (0.0588 * L) - (0.296 * S) - 15.8

    reading_time_minutes = total_words / 225

    return {
        'flesch_reading_ease': round(flesch_reading_ease, 1),
        'flesch_kincaid_grade': round(flesch_kincaid_grade, 1),
        'coleman_liau_index': round(coleman_liau_index, 1),
        'avg_words_per_sentence': round(avg_words_per_sentence, 1),
        'avg_syllables_per_word': round(avg_syllables_per_word, 3),
        'reading_time_minutes': round(reading_time_minutes, 1),
        'total_sentences': total_sentences,
        'total_words': len(words),
        'total_syllables': total_syllables,
    }
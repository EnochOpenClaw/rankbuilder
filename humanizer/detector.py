"""
StealthHumanizer — AI Detection Engine (12 Statistical Metrics)
Ported from TypeScript lib/detector.ts → Python

Runs entirely locally — no API needed.
Returns weighted overall score + per-sentence analysis.
"""

import re
import math
from typing import Optional

# ==================== PATTERN DATABASES ====================

AI_PHRASES = [
    'it is important to note', 'it is worth mentioning', 'it is worth noting',
    'in conclusion', 'in summary', 'to summarize', 'to conclude',
    'furthermore', 'moreover', 'additionally', 'in addition',
    'it is crucial', 'it is essential', 'it is imperative',
    'plays a crucial role', 'plays an important role', 'plays a pivotal role',
    'has the potential to', 'it is evident that', 'it is clear that',
    'demonstrates the', 'illustrates the', 'showcases the',
    'underscores the', 'highlights the', 'emphasizes the',
    'on the other hand', 'in terms of', 'when it comes to',
    'as previously mentioned', 'as discussed earlier', 'as noted above',
    'it should be noted', 'it must be noted', 'needless to say',
    'last but not least', 'first and foremost', 'at the end of the day',
    'in today\'s world', 'in this day and age', 'in the modern era',
    'in the contemporary landscape', 'in the current landscape',
    'a myriad of', 'delve into', 'delves into',
    'tapestry of', 'navigating the landscape',
    'multifaceted', 'robust', 'seamless', 'streamline',
    'synergy', 'paradigm', 'paradigm shift', 'holistic',
    'innovative', 'cutting-edge', 'state-of-the-art', 'groundbreaking',
    'transformative', 'comprehensive', 'unprecedented',
    'utilize', 'facilitate', 'optimize', 'leverage',
    'implement', 'foster', 'cultivate', 'empower',
    'embark on a journey', 'sheds light on', 'brings to the forefront',
]

AI_SENTENCE_STARTERS = [
    'In this article', 'This paper', 'This study', 'This research',
    'The results', 'The findings', 'The analysis', 'The data',
    'It is widely', 'It is commonly', 'There is a',
    'One of the', 'Another important', 'A key aspect',
    'The importance of', 'The significance of', 'The role of',
    'Research has shown', 'Studies have shown', 'Evidence suggests',
]

HEDGING_PHRASES = [
    'it could be argued', 'one might consider', 'it is possible that',
    'it would seem', 'this suggests that', 'this may indicate',
    'it appears that', 'this could potentially', 'one could argue',
]

QUANTIFIERS = [
    'numerous', 'various', 'multiple', 'several', 'a variety of',
    'a multitude of', 'a range of', 'a number of', 'countless',
    'a vast array of', 'a wide range of', 'a significant number of',
]

TRANSITION_WORDS = [
    'however', 'therefore', 'moreover', 'furthermore', 'additionally',
    'consequently', 'nevertheless', 'meanwhile', 'subsequently', 'thus',
    'hence', 'accordingly', 'similarly', 'likewise', 'conversely',
    'otherwise', 'instead', 'rather', 'yet', 'still', 'moreover',
]

HUMAN_INDICATORS = [
    'basically', 'actually', 'literally', 'honestly', 'like',
    'you know', 'I mean', 'kind of', 'sort of', 'pretty much',
    'I think', 'I feel like', 'I guess', 'I\'d say', 'to be honest',
    'weirdly', 'interestingly', 'funnily enough', 'surprisingly',
    'anyway', 'so yeah', 'I dunno', 'tbh', 'imo',
]


# ==================== CORE ANALYSIS FUNCTIONS ====================

def _split_into_sentences(text: str) -> list[str]:
    abbreviations = {'Mr', 'Mrs', 'Ms', 'Dr', 'Prof', 'Sr', 'Jr', 'St', 'etc',
                     'vs', 'i.e', 'e.g', 'Inc', 'Ltd', 'Co', 'Corp'}
    sentences = []
    current = ''
    i = 0
    while i < len(text):
        current += text[i]
        if text[i] in '.!?' and i > 0:
            before_match = text[max(0, i - 5):i + 1]
            is_inside_id = (text[i] == '.' and
                            text[i - 1].isalnum() and
                            i + 1 < len(text) and text[i + 1].isalnum())
            is_abbr = any(before_match.endswith(abbr + '.') for abbr in abbreviations)
            if not is_inside_id and not is_abbr:
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


def _calculate_perplexity(text: str) -> float:
    words = text.lower().split()
    if len(words) < 5:
        return 50.0
    freq = {}
    for w in words:
        freq[w] = freq.get(w, 0) + 1
    values = list(freq.values())
    max_freq = max(values)
    avg_freq = len(words) / len(values)
    uniformity = max_freq / avg_freq

    bigrams = []
    for i in range(len(words) - 1):
        bigrams.append(words[i] + ' ' + words[i + 1])
    bigram_freq = {}
    for b in bigrams:
        bigram_freq[b] = bigram_freq.get(b, 0) + 1
    unique_bigrams = len(bigram_freq)
    bigram_diversity = unique_bigrams / len(bigrams) if bigrams else 0

    score = (bigram_diversity * 60) + ((100 - uniformity * 15) * 0.4)
    return max(0, min(100, score))


def _calculate_burstiness(sentences: list[str]) -> float:
    if len(sentences) < 3:
        return 50.0
    lengths = [len(s.split()) for s in sentences]
    avg = sum(lengths) / len(lengths)
    variance = sum((l - avg) ** 2 for l in lengths) / len(lengths)
    std_dev = math.sqrt(variance)
    burstiness = (std_dev / avg) * 100 if avg > 0 else 0
    return min(100, burstiness * 2.5)


def _calculate_vocabulary_diversity(text: str) -> float:
    words = re.findall(r'[a-zA-Z]+', text.lower())
    words = [w for w in words if len(w) > 2]
    if len(words) < 10:
        return 50.0
    return (len(set(words)) / len(words)) * 100


def _calculate_sentence_length_variation(sentences: list[str]) -> float:
    if len(sentences) < 3:
        return 50.0
    lengths = [len(s.split()) for s in sentences]
    max_len = max(lengths)
    min_len = min(lengths)
    avg = sum(lengths) / len(lengths)
    return min(100, ((max_len - min_len) / avg) * 60) if avg > 0 else 50


def _calculate_transition_frequency(text: str) -> float:
    words = text.lower().split()
    if len(words) < 10:
        return 50.0
    count = 0
    lower = text.lower()
    for w in TRANSITION_WORDS:
        count += len(re.findall(r'\b' + re.escape(w) + r'\b', lower))
    return min(100, (count / len(words)) * 1000)


def _calculate_passive_voice_ratio(text: str) -> float:
    sentences = _split_into_sentences(text)
    if len(sentences) < 2:
        return 50.0
    patterns = [
        re.compile(r'\b(is|are|was|were|been|being)\s+\w+ed\b', re.I),
        re.compile(r'\b(is|are|was|were|been|being)\s+\w+en\b', re.I),
    ]
    passive_count = 0
    for s in sentences:
        for p in patterns:
            passive_count += len(p.findall(s))
    return min(100, (passive_count / len(sentences)) * 100)


def _calculate_ai_phrase_density(text: str) -> float:
    lower = text.lower()
    count = 0
    for phrase in AI_PHRASES:
        if phrase in lower:
            count += 1
    return min(100, (count / max(len(_split_into_sentences(text)), 1)) * 20)


def _calculate_sentence_start_diversity(sentences: list[str]) -> float:
    if len(sentences) < 4:
        return 50.0
    starts = [re.sub(r'[^a-z]', '', s.split()[0].lower()) for s in sentences if s.split()]
    unique = len(set(starts))
    return (unique / len(starts)) * 100


def _calculate_pronoun_usage(text: str) -> float:
    personal = ['I', 'me', 'my', 'we', 'us', 'our', 'you', 'your']
    words = text.split()
    count = sum(1 for w in words if w in personal)
    ratio = (count / max(len(words), 1)) * 500
    return min(100, ratio)


def _calculate_hedging_frequency(text: str) -> float:
    lower = text.lower()
    count = 0
    for phrase in HEDGING_PHRASES:
        if phrase in lower:
            count += 1
    return min(100, count * 15)


def _calculate_quantifier_overuse(text: str) -> float:
    lower = text.lower()
    count = 0
    for q in QUANTIFIERS:
        count += len(re.findall(r'\b' + re.escape(q) + r'\b', lower))
    return min(100, count * 10)


# ==================== SENTENCE-LEVEL ANALYSIS ====================

def _analyze_sentence(sentence: str, calibrated_thresholds: Optional[dict] = None) -> dict:
    issues = []
    score = 35

    lower = sentence.lower()

    # AI phrases (heavy penalty)
    ai_phrase_count = 0
    for phrase in AI_PHRASES:
        if phrase in lower:
            ai_phrase_count += 1
            issues.append(f'AI phrase: "{phrase}"')
    score -= ai_phrase_count * 22

    # AI sentence starters
    for starter in AI_SENTENCE_STARTERS:
        if lower.startswith(starter.lower()):
            score -= 12
            issues.append('AI-like sentence opener')
            break

    # Sentence length
    words = sentence.split()
    word_count = len(words)
    if word_count > 35:
        issues.append('Very long sentence')
        score -= 18
    if word_count > 25:
        issues.append('Long sentence (AI tendency)')
        score -= 8
    if 2 <= word_count <= 5:
        score += 5

    # Formal vocabulary
    if re.search(r'\b(utilize|implement|facilitate|leverage|foster|cultivate|empower)\b', sentence, re.I):
        issues.append('Formal/AI vocabulary')
        score -= 15

    # Passive voice
    if re.search(r'\b(is|are|was|were|been|being)\s+\w+ed\b', sentence, re.I):
        issues.append('Passive voice')
        score -= 8

    # Hedging
    for h in HEDGING_PHRASES:
        if h in lower:
            issues.append('Hedging language')
            score -= 10
            break

    # Quantifiers
    for q in QUANTIFIERS:
        if q in lower:
            score -= 6
            break

    # Human indicators (weak signals)
    human_signals = sum(1 for h in HUMAN_INDICATORS if h in lower)
    score += human_signals * 0.5

    # Contractions
    contractions = re.findall(r'[a-zA-Z]{1,15}\'(?:t|s|re|ve|ll|d|m)\b', sentence, re.I)
    if contractions:
        score += len(contractions) * 0.5

    # First person
    if re.search(r'\b(I|me|my|we|us|our)\b', sentence):
        score += 1

    # Second person
    if re.search(r'\byou\b', sentence, re.I):
        score += 0.5

    # Questions
    if sentence.strip().endswith('?'):
        score += 1

    # Exclamation
    if sentence.strip().endswith('!'):
        score += 1

    # Em-dashes
    if '—' in sentence or ' - ' in sentence:
        score += 1

    # Parenthetical asides
    if '(' in sentence and ')' in sentence:
        score += 1

    # Starts with conjunction
    if re.match(r'^(and|but|so|because|also|plus|or|well|ok|hey)\b', sentence, re.I):
        score += 1

    # Uniform structure penalty
    if (len(words) >= 10 and len(words) <= 25 and
            all(re.match(r'^[\w,.!?]+$', w) for w in words) and
            re.search(r'[.!?]$', sentence)):
        issues.append('Uniform structure')
        score -= 18

    score = max(0, min(100, score))

    s_floor = calibrated_thresholds.get('humanScoreMin', 55) if calibrated_thresholds else 55
    s_mid = max(20, s_floor - 20)

    if score >= s_floor:
        classification = 'human'
    elif score >= s_mid:
        classification = 'maybe'
    else:
        classification = 'ai'

    return {
        'text': sentence,
        'score': score,
        'classification': classification,
        'issues': issues,
    }


# ==================== MAIN DETECTION FUNCTION ====================


def detect_ai(text: str, calibrated_thresholds: Optional[dict] = None) -> dict:
    """
    Analyze text for AI-generated patterns. Returns a dict with:
    - score: 0-100 (higher = more human-like)
    - confidence_interval: {lower, upper}
    - sentences: list of per-sentence analysis
    - overall_verdict: 'human', 'mixed', or 'ai'
    - analysis: dict of 12 statistical metrics
    """
    sentences = _split_into_sentences(text)
    sentence_results = [_analyze_sentence(s, calibrated_thresholds) for s in sentences]

    perplexity = _calculate_perplexity(text)
    burstiness = _calculate_burstiness(sentences)
    vocabulary_diversity = _calculate_vocabulary_diversity(text)
    sentence_length_variation = _calculate_sentence_length_variation(sentences)
    transition_frequency = _calculate_transition_frequency(text)
    passive_voice_ratio = _calculate_passive_voice_ratio(text)
    ai_phrase_density = _calculate_ai_phrase_density(text)
    sentence_start_diversity = _calculate_sentence_start_diversity(sentences)
    pronoun_usage = _calculate_pronoun_usage(text)
    hedging_frequency = _calculate_hedging_frequency(text)
    quantifier_overuse = _calculate_quantifier_overuse(text)

    weights = {
        'sentence_avg': 0.25,
        'perplexity': 0.15,
        'burstiness': 0.15,
        'vocabulary': 0.05,
        'sentence_variation': 0.08,
        'transitions': 0.08,
        'passive': 0.05,
        'ai_phrases': 0.12,
        'sentence_start': 0.05,
        'pronoun': 0.03,
        'hedging': 0.03,
        'quantifier': 0.02,
    }

    sentence_avg = (sum(r['score'] for r in sentence_results) / len(sentence_results)
                    if sentence_results else 50)

    overall_score = (
        sentence_avg * weights['sentence_avg'] +
        perplexity * weights['perplexity'] +
        burstiness * weights['burstiness'] +
        vocabulary_diversity * weights['vocabulary'] +
        sentence_length_variation * weights['sentence_variation'] +
        (100 - transition_frequency) * weights['transitions'] +
        (100 - passive_voice_ratio) * weights['passive'] +
        (100 - ai_phrase_density) * weights['ai_phrases'] +
        sentence_start_diversity * weights['sentence_start'] +
        pronoun_usage * weights['pronoun'] +
        (100 - hedging_frequency) * weights['hedging'] +
        (100 - quantifier_overuse) * weights['quantifier']
    )

    human_floor = calibrated_thresholds.get('humanScoreMin', 55) if calibrated_thresholds else 55
    mixed_floor = max(20, human_floor - 20)

    if overall_score >= human_floor:
        overall_verdict = 'human'
    elif overall_score >= mixed_floor:
        overall_verdict = 'mixed'
    else:
        overall_verdict = 'ai'

    # Confidence interval
    sentence_score_variance = (
        sum((r['score'] - overall_score) ** 2 for r in sentence_results) / len(sentence_results)
        if len(sentence_results) > 1 else 400
    )
    margin = min(15, round(math.sqrt(sentence_score_variance) * 0.6 + (6 if len(sentence_results) < 5 else 2)))
    confidence_interval = {
        'lower': max(0, round(overall_score - margin)),
        'upper': min(100, round(overall_score + margin)),
    }

    return {
        'score': round(overall_score),
        'confidence_interval': confidence_interval,
        'sentences': sentence_results,
        'overall_verdict': overall_verdict,
        'analysis': {
            'perplexity': round(perplexity),
            'burstiness': round(burstiness),
            'vocabulary_diversity': round(vocabulary_diversity),
            'sentence_length_variation': round(sentence_length_variation),
            'transition_frequency': round(transition_frequency),
            'passive_voice_ratio': round(passive_voice_ratio),
            'ai_phrase_density': round(ai_phrase_density),
            'sentence_start_diversity': round(sentence_start_diversity),
            'pronoun_usage': round(pronoun_usage),
            'hedging_frequency': round(hedging_frequency),
            'quantifier_overuse': round(quantifier_overuse),
        },
    }


# Alias for import compatibility
DetectionResult = dict
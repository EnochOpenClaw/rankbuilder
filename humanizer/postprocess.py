"""
StealthHumanizer Layer 2 — Deterministic Post-Processing Engine
Ported from TypeScript lib/postprocess.ts → Python

Applies all non-LLM transformations:
- AI em-dash stripping
- Aggressive synonym swap (AI vocab removal)
- Collocation replacements
- Safe synonym swapping (25% probability)
- Punctuation noise
- Sentence length manipulation
- Flow disruption
- Sentence reordering
- Paragraph randomization
- Typographic variation
"""

import random
import re
from typing import Optional

from .collocations import apply_collocation, apply_random_collocation
from .synonyms import get_random_safe_synonym

# ==================== HELPERS ====================


def _split_sentences(text: str) -> list[str]:
    """Split text into sentences with abbreviation and identifier handling."""
    abbreviations = {'Mr', 'Mrs', 'Ms', 'Dr', 'Prof', 'Sr', 'Jr', 'St', 'etc',
                     'vs', 'i.e', 'e.g', 'Inc', 'Ltd', 'Co', 'Corp', 'Rev',
                     'Gen', 'Sen', 'Rep', 'Pres', 'Hon', 'al'}
    sentences = []
    current = ''
    i = 0
    while i < len(text):
        current += text[i]
        if text[i] in '.!?' and i > 0:
            before_match = text[max(0, i - 5):i + 1]
            # Protect periods inside identifiers (e.g., file.ext, 3.x, 192.168.1.1)
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


def _split_paragraphs(text: str) -> list[str]:
    return [p.strip() for p in text.split('\n\n') if p.strip()]


def _join_paragraphs(paragraphs: list[str]) -> str:
    return '\n\n'.join(paragraphs)


def _word_count(text: str) -> int:
    return len([w for w in text.strip().split() if w])


def _looks_like_proper_noun(word: str, position: int, sentence: str) -> bool:
    if position == 0:
        return False
    if not word or not word[0].isupper():
        return False
    trimmed = sentence.strip()
    if trimmed.startswith(word):
        return False
    return True


def _is_in_quotes(text: str, index: int) -> bool:
    in_quote = False
    for i in range(index):
        if text[i] == '"':
            in_quote = not in_quote
        if text[i] == "'" and (i == 0 or text[i - 1] != 's') and (i == len(text) - 1 or text[i + 1] != 's'):
            in_quote = not in_quote
    return in_quote


# ==================== 2a. SYNONYM SWAPPING ====================


def _swap_synonyms(text: str) -> str:
    words = re.split(r'(\s+)', text)
    result = []
    for i, word in enumerate(words):
        # Skip whitespace, punctuation, numbers, short words, words in quotes
        if not word or re.match(r'^\s+$', word) or re.match(r'^[^a-zA-Z]+$', word) or len(word) < 4:
            result.append(word)
            continue
        # Skip all-caps words
        if word == word.upper():
            result.append(word)
            continue
        # Skip words in quotes
        full_text_so_far = ''.join(words[:i])
        if _is_in_quotes(text, len(full_text_so_far)):
            result.append(word)
            continue
        # Skip proper nouns
        sentence_context = ''.join(words[max(0, i - 20):i + 20])
        if _looks_like_proper_noun(word, i, sentence_context):
            result.append(word)
            continue
        # 25% chance to swap
        if random.random() < 0.25:
            synonym = get_random_safe_synonym(word)
            if synonym:
                # Preserve capitalization
                if word[0].isupper() and synonym[0].islower():
                    result.append(synonym[0].upper() + synonym[1:])
                else:
                    result.append(synonym)
                continue
        result.append(word)
    return ''.join(result)


# ==================== TYPOGRAPHIC VARIATION ====================


def _add_typographic_variation(text: str) -> str:
    result = text
    # Occasionally replace straight quotes with smart quotes
    if random.random() < 0.15:
        quoted = list(re.finditer(r'"([^"]{2,})"', result))
        if quoted:
            q = random.choice(quoted)
            word = q.group(1)
            result = result[:q.start()] + f'\u201C{word}\u201D' + result[q.end():]
    # Occasionally use en-dash for number ranges
    if random.random() < 0.20:
        result = re.sub(r'(\d)\s*[-\u2013]\s*(\d)',
                        lambda m: f'{m.group(1)}\u2013{m.group(2)}' if random.random() < 0.3 else m.group(0),
                        result)
    return result


# ==================== 2b. SENTENCE REORDERING ====================


def _reorder_sentences(paragraph: str) -> str:
    sentences = _split_sentences(paragraph)
    if len(sentences) <= 2:
        return paragraph

    pronoun_pattern = re.compile(r'\b(he|she|it|they|this|that|these|those|his|her|its|their)\b', re.I)

    # Keep first and last in place, swap 20-30% of middle sentences
    middle = sentences[1:-1]
    if len(middle) <= 1:
        return paragraph

    swap_count = max(1, int(len(middle) * (0.2 + random.random() * 0.1)))
    result = list(middle)

    for _ in range(swap_count):
        i = random.randint(0, len(result) - 1)
        j = random.randint(0, len(result) - 1)
        if i == j:
            continue

        # Check pronoun references
        after_i = ' '.join(result[min(i, j) + 1:])
        sent_i = result[i]
        sent_j = result[j]
        first_word_i = sent_i.split()[0] if sent_i.split() else ''
        first_word_j = sent_j.split()[0] if sent_j.split() else ''

        if pronoun_pattern.match(first_word_i) or pronoun_pattern.match(first_word_j):
            if random.random() < 0.5:
                continue

        result[i], result[j] = result[j], result[i]

    return ' '.join([sentences[0]] + result + [sentences[-1]])


# ==================== 2b'. STRIP AI EM-DASHES ====================


def _strip_ai_dashes(text: str) -> str:
    """Replace em-dashes with commas. Numeric ranges preserved."""
    RANGE_PLACEHOLDER = '\x01RANGE\x01'
    text = re.sub(r'(\d)\s*[\u2013\u2014\u2015]\s*(\d)', lambda m: f'{m.group(1)}{RANGE_PLACEHOLDER}{m.group(2)}', text)
    text = re.sub(r'\s*[\u2014\u2013\u2015]\s*', ', ', text)
    text = text.replace(RANGE_PLACEHOLDER, '\u2013')
    return text


# ==================== 2c. PUNCTUATION NOISE ====================

CONTRACTIONS = [
    ("don't", "do not"), ("can't", "cannot"), ("won't", "will not"),
    ("isn't", "is not"), ("aren't", "are not"), ("wasn't", "was not"),
    ("weren't", "were not"), ("hasn't", "has not"), ("haven't", "have not"),
    ("hadn't", "had not"), ("doesn't", "does not"), ("didn't", "did not"),
    ("shouldn't", "should not"), ("wouldn't", "would not"), ("couldn't", "could not"),
    ("I'm", "I am"), ("you're", "you are"), ("he's", "he is"),
    ("she's", "she is"), ("it's", "it is"), ("we're", "we are"),
    ("they're", "they are"), ("I've", "I have"), ("you've", "you have"),
    ("we've", "we have"), ("they've", "they have"), ("I'll", "I will"),
    ("you'll", "you will"), ("he'll", "he will"), ("she'll", "she will"),
    ("we'll", "we will"), ("they'll", "they will"), ("I'd", "I would"),
    ("you'd", "you would"), ("he'd", "he would"), ("she'd", "she would"),
    ("let's", "let us"), ("that's", "that is"), ("there's", "there is"),
    ("here's", "here is"), ("what's", "what is"), ("who's", "who is"),
]


def _add_punctuation_noise(text: str) -> str:
    result = text

    # 10% chance: double space between some sentences
    if random.random() < 0.10:
        sentence_ends = list(re.finditer(r'([.!?])\s+', result))
        if sentence_ends:
            idx = random.randint(0, len(sentence_ends) - 1)
            match = sentence_ends[idx]
            result = result[:match.start()] + match.group(1) + '  ' + result[match.end():]

    # 5% chance: semicolon between related sentences
    if random.random() < 0.05:
        period_spaces = list(re.finditer(r'\.\s+(?=[A-Z])', result))
        if period_spaces:
            p = random.choice(period_spaces)
            before = result[:p.start()]
            after = result[p.end():]
            result = before + '; ' + after[0].lower() + after[1:]

    # Contractions expansion/randomization
    if random.random() < 0.15:
        short, expanded = random.choice(CONTRACTIONS)
        if random.random() < 0.5:
            # Expand contraction
            result = re.sub(r'\b' + re.escape(short) + r'\b', expanded, result, flags=re.I, count=1)
        else:
            # Contract (only if expanded form exists)
            result = re.sub(r'\b' + re.escape(expanded) + r'\b', short, result, flags=re.I, count=1)

    return result


# ==================== 2d. SENTENCE LENGTH MANIPULATION ====================

FILLER_PHRASES = [
    'in my experience,',
    'from what I\'ve seen,',
    'I\'d argue that',
    'honestly,',
    'the way I see it,',
    'from my perspective,',
    'if you think about it,',
    'interestingly,',
    'to be fair,',
    'in practice,',
    'at least in my view,',
    'one thing that stands out is',
    'what strikes me is',
    'it\'s worth pointing out that',
    'as far as I can tell,',
]


def _manipulate_sentence_lengths(text: str) -> str:
    sentences = _split_sentences(text)
    result = []

    i = 0
    while i < len(sentences):
        sentence = sentences[i]
        words = sentence.strip().split()
        wc = len(words)

        # Merge two consecutive short sentences
        if (wc < 8 and i < len(sentences) - 1 and
                len(sentences[i + 1].strip().split()) < 8 and
                random.random() < 0.20):
            next_sent = sentences[i + 1].strip()
            conjunction = random.choice(['and', 'but', 'while', 'whereas'])
            merged = re.sub(r'[.!?]+$', '', sentence.strip()) + ', ' + conjunction + ' ' + next_sent[0].lower() + next_sent[1:]
            result.append(merged)
            i += 2
            continue

        # Split long sentences (>30 words)
        if wc > 30 and random.random() < 0.30:
            text_sent = sentence.strip()
            break_patterns = [
                re.compile(r',\s+(?:and|but|or|while)\s+', re.I),
                re.compile(r',\s+(?:which|that|where|when|who)\s+', re.I),
                re.compile(r',\s+(?:however|therefore|moreover|furthermore)\s+', re.I),
            ]

            break_point = -1
            replacement = '. '

            for pattern in break_patterns:
                match = pattern.search(text_sent)
                if match and match.start() > 10 and match.start() < len(text_sent) - 10:
                    break_point = match.start()
                    conjunction = match.group(0).replace(', ', '')
                    replacement = '. ' + conjunction[0].upper() + conjunction[1:]
                    break

            # Fallback: split at a comma in the middle
            if break_point == -1:
                commas = list(re.finditer(r',\s+', text_sent))
                middle_commas = [c for c in commas
                                 if c.start() > len(text_sent) * 0.3 and c.start() < len(text_sent) * 0.7]
                if middle_commas:
                    c = random.choice(middle_commas)
                    break_point = c.start()
                    replacement = '. '

            if break_point > 0:
                first = text_sent[:break_point].rstrip(',:')
                second = text_sent[break_point:].lstrip(', ')
                second_cap = second[0].upper() + second[1:]
                result.append(first + '. ' + second_cap)
                i += 1
                continue

        result.append(sentence)
        i += 1

    return ' '.join(result)


# ==================== 2h. AGGRESSIVE AI VOCABULARY REMOVAL ====================


def _aggressive_synonym_swap(text: str, style: Optional[str] = None) -> str:
    is_formal = style in ('academic', 'professional', 'technical')

    replacements = [
        (re.compile(r'\bdemonstrates?\b', re.I), ['shows', 'makes clear', 'reveals', 'tells us']),
        (re.compile(r'\bfurthermore\b', re.I), ['also', 'and', 'on top of that', 'plus']),
        (re.compile(r'\bmoreover\b', re.I), ['also', 'and', 'besides', "what's more"]),
        (re.compile(r'\badditionally\b', re.I), ['also', 'and', 'plus', 'on top of that']),
        (re.compile(r'\bconsequently\b', re.I), ['so', 'which means', 'as a result', 'because of that']),
        (re.compile(r'\bsignificantly\b', re.I),
         ['noticeably', 'considerably', 'to a meaningful extent'] if is_formal else ['a lot', 'noticeably', 'quite a bit']),
        (re.compile(r'\bsubstantially\b', re.I),
         ['considerably', 'to a large extent', 'materially'] if is_formal else ['a lot', 'quite a bit', 'in a big way']),
        (re.compile(r'\bnotably\b', re.I), ['especially', 'worth pointing out', 'interestingly']),
        (re.compile(r'\bremarkably\b', re.I),
         ['surprisingly', 'strikingly', 'to a notable degree'] if is_formal else ['surprisingly', 'interestingly', 'quite a bit']),
        (re.compile(r'\bparticularly\b', re.I), ['especially', 'mainly', 'mostly']),
        (re.compile(r'\bessentially\b', re.I),
         ['fundamentally', 'at its core', 'in essence'] if is_formal else ['basically', 'at its core', 'when you get down to it']),
        (re.compile(r'\bfundamentally\b', re.I),
         ['at its core', 'in essence', 'in principle'] if is_formal else ['basically', 'at its core', 'really']),
        (re.compile(r'\bultimately\b', re.I),
         ['in the end', 'in the final analysis', 'as a conclusion'] if is_formal else ['in the end', 'at the end of the day', 'when all is said and done']),
        (re.compile(r'\binherently\b', re.I), ['naturally', 'by its nature', 'built into it']),
        (re.compile(r'\butilize\b', re.I), ['use', 'work with', 'make use of']),
        (re.compile(r'\bfacilitate\b', re.I), ['help with', 'make easier', 'enable']),
        (re.compile(r'\bleverage\b', re.I), ['use', 'take advantage of', 'build on']),
        (re.compile(r'\boptimize\b', re.I), ['improve', 'make better', 'fine-tune']),
        (re.compile(r'\bimplement\b', re.I), ['set up', 'put in place', 'start using']),
        (re.compile(r'\bcomprehensive\b', re.I), ['thorough', 'complete', 'full']),
        (re.compile(r'\binnovative\b', re.I), ['new', 'fresh', 'creative', 'different']),
        (re.compile(r'\btransformative\b', re.I),
         ['major', 'significant', 'far-reaching'] if is_formal else ['major', 'really big', 'a big deal']),
        (re.compile(r'\bunprecedented\b', re.I), ['never seen before', 'completely new', 'totally unusual']),
        (re.compile(r'\bstreamline\b', re.I), ['simplify', 'make smoother', 'speed up']),
        (re.compile(r'\bcrucial\b', re.I), ['key', 'important', 'really matters']),
        (re.compile(r'\bpivotal\b', re.I), ['key', 'important', 'central']),
        (re.compile(r'\bit is evident that\b', re.I), ['clearly', 'obviously', 'you can see that']),
        (re.compile(r'\bit is clear that\b', re.I), ['clearly', 'obviously']),
        (re.compile(r'\bplays? a crucial role\b', re.I),
         ['is central to', 'is a key factor in', 'has a significant impact on'] if is_formal else ['matters a lot', 'is really important', 'makes a big difference']),
        (re.compile(r'\bplays? an important role\b', re.I),
         ['is significant in', 'contributes meaningfully to', 'is a key part of'] if is_formal else ['matters', 'is important', 'makes a difference']),
        (re.compile(r'\bhas the potential to\b', re.I), ['could', 'might', 'stands to']),
        (re.compile(r'\bin today\'s world\b', re.I), ['now', 'these days', 'right now']),
        (re.compile(r'\bin the modern era\b', re.I), ['now', 'these days']),
        (re.compile(r'\bin conclusion\b', re.I), ['']),
        (re.compile(r'\bin summary\b', re.I), ['']),
        (re.compile(r'\bto summarize\b', re.I), ['']),
        (re.compile(r'\bit is important to note\b', re.I), ['']),
        (re.compile(r'\bit is worth noting(?: that)?\b', re.I), ['']),
        (re.compile(r'\bit is worth mentioning\b', re.I), ['']),
        (re.compile(r'\bdelves? into\b', re.I), ['looks at', 'digs into', 'explores']),
        (re.compile(r'\blandscape\b', re.I), ['space', 'area', 'world', 'field']),
        (re.compile(r'\bmultifaceted\b', re.I), ['complex', 'complicated', 'many-sided']),
        (re.compile(r'\bembark on a journey\b', re.I), ['start', 'begin', 'get into']),
        (re.compile(r'\bseamless(ly)?\b', re.I), ['smooth', 'easy', 'natural']),
        (re.compile(r'\bnumerous\b', re.I),
         ['many', 'several', 'a considerable number of'] if is_formal else ['many', 'a lot of', 'tons of']),
        (re.compile(r'\ba variety of\b', re.I), ['different', 'various', 'all kinds of']),
        (re.compile(r'\ba multitude of\b', re.I),
         ['many', 'numerous', 'a significant number of'] if is_formal else ['many', 'a lot of', 'tons of']),
        (re.compile(r'\ba significant number of\b', re.I),
         ['many', 'numerous', 'a considerable number of'] if is_formal else ['many', 'a lot of', 'quite a few']),
        (re.compile(r'\bin today\'s digital landscape\b', re.I), ['now', 'these days', 'in the current environment']),
        (re.compile(r'\bin the realm of\b', re.I),
         ['in the field of', 'in the area of', 'when it comes to'] if is_formal else ['in', 'when it comes to', 'for']),
        (re.compile(r'\bas we navigate\b', re.I), ['as we deal with', 'as we work through', 'when dealing with']),
        (re.compile(r'\btapestry of\b', re.I), ['mix of', 'variety of', 'collection of']),
        (re.compile(r'\bshowcase\b', re.I), ['show', 'display', 'demonstrate', 'highlight']),
        (re.compile(r'\brobust\b', re.I),
         ['strong', 'solid', 'well-built'] if is_formal else ['strong', 'solid', 'reliable']),
        (re.compile(r'\bdynamic\b', re.I), ['active', 'changing', 'flexible', 'adaptable']),
        (re.compile(r'\bmeticulous(ly)?\b', re.I),
         ['careful', 'thorough', 'detailed'] if is_formal else ['careful', 'thorough', 'precise']),
        (re.compile(r'\bempowers?\b', re.I), ['enables', 'allows', 'helps', 'lets']),
        (re.compile(r'\brevolutionize\b', re.I), ['change', 'transform', 'improve dramatically']),
        (re.compile(r'\bcutting-edge\b', re.I), ['latest', 'newest', 'modern', 'advanced']),
        (re.compile(r'\bstate-of-the-art\b', re.I), ['latest', 'most advanced', 'top-of-the-line']),
        (re.compile(r'\bgame-changer\b', re.I), ['big deal', 'major shift', 'important development']),
        (re.compile(r'\bparadigm shift\b', re.I), ['major change', 'fundamental shift', 'big shift']),
        (re.compile(r'\bin the ever-evolving\b', re.I), ['in the changing', 'in the growing']),
        (re.compile(r'\bmeticulously crafted\b', re.I), ['carefully made', 'well-designed', 'thoughtfully built']),
        (re.compile(r'\bholistic\b', re.I), ['complete', 'all-around', 'full-picture']),
        (re.compile(r'\bgroundbreaking\b', re.I), ['revolutionary', 'huge', 'game-changing']),
        (re.compile(r'\bbest practices\b', re.I), ['smart approaches', 'proven methods', 'what works']),
        (re.compile(r'\bnavigating\b', re.I), ['working through', 'dealing with', 'handling']),
    ]

    result = text
    for pattern, alternatives in replacements:
        def replacer(m):
            return random.choice(alternatives)
        result = pattern.sub(replacer, result)

    # Clean up double spaces from removed phrases
    result = re.sub(r'\s{2,}', ' ', result)
    result = re.sub(r'\.\s*\.', '.', result)
    result = re.sub(r'\s+,', ',', result)
    return result.strip()


# ==================== 2i. FLOW DISRUPTION ====================


def _disrupt_flow(text: str, style: Optional[str] = None) -> str:
    is_formal = style in ('academic', 'professional', 'technical')
    paragraphs = _split_paragraphs(text)

    result = []
    for p in paragraphs:
        sentences = _split_sentences(p)
        if len(sentences) < 2:
            result.append(p)
            continue

        sent_result = list(sentences)

        if is_formal:
            # Formal: mild insertions
            if random.random() < 0.20 and len(sent_result) >= 3:
                formal_insertions = [
                    '— though this remains debated',
                    '— at least in principle',
                    'which is worth considering.',
                    'notably.',
                    '— a point worth emphasizing.',
                    'in practice.',
                ]
                idx = random.randint(1, len(sent_result) - 1)
                sent_result.insert(idx, random.choice(formal_insertions))
            if random.random() < 0.15:
                formal_starters = ['Importantly, ', 'In practice, ', 'Notably, ', 'As it turns out, ', 'Looking at the data, ']
                sent_result[0] = random.choice(formal_starters) + sent_result[0][0].lower() + sent_result[0][1:]
        else:
            # Casual: short insertions
            if random.random() < 0.30 and len(sent_result) >= 3:
                insertions = ['Right.', 'Exactly.', 'Makes sense.', 'Think about that.', 'Hmm.', 'Interesting.', 'Yeah.',
                              'No, really.', 'Honestly.', 'True story.', 'Funny enough.']
                idx = random.randint(1, len(sent_result) - 1)
                sent_result.insert(idx, random.choice(insertions))
            # Start with conjunction
            if random.random() < 0.15:
                starters = ['And', 'But', 'So', 'Plus', 'Also']
                sent_result[0] = random.choice(starters) + ' ' + sent_result[0][0].lower() + sent_result[0][1:]
            # Add trailing thought
            if random.random() < 0.10:
                trailing = ["Or at least that's the idea.", "You get the picture.", "Well, mostly.",
                            "In theory, anyway.", "For what it's worth."]
                sent_result.append(' ' + random.choice(trailing))

        result.append(' '.join(sent_result))

    return '\n\n'.join(result)


# ==================== 2j. PARAGRAPH STRUCTURE RANDOMIZATION ====================


def _randomize_paragraphs(text: str) -> str:
    paragraphs = _split_paragraphs(text)
    if len(paragraphs) <= 1:
        return text

    result = []
    i = 0
    while i < len(paragraphs):
        p = paragraphs[i]
        sentences = _split_sentences(p)

        # 20% chance to split a paragraph into two
        if len(sentences) >= 4 and random.random() < 0.20:
            split_point = 1 + random.randint(0, len(sentences) - 3)
            first = ' '.join(sentences[:split_point])
            second = ' '.join(sentences[split_point:])
            result.append(first)
            result.append(second)
            i += 1
            continue

        # 20% chance to merge with next paragraph if both are short
        if (i < len(paragraphs) - 1 and
                len(sentences) <= 2 and
                len(_split_sentences(paragraphs[i + 1])) <= 2 and
                random.random() < 0.20):
            result.append(p + ' ' + paragraphs[i + 1])
            i += 2
            continue

        # 5% chance to add a one-sentence paragraph emphasis
        if random.random() < 0.05 and len(sentences) >= 3:
            emphasize_idx = 1 + random.randint(0, len(sentences) - 3)
            emphasized = sentences[emphasize_idx]
            remaining = [s for j, s in enumerate(sentences) if j != emphasize_idx]
            result.append(' '.join(remaining))
            result.append(emphasized)
            i += 1
            continue

        result.append(p)
        i += 1

    return '\n\n'.join(result)


# ==================== READABILITY GUARD ====================


def _calculate_readability(text: str) -> dict:
    """Simple Flesch Reading Ease calculation."""
    sentences = [s for s in re.split(r'[.!?]+', text) if s.strip()]
    words = [w for w in re.split(r'\s+', text.strip()) if w]
    total_words = max(len(words), 1)
    total_sentences = max(len(sentences), 1)

    total_syllables = 0
    for word in words:
        w = re.sub(r'[^a-zA-Z]', '', word.lower())
        if len(w) <= 3:
            total_syllables += 1
            continue
        w = re.sub(r'(?:[^laeiouy]es|ed|[^laeiouy]e)$', '', w)
        w = re.sub(r'^y', '', w)
        matches = re.findall(r'[aeiouy]{1,2}', w)
        total_syllables += len(matches) if matches else 1

    avg_words_per_sentence = total_words / total_sentences
    avg_syllables_per_word = total_syllables / total_words

    flesch = max(0, min(100,
        206.835 - (1.015 * avg_words_per_sentence) - (84.6 * avg_syllables_per_word)))

    return {'flesch': flesch}


def _readability_guard(original: str, processed: str) -> str:
    """If readability drops by >15 points, revert to lighter processing."""
    orig_scores = _calculate_readability(original)
    proc_scores = _calculate_readability(processed)
    drop = orig_scores['flesch'] - proc_scores['flesch']

    if drop > 15:
        # Revert to lighter version
        safe = _aggressive_synonym_swap(original)
        safe = apply_collocation(safe)
        safe = _swap_synonyms(safe)
        safe = _add_typographic_variation(safe)
        safe = re.sub(r'\s{2,}', ' ', safe)
        safe = re.sub(r'\n{3,}', '\n\n', safe)
        return safe.strip()

    return processed


# ==================== MAIN POST-PROCESS FUNCTION ====================


def postprocess(text: str, light: bool = False, style: Optional[str] = None,
                aggressive: bool = False, skip_readability_guard: bool = False) -> str:
    """
    Apply all non-LLM post-processing transformations.
    
    Args:
        text: Input text to humanize.
        light: If True, apply lighter version (for Layer 4 polish).
        style: 'academic', 'casual', 'professional', 'creative', 'technical'
        aggressive: If True, apply extra disruption and paragraph randomization.
        skip_readability_guard: If True, skip the readability guard check.
    
    Returns:
        Humanized text string.
    """
    result = text

    # ALWAYS: Strip em-dashes (strongest AI tell)
    result = _strip_ai_dashes(result)

    # Aggressive AI vocabulary removal (style-aware)
    result = _aggressive_synonym_swap(result, style)

    # ALWAYS: Collocation replacements
    result = apply_collocation(result)

    if light:
        result = _swap_synonyms(result)
        if random.random() < 0.5:
            result = _add_punctuation_noise(result)
        result = result.replace(', ,', ',')
        result = re.sub(r'\s+,', ',', result)
        result = re.sub(r'\s{2,}', ' ', result).strip()
        return result

    # Full post-processing pipeline
    result = _swap_synonyms(result)
    result = _add_punctuation_noise(result)
    result = _manipulate_sentence_lengths(result)
    result = _disrupt_flow(result, style)

    # Sentence reordering
    paragraphs = _split_paragraphs(result)
    reordered = [_reorder_sentences(p) for p in paragraphs]
    result = '\n\n'.join(reordered)

    # Paragraph randomization (only if aggressive)
    if aggressive:
        result = _randomize_paragraphs(result)

    # Additional collocation passes
    for _ in range(3):
        result = apply_random_collocation(result)

    # Safe typographic variation
    result = _add_typographic_variation(result)

    # Readability guard
    if not skip_readability_guard:
        result = _readability_guard(text, result)

    # Clean up
    result = re.sub(r'  +', ' ', result)
    result = re.sub(r'\n{3,}', '\n\n', result)
    result = re.sub(r'\.\s*\.', '.', result)
    result = re.sub(r',\s*,', ',', result)
    result = re.sub(r'\s+,', ',', result)
    result = re.sub(r'\s{2,}', ' ', result)

    return result.strip()
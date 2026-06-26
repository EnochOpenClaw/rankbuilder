"""
StealthHumanizer — Collocation Replacements (230+ entries)
Ported from TypeScript lib/collocations.ts → Python

Replaces predictable AI-favored word pairs with more human, casual alternatives.
"""

import random
import re
from typing import Union

# Each entry: (pattern_to_find, list_of_replacements)
# pattern can be str or re.Pattern

COLLOCATIONS: list[tuple[Union[str, re.Pattern], list[str]]] = [
    # Multi-word phrases AI loves
    ('in order to', ['so we can', 'to', 'so that we', 'for the purpose of']),
    ('due to the fact that', ['since', 'because', 'seeing as', 'given that']),
    ('it is worth noting that', ['worth mentioning', 'also', 'one more thing', 'it helps to know']),
    ('it is worth noting', ['worth mentioning', "it's good to know", 'keep in mind']),
    ('it is important to note', ['keep in mind', 'remember', 'it helps to know']),
    ('it is important to', ['it matters to', 'you need to', 'make sure to', "it's key to"]),
    ('it is important', ['it matters', 'this is key', 'this counts', 'this is a big deal']),
    ('it is essential', ['you really need', 'this is non-negotiable', 'you can\'t skip']),
    ('it is crucial', ['this matters a lot', 'this is make-or-break', 'you can\'t ignore']),
    ('it is evident that', ['clearly', 'obviously', 'you can see that', 'it\'s pretty clear']),
    ('it is clear that', ['clearly', 'obviously', 'you can tell', 'no surprise']),
    ('it is clear', ['obviously', 'clearly', 'no doubt', 'pretty obvious']),
    ('it is possible', ['it could happen', 'there\'s a chance', 'maybe']),
    ('it is likely', ['probably', 'chances are', 'I\'d bet']),
    ('it is unlikely', ['probably not', 'doubtful', 'a long shot']),
    ('it is necessary', ['you need to', 'it has to happen', 'required']),
    ('it is interesting', ['pretty cool actually', 'neat', 'fascinating when you think about it']),
    ('it is difficult', ['it\'s hard', 'not easy', 'tough', 'tricky']),
    ('it is true that', ['sure', 'granted', 'fair point', 'admittedly']),
    ('it should be noted', ['keep in mind', 'worth knowing', 'one thing to remember']),
    ('it should be mentioned', ['worth bringing up', 'I should add', 'also']),
    ('it goes without saying', ['obviously', 'naturally', 'of course', 'no brainer']),
    ('it is safe to say', ['you can pretty much say', 'I think it\'s fair to say', 'safe bet']),
    ('it cannot be denied', ['you can\'t really argue with', 'hard to dispute', 'no way around it']),
    ('it cannot be overstated', ['this really can\'t be said enough', 'huge deal', 'seriously important']),
    ('has the ability to', ['can', 'is able to', 'knows how to']),
    ('has the potential to', ['could', 'might just', 'stands a chance of']),
    ('has the capacity to', ['can', 'is equipped to', 'has what it takes to']),
    ('has the potential', ['could', 'might', 'has a shot at']),
    ('a large number of', ['tons of', 'a bunch of', 'quite a few', 'loads of', 'a whole lot of']),
    ('a significant number of', ['quite a few', 'a good chunk of', 'a bunch of']),
    ('a wide range of', ['all sorts of', 'a variety of', 'different kinds of']),
    ('a variety of', ['different', 'various', 'all kinds of', 'a mix of']),
    ('a great deal of', ['a lot of', 'tons of', 'loads of', 'a massive amount of']),
    ('a vast amount of', ['a ton of', 'so much', 'a mountain of']),
    ('a considerable amount', ['a lot', 'quite a bit', 'a good amount']),
    ('a considerable number', ['a bunch', 'quite a few', 'a good number']),
    ('a high level of', ['a lot of', 'deep', 'serious']),
    ('in the field of', ['when it comes to', 'in the world of', 'for anyone working in']),
    ('in the realm of', ['in the world of', 'when it comes to', 'within']),
    ('in the context of', ['when you look at', 'in the case of', 'given']),
    ('in the case of', ['when it comes to', 'for', 'with']),
    ('in addition to', ['besides', 'on top of', 'along with', 'plus']),
    ('in terms of', ['when it comes to', 'regarding', 'as for', 'looking at']),
    ('in light of', ['given', 'considering', 'because of', 'with']),
    ('in spite of', ['despite', 'even with', 'even though', 'regardless of']),
    ('in relation to', ['about', 'regarding', 'when it comes to', 'connected to']),
    ('in comparison to', ['compared to', 'versus', 'next to', 'against']),
    ('in contrast to', ['unlike', 'compared to', 'on the flip side', 'while']),
    ('in response to', ['as an answer to', 'reacting to', 'to address']),
    ('make a decision', ['decide', 'make up your mind', 'land on something', 'figure out what to do']),
    ('make a difference', ['change things', 'have an impact', 'actually matter']),
    ('make an effort', ['try', 'put in the work', 'push', 'make a point of']),
    ('make use of', ['use', 'leverage', 'take advantage of', 'put to work']),
    ('make a contribution', ['chip in', 'add something', 'do your part']),
    ('make progress', ['move forward', 'get somewhere', 'make headway']),
    ('take into account', ['consider', 'factor in', 'think about', 'keep in mind']),
    ('take into consideration', ['consider', 'factor in', 'think about', 'weigh']),
    ('take advantage of', ['use', 'leverage', 'capitalize on', 'jump on']),
    ('play a role', ['matter', 'be a factor', 'make a difference', 'have a say']),
    ('play a crucial role', ['be a big deal', 'really matter', 'make a huge difference']),
    ('play a key role', ['be central', 'be a big factor', 'really matter']),
    ('play a significant role', ['be a big part', 'carry real weight', 'matter a lot']),
    ('play an important role', ['really matter', 'be important', 'carry weight']),
    ('on the other hand', ['then again', 'but then', 'on the flip side', 'that said']),
    ('on the one hand', ['for one thing', 'sure', 'on one side']),
    ('at the same time', ['simultaneously', 'meanwhile', 'all the while', 'but also']),
    ('at the end of the day', ['ultimately', 'when all is said and done', 'in the end']),
    ('for the most part', ['mostly', 'generally', 'by and large', 'usually']),
    ('for the purpose of', ['to', 'for', 'so we can', 'in order to']),
    ('as a matter of fact', ['actually', 'in fact', 'truthfully', 'honestly']),
    ('as a result of', ['because of', 'thanks to', 'due to', 'from']),
    ('as a result', ['so', 'because of this', 'that\'s why', 'consequently']),
    ('as well as', ['and', 'plus', 'along with', 'alongside']),
    ('with regard to', ['about', 'regarding', 'when it comes to', 'on the topic of']),
    ('with respect to', ['about', 'regarding', 'in terms of', 'on']),
    ('with the exception of', ['except', 'other than', 'besides']),
    ('first and foremost', ['first off', 'to start', 'the main thing']),
    ('last but not least', ['finally', 'one more thing', 'also']),
    ('to begin with', ['first off', 'to start', 'for starters']),
    ('to sum up', ['basically', 'in short', 'long story short', 'the bottom line']),
    ('to put it differently', ['or to say it another way', 'in other words', 'basically']),
    ('to put it simply', ['basically', 'simply put', 'long story short']),
    ('the vast majority of', ['most', 'pretty much all', 'nearly all', 'almost all']),
    ('the majority of', ['most', 'a lot of', 'pretty much all']),
    ('a growing number of', ['more and more', 'an increasing number of', 'increasingly']),
    ('an increasing number of', ['more and more', 'growing numbers of']),
    ('the purpose of', ['why we', 'the point of', 'what we\'re trying to do']),
    ('the fact that', ['that', 'how', 'the reality that']),
    ('the ability to', ['being able to', 'can', 'getting to']),
    ('the importance of', ['why ... matters', 'how key ... is', 'how important ... is']),
    ('the development of', ['how ... developed', 'building', 'the rise of']),
    ('the implementation of', ['putting ... in place', 'rolling out', 'deploying']),
    ('the utilization of', ['using', 'the use of', 'how we use']),
    ('the use of', ['using', 'how we use', 'relying on']),
    ('the impact of', ['how ... affects things', 'what ... does', 'the effect of']),
    ('the results of', ['what happened when', 'the outcome of', 'what we got from']),
    ('in conclusion', ['to wrap up', 'so yeah', 'basically', 'at the end of the day']),
    ('to conclude', ['to wrap up', 'so', 'anyway', 'long story short']),
    ('in summary', ['basically', 'long story short', 'so yeah', 'the bottom line']),
    ('it is widely recognized', ['everyone knows', 'it\'s pretty well known', 'people generally agree']),
    ('it is widely accepted', ['most people agree', 'it\'s generally agreed', 'pretty much everyone accepts']),
    ('it is generally accepted', ['most people agree', 'it\'s pretty widely accepted', 'common knowledge']),
    ('it is generally understood', ['most people get that', 'pretty clear to everyone', 'common understanding']),
    ('there is a growing', ['there\'s more and more', 'we\'re seeing increasing']),
    ('there is no doubt', ['no question', 'clearly', 'definitely', 'for sure']),
    ('there is no denying', ['you can\'t deny', 'hard to argue with', 'undeniably']),
    ('demonstrates that', ['shows that', 'proves', 'makes it clear that']),
    ('suggests that', ['hints at', 'points to', 'seems like', 'makes you think']),
    ('indicates that', ['shows', 'points to', 'suggests', 'gives the sense that']),
    ('has been shown to', ['has proven to', 'we know', 'turns out to']),
    ('has been proven to', ['we\'ve seen that', 'it\'s been shown', 'clearly']),
    ('capable of', ['able to', 'can', 'equipped to']),
    ('responsible for', ['in charge of', 'handling', 'taking care of', 'doing']),
    ('associated with', ['linked to', 'tied to', 'connected to', 'related to']),
    ('according to', ['per', 'based on what', 'if you look at', 'says']),
    ('prior to', ['before', 'leading up to', 'ahead of']),
    ('subsequent to', ['after', 'following', 'once']),
    ('in the first place', ['to begin with', 'first off', 'for starters']),
    ('in the second place', ['secondly', 'also', 'on top of that']),
    ('moreover', ['plus', 'also', 'on top of that', 'and']),
    ('furthermore', ['also', 'plus', 'on top of that', 'beyond that']),
    ('additionally', ['also', 'plus', 'on top of that', 'and another thing']),
    ('nevertheless', ['still', 'but', 'even so', 'that said']),
    ('consequently', ['so', 'as a result', 'that\'s why', 'because of that']),
    ('subsequently', ['then', 'after that', 'later', 'next']),
    ('facilitate', ['help with', 'make easier', 'enable', 'allow']),
    ('utilize', ['use', 'work with', 'put to use', 'apply']),
    ('implement', ['put in place', 'roll out', 'set up', 'start using']),
    ('leverage', ['use', 'take advantage of', 'build on', 'work with']),
    ('optimize', ['improve', 'fine-tune', 'make better', 'tweak']),
    ('comprehensive', ['thorough', 'complete', 'detailed', 'full']),
    ('facilitates the', ['helps with', 'makes it easier to', 'allows for']),
    ('paramount', ['key', 'top priority', 'most important', 'critical']),
    ('underscore', ['highlight', 'stress', 'point out', 'show']),
    ('delve into', ['dig into', 'look at', 'explore', 'get into']),
    ('sheds light on', ['helps explain', 'clarifies', 'makes sense of', 'reveals']),
    ('landscape', ['world', 'space', 'scene', 'area', 'environment']),
    ('a myriad of', ['lots of', 'tons of', 'all kinds of', 'a bunch of']),
    ('multifaceted', ['complex', 'many-sided', 'layered', 'complicated']),
    ('seamless', ['smooth', 'easy', 'frictionless', 'painless']),
    ('synergy', ['teamwork', 'working together', 'combined effort', 'collaboration']),
    ('paradigm shift', ['big change', 'fundamental shift', 'game changer', 'new way of thinking']),
    ('holistic', ['complete', 'all-around', 'full-picture', 'big-picture']),
    ('groundbreaking', ['revolutionary', 'huge', 'game-changing', 'innovative']),
    ('transformative', ['life-changing', 'revolutionary', 'major', 'powerful']),
    ('unprecedented', ['never seen before', 'unheard of', 'unlike anything before', 'brand new']),
    ('embark on', ['start', 'begin', 'kick off', 'dive into']),
    ('navigating', ['working through', 'dealing with', 'handling', 'figuring out']),
    ('pivotal', ['key', 'crucial', 'critical', 'game-changing']),
    ('integral', ['important', 'essential', 'key', 'central']),
    ('robust', ['strong', 'solid', 'tough', 'reliable']),
    ('innovative', ['new', 'fresh', 'creative', 'cutting-edge']),
    ('streamline', ['simplify', 'speed up', 'make easier', 'smooth out']),
    ('state-of-the-art', ['latest', 'cutting-edge', 'modern', 'top-of-the-line']),
    ('cutting-edge', ['latest', 'bleeding-edge', 'newest', 'advanced']),
    ('best practices', ['smart approaches', 'proven methods', 'what works', 'standard approaches']),
    ("in today's world", ['now', 'these days', 'right now', 'at this point']),
    ("in today's society", ['nowadays', 'these days', 'right now', 'in 2024']),
    ('in the modern era', ['now', 'these days', 'today', 'in this day and age']),
    ('in this day and age', ['now', 'these days', 'today', 'right now']),
    # Phase 3: 50+ NEW AI PHRASE ENTRIES
    ('a deep dive into', ['a closer look at', 'digging into', 'exploring', 'looking at']),
    ('deep dive', ['closer look', 'detailed look', 'proper examination', 'real analysis']),
    ('unlocking the potential', ['tapping into', 'making the most of', 'getting more out of', 'using']),
    ('unlocking', ['opening up', 'revealing', 'exposing', 'making available']),
    ('the intersection of', ['where ... meets', 'the overlap between', 'how ... connects to']),
    ('at the intersection of', ['where ... meets', 'between', 'at the crossroads of']),
    ('paving the way', ['leading to', 'making room for', 'opening the door for', 'setting up']),
    ('paves the way', ['leads to', 'sets up', 'clears the path for', 'makes possible']),
    ('the backbone of', ['the core of', 'what supports', 'the foundation of', 'what holds up']),
    ('a testament to', ['proof of', 'shows that', 'evidence of', 'a sign of']),
    ('in an ever-changing', ['in a changing', 'as things change in', 'in today\'s', 'in a shifting']),
    ('ever-evolving', ['constantly changing', 'always shifting', 'developing', 'moving']),
    ('not only... but also', ['both... and', 'not just... it also', '...and on top of that']),
    ('it is imperative that', ['we really need to', 'it\'s critical to', 'you have to', 'we must']),
    ('the landscape of', ['the world of', 'the field of', 'the area of', 'the space of']),
    ('navigating the complexities', ['dealing with the complexity', 'working through the complications', 'handling the tricky parts']),
    ('a rich tapestry', ['a mix of', 'a blend of', 'a variety of', 'a combination of']),
    ('tapestry', ['mix', 'blend', 'combination', 'mosaic', 'collection']),
    ('the nuances of', ['the subtle parts of', 'the details of', 'the finer points of']),
    ('bringing to light', ['revealing', 'showing', 'exposing', 'uncovering']),
    ('in the grand scheme of things', ['overall', 'when you step back', 'in the bigger picture', 'all things considered']),
    ('it bears mentioning', ['worth saying', 'I should add', 'also', 'one more thing']),
    ('serves as a', ['acts as a', 'works as a', 'functions as a', 'is a']),
    ('acts as a catalyst', ['sparks', 'drives', 'pushes forward', 'accelerates']),
    ('catalyst for change', ['what drives change', 'what pushes things forward', 'a driver of change']),
    ('the crux of', ['the heart of', 'the key part of', 'the main point of', 'what matters most about']),
    ('at its core', ['basically', 'fundamentally', 'at the heart of it', 'when you get down to it']),
    ('at its essence', ['basically', 'in essence', 'at heart', 'fundamentally']),
    ('it is undeniable that', ['clearly', 'obviously', 'you can\'t argue with', 'no question']),
    ('undeniably', ['clearly', 'without doubt', 'for sure', 'no question']),
    ('a beacon of', ['a sign of', 'an example of', 'a model for', 'a symbol of']),
    ('the paradigm of', ['the model of', 'the approach to', 'the pattern of', 'the framework for']),
    ('in a rapidly evolving', ['in a fast-changing', 'in a quickly changing', 'in today\'s', 'in a developing']),
    ('rapidly evolving', ['fast-changing', 'quickly developing', 'shifting', 'growing']),
    ('weaving together', ['combining', 'bringing together', 'mixing', 'merging']),
    ('a delicate balance', ['a tricky balance', 'a fine line', 'a careful balance', 'a tight balance']),
    ('it is paramount', ['it\'s crucial', 'this is the top priority', 'this matters most', 'nothing is more important']),
    ('paramount importance', ['really important', 'top priority', 'critical', 'the most important thing']),
    ('fostering a culture of', ['building a culture of', 'creating an environment for', 'encouraging']),
    ('the proliferation of', ['the spread of', 'the growth of', 'more and more', 'the rise in']),
    ('proliferation', ['spread', 'growth', 'increase', 'expansion']),
    ('a myriad of ways', ['lots of ways', 'many ways', 'all sorts of ways', 'tons of ways']),
    ('championing', ['supporting', 'pushing for', 'leading', 'advocating for']),
    ('demystifying', ['explaining', 'breaking down', 'making sense of', 'clarifying']),
    ('thought-provoking', ['interesting', 'makes you think', 'worth reflecting on', 'stimulating']),
    ('game-changing', ['huge', 'revolutionary', 'major', 'a big deal']),
    ('reshaping the way', ['changing how', 'transforming how', 'shifting how']),
    ('bridging the gap', ['closing the gap', 'connecting', 'filling the gap', 'linking']),
    ('a cornerstone of', ['a key part of', 'central to', 'essential to', 'a foundation of']),
    ('stands as', ['is', 'serves as', 'works as', 'functions as']),
    ('encompasses', ['includes', 'covers', 'involves', 'contains']),
    ('the advent of', ['the arrival of', 'the start of', 'the beginning of', 'when ... first appeared']),
    ('a stark contrast', ['a big difference', 'a clear difference', 'totally different from', 'nothing like']),
    ('delves deeper', ['goes deeper', 'looks closer', 'digs into', 'explores further']),
    ('unparalleled', ['unmatched', 'unequaled', 'unrivaled', 'like nothing else']),
    ('a lens through which', ['a way to look at', 'a perspective on', 'an angle for']),
]


def apply_collocation(text: str) -> str:
    """Apply all collocation replacements to text."""
    result = text
    for col_from, col_to in COLLOCATIONS:
        if isinstance(col_from, re.Pattern):
            match = col_from.search(result)
            if match:
                replacement = random.choice(col_to)
                result = col_from.sub(replacement, result, count=1)
        else:
            pattern = re.compile(re.escape(col_from), re.I)
            if pattern.search(result):
                replacement = random.choice(col_to)
                result = pattern.sub(replacement, result)
    return result


def apply_random_collocation(text: str) -> str:
    """Apply a single random applicable collocation replacement."""
    applicable = []
    for col_from, col_to in COLLOCATIONS:
        if isinstance(col_from, re.Pattern):
            if col_from.search(text):
                applicable.append((col_from, col_to))
        else:
            if re.search(re.escape(col_from), text, re.I):
                applicable.append((col_from, col_to))

    if not applicable:
        return text

    col_from, col_to = random.choice(applicable)
    replacement = random.choice(col_to)

    if isinstance(col_from, re.Pattern):
        return col_from.sub(replacement, text, count=1)

    pattern = re.compile(re.escape(col_from), re.I)
    return pattern.sub(replacement, text, count=1)
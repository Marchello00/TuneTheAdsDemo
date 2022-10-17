import random
import string


_all_en_words = None
_bad_en_words = None
_stop_words = None


def init():
    global _all_en_words, _bad_en_words, _stop_words
    import nltk
    nltk.download("stopwords")
    nltk.download("words")

    from nltk.corpus import words
    _all_en_words = set(words.words())

    from nltk.corpus import stopwords
    _stop_words = set(stopwords.words('english'))

    with open('core/english_ban.txt') as f:
        _bad_en_words = set(f.read().split('\n'))


def choose(arr, prev=""):
    return random.choice(list(set(arr) - {prev}))


def get_all_en_words():
    if _all_en_words is None:
        init()
    return _all_en_words


def get_bad_en_words():
    if _bad_en_words is None:
        init()
    return _bad_en_words


def get_stop_words():
    if _stop_words is None:
        init()
    return _stop_words


def is_fraud(text):
    all_en_words = get_all_en_words()

    text = text.translate(str.maketrans('', '', string.punctuation))
    good_words = 0
    total = 0
    for word in text.split():
        good_words += word in all_en_words
        total += 1
    share = good_words / total
    return share < 0.2

import tune_the_model as ttm
import pandas as pd
import numpy as np
import core.parse_html
import time


def get_title_and_content(url, num_retries=5):
    for retry in range(num_retries):
        try:
            title, content = core.parse_html.page_parser(url)
        except Exception:
            time.sleep(1 + retry)
            continue
        if len(title) + len(content) < 500 and retry < num_retries - 1:
            time.sleep(1 + retry)
            continue
        content = content[:5000]
        return title, content


def get_request_classifier():
    return ttm.TuneTheModel.from_id(
        '4cc5a4244e0611ed96478b0f9eb21374'  # autotarget, translated
    )


def get_request_generator():
    return ttm.TuneTheModel.from_id(
        '2e515fe24e0611eda45161dc08b2d04c' # autotarget, translated
    )


def get_keyword_generator():
    return ttm.TuneTheModel.from_id(
        '7bc2658a511e11ed966e1b318d0839ce'  # similarweb
    )


def get_banner_generator():
    return ttm.TuneTheModel.from_id(
        'f5782c4c511a11ed9cbc2b904aa4d5aa'  # similarweb
        # '09d6dd904e0611edbf82ff3a2de0976d' # autotarget, translated
    )


def get_banner_classifier():
    return ttm.TuneTheModel.from_id(
        '2e96b14e220711ed9e95b1ae88b1dbe2'
    )


def get_banner_gen_prefix(title, content):
    # return title + '\n' + content + '\n\n\n' # autotarget
    return title + '\n' + content + '\n\nBanner\n'  # similarweb


def get_keyword_gen_prefix(title, content, banner, label='exact'):
    # similarweb
    return get_banner_gen_prefix(title, content) + banner + '\n\nKeyword\n'


def get_request_gen_prefix(title, content, banner, label='exact'):
    # autotarget
    return get_banner_gen_prefix(title, content) + '\n\nBanner:\n' +\
            banner + '\n\nLabel: ' + label + '\n\nSearch request: '


# label \in [broad, exact, unlikely]
def get_request_classify_prompt(title, content, banner, request):
    # autotarget
    return get_banner_gen_prefix(title, content) + '\n\nBanner:\n' +\
            banner + '\n\nSearch request: ' + request


request_classifier_mapping = [
    'Accessory',
    'Alternative',
    'Broader',
    'Competitor',
    'Exact match',
    'No match'
]


def is_bad_content(title, content):
    if not content:
        return True
    if len(title) + len(content) < 100:
        return True

    ban_patterns = [
        ('access', 'denied'),
        'page not found'
    ]
    for pats in ban_patterns:
        if isinstance(pats, str):
            pats = [pats]
        all_in = True
        for pat in pats:
            if pat not in content.lower() and pat not in title.lower():
                all_in = False
                break
        if all_in:
            return True
    return False


def classify_request(request_classifier, title, content, banner, request):
    scores = request_classifier.classify(
        get_request_classify_prompt(title, content, banner, request)
    )
    result = pd.DataFrame.from_dict(
        {'Property': request_classifier_mapping, 'Score': scores}
    )
    return result


def gen_keywords(
    keyword_generator, request_classifier,
    title, content, banner, temp=1.1, num_hypos=18
):
    model_input = get_keyword_gen_prefix(title, content, banner)

    result = keyword_generator.generate(
        model_input, num_hypos=num_hypos, min_tokens=4,
        max_tokens=128, temperature=temp, top_k=30
    )

    result = np.unique(result)

    result = [
        (
            keyword,
            classify_request(
                request_classifier, title, content, banner, keyword
            )
        )
        for keyword in result
    ]

    result = sorted(
        [
            (keyword, scores)
            for keyword, scores in result
            if scores[scores['Property'] == 'No match']['Score'].iloc[0] < 0.5
        ],
        key=lambda x: -x[1][x[1]['Property'] == 'Exact match']['Score'].iloc[0]
    )

    return result


def generate_banner(
    banner_generator, banner_classifier,
    title, content, temp=0.6, num_hypos=7
):
    model_input = get_banner_gen_prefix(title, content)
    try:
        banners = banner_generator.generate(
            model_input, num_hypos=num_hypos, min_tokens=4,
            max_tokens=128, temperature=temp, top_k=30
        )
    except ttm.TuneTheModelException:
        raise SystemError("Server error.")

    banners = [b.replace('\\r\\n', '\n') for b in banners]
    split_banners = [b.split('\n', maxsplit=1) for b in banners]
    inputs = ['\n '.join(parts + [title, content[:200]])
              for parts in split_banners]
    scores = [banner_classifier.classify(i)[0] for i in inputs]

    result = []
    for s, b in sorted(zip(scores, split_banners), reverse=True):
        if len(b) <= 1:
            continue
        result.append(b)

    if not result:
        raise ValueError("No banners generated.")
    return result

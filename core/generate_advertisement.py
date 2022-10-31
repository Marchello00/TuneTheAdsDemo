import tune_the_model as ttm
import pandas as pd
import numpy as np
import core.parse_html
import time
import langid
from concurrent.futures import ProcessPoolExecutor as Pool
from functools import partial


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
        '2e515fe24e0611eda45161dc08b2d04c'  # autotarget, translated
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


def classify_request(request, request_classifier, title, content, banner):
    scores = request_classifier.classify(
        get_request_classify_prompt(title, content, banner, request)
    )
    result = pd.DataFrame.from_dict(
        {'Property': request_classifier_mapping, 'Score': scores}
    )
    return result


def gen_keywords(
    keyword_generator, request_classifier,
    title, content, banner, temp=1.1, num_hypos=18,
    num_workers=1
):
    if not isinstance(banner, str):
        h, t = banner
        banner = h + '\n' + t
    model_input = get_keyword_gen_prefix(title, content, banner)

    result = keyword_generator.generate(
        model_input, num_hypos=num_hypos, min_tokens=4,
        max_tokens=128, temperature=temp, top_k=30
    )

    result = np.unique(result)

    if num_workers == 1:
        result = [
            (
                keyword,
                classify_request(
                    keyword, request_classifier, title, content, banner
                )
            )
            for keyword in result
        ]
    else:
        with Pool(num_workers) as p:
            class_probas = p.map(
                partial(
                    classify_request,
                    request_classifier=request_classifier,
                    title=title, content=content, banner=banner
                ),
                result
            )
            result = list(zip(result, class_probas))

    result = sorted(
        [
            (keyword, scores)
            for keyword, scores in result
            if scores[scores['Property'] == 'No match']['Score'].iloc[0] < 0.5
        ],
        key=lambda x: -x[1][x[1]['Property'] == 'Exact match']['Score'].iloc[0]
    )

    return result


def prepare_banner(banner):
    banner = banner.replace('\\r\\n', '\n')
    parts = banner.split('\n', maxsplit=1)  # [title, description]
    parts = [p.strip() for p in parts]
    return parts


# banner = [title, description]
def is_good_banner(
    banner, title, content, banner_classifier, score=True, threshold=0.3
):
    if len(banner) <= 1:
        return False, 0
    if any(len(b) == 0 for b in banner):
        return False, 0

    if langid.classify('\n'.join(banner))[0] != 'en':
        return False, 0

    banner_classifier_input = '\n '.join(banner + [title, content[:200]])
    if score:
        score = banner_classifier.classify(banner_classifier_input)[0]
    else:
        score = 1.

    return score >= threshold, score


def generate_banner(
    banner_generator, banner_classifier,
    title, content, temp=0.6, num_hypos=7,
    retries=4, score=True, exceptions=True
):
    model_input = get_banner_gen_prefix(title, content)
    try:
        banners = [('', -1, False)] * num_hypos
        for _ in range(retries):
            ids = [
                i for i, (b, score, b_ready) in enumerate(banners)
                if not b_ready
            ]

            banners_cands = banner_generator.generate(
                model_input, num_hypos=len(ids), min_tokens=4,
                max_tokens=128, temperature=temp, top_k=30
            )

            for banner, idd in zip(banners_cands, ids):
                banner = prepare_banner(banner)

                is_good, score = is_good_banner(
                    banner, title, content, banner_classifier, score=score
                )
                if is_good:
                    banners[idd] = banner, score, True
                else:
                    if banners[idd][1] < score:
                        banners[idd] = banner, score, False
    except ttm.TuneTheModelException:
        if not exceptions:
            return []
        else:
            raise SystemError("Server error.")

    banners.sort(key=lambda x: -x[1])

    # discard bad banners (including non-english)
    result = [b for b, score, b_ready in banners if b_ready]

    if not result:
        if not exceptions:
            return []
        else:
            raise ValueError("No banners generated.")
    return result


def generate_banner_keyword(
    fake,
    banner_generator, banner_classifier,
    keyword_generator, request_classifier,
    title, content,
    banner_temp=0.6,
    keyword_temp=1.1, num_keywords=18,
    score=True, retries=2, num_kw_workers=4,
):
    try:
        banner = generate_banner(
            banner_generator, banner_classifier,
            title, content,
            temp=banner_temp, num_hypos=1, retries=retries,
            exceptions=True
        )[0]
        keywords = gen_keywords(
            keyword_generator, request_classifier,
            title, content, banner,
            temp=keyword_temp, num_hypos=num_keywords,
            num_workers=num_kw_workers
        )
    except Exception:
        return None, None

    return banner, keywords


def generate_banner_keyword_parallel(
    banner_generator, banner_classifier,
    keyword_generator, request_classifier,
    title, content,
    banner_temp=0.6, num_banners=5,
    keyword_temp=1.1, num_keywords=18,
    score=True, retries=2,
    num_workers=5, num_kw_workers=4
):
    with Pool(num_workers) as p:
        for banner, keywords in p.map(
            partial(generate_banner_keyword,
                banner_generator=banner_generator,
                banner_classifier=banner_classifier,
                keyword_generator=keyword_generator,
                request_classifier=request_classifier,
                title=title, content=content,
                banner_temp=banner_temp,
                keyword_temp=keyword_temp, num_keywords=num_keywords,
                score=score, retries=retries, num_kw_workers=num_kw_workers),
            range(num_banners)
        ):
            if banner is None:
                continue
            yield banner, keywords

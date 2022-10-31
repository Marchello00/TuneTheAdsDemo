import streamlit as st
import core.utils
import core.constants
import core.generate_advertisement
from samples.generate_advertisement import samples

if __name__ == '__main__':
    NUM_BANNERS = 5
    NUM_KEYWORDS = 10

    st.set_page_config(
        page_title="📈 Generate Advertisement",
    )

    if 'request_classifier' not in st.session_state:
        st.session_state['request_classifier'] =\
            core.generate_advertisement.get_request_classifier()

    if 'keyword_generator' not in st.session_state:
        st.session_state['keyword_generator'] =\
            core.generate_advertisement.get_keyword_generator()

    if 'banner_classifier' not in st.session_state:
        st.session_state['banner_classifier'] =\
            core.generate_advertisement.get_banner_classifier()

    if 'banner_generator' not in st.session_state:
        st.session_state['banner_generator'] =\
            core.generate_advertisement.get_banner_generator()

    if 'adgen_input' not in st.session_state:
        st.session_state['adgen_input'] = core.utils.choose(samples)


# def gen_keywords(title, content, banners, temp):
#     return core.generate_advertisement.gen_keywords_parallel(
#         st.session_state['keyword_generator'],
#         st.session_state['request_classifier'],
#         title,
#         content,
#         banners,
#         temp,
#         num_hypos=10
#     )


# def gen_banners(title, content, temp, max_num_hypos=5):
#     return core.generate_advertisement.generate_banners_parallel(
#         st.session_state['banner_generator'],
#         st.session_state['banner_classifier'],
#         title,
#         content,
#         num_banners=5,
#         temp=temp,
#         num_workers=5,
#     )

def process(url, additional_info, keyword_temp, banner_temp):
    try:
        title, content = core.generate_advertisement.get_title_and_content(url)
    except Exception:
        st.error('An error occurred while downloading data from the site. '
                 'Make sure the address is correct '
                 '(for example, \"https://www.northstardubai.com /\"), '
                 ' or try generation for another site.')
        return
    if not title and not content:
        st.error('Unfortunately, it was not possible to extract '
                 'the text from the page. '
                 'Please try generating for another site.')
        return
    ex = st.expander('Site content')
    ex.write('Title:')
    ex.write(title)
    if additional_info:
        ex.write("Additional information:")
        ex.write(additional_info)
    ex.write('Content:')
    ex.write(content)

    content = additional_info + content

    if core.generate_advertisement.is_bad_content(title, content):
        st.error(
            "Sorry, we couldn't download the information from the site.\n"
            "Access may have been blocked, you can check the "
            "\"Site content\" section above.\n\n"
            "Please, try again or choose another site."
        )
        return

    if len(title) + len(content) < 300:
        st.warning('Attention! Very little text was '
                   'extracted from the page - the '
                   'results may be of poor quality.')

    '--------'

    tmp = st.columns(2)
    tmp[0].header('Banners:')
    tmp[1].header('Keywords:')
    '--------'

    generated = False

    with st.spinner('Generating advertisement...'):
        for banner, banner_keywords in\
                core.generate_advertisement.generate_banner_keyword_parallel(
                    st.session_state['banner_generator'],
                    st.session_state['banner_classifier'],
                    st.session_state['keyword_generator'],
                    st.session_state['request_classifier'],
                    title, content,
                    banner_temp=banner_temp, num_banners=NUM_BANNERS,
                    keyword_temp=1.1, num_keywords=NUM_KEYWORDS,
                    score=True, retries=2,
                    num_workers=NUM_BANNERS,
                    num_kw_workers=4
                ):
            c1, c2 = st.columns(2)
            with c1:
                h, t = banner
                st.subheader(h)
                st.write(t)

            with c2:
                for t in banner_keywords:
                    ex = st.expander(t[0])
                    ex.bar_chart(t[1], x='Property', y='Score')

            generated = True
            '--------'

    if not generated:
        st.error(
            "Sorry, we were unable to create banners "
            "for this site. The content may be too "
            "specific or non-English, you can check "
            "the \"Site Content\" section above.\n\n"
            "Please, try again or choose another site."
        )
        return

    st.caption(core.constants.generation_warning)


def main():
    st.image('img/logo.png')

    st.markdown('[Tune the Model](tunethemodel.com) allows you '
                'to create a custom text AI tailored for your application.')

    'Powered by huge pre-trained transformer language models, '\
        'Tune the Model enables you to create text AI and bring it '\
        'to production without investing in labelling large datasets, '\
        'running tons of experiments, or setting up GPU cloud.'

    st.title('Generate Advertisement')

    'You can tune the model to generate great advertisement '\
        'by the content of the website! Also you can tune generator '\
        'to make up search queries for each banner!'

    if st.button('Give me an example!'):
        st.session_state['adgen_input'] = core.utils.choose(
            samples, st.session_state['adgen_input']
        )
    url = st.text_input('URL', value=st.session_state['adgen_input'])

    additional_info = st.text_area(
        'Description',
        placeholder="Write some information about your product, "
        "company or any other stuff, that you want to advertise.\n"
        "You can leave this field empty, if your website contains "
        "enough information.",
        max_chars=2000,
        height=200
    )
    st.button("Generate!")
    c1, c2 = st.columns(2)
    with c1:
        st.subheader('Banner generation parameters')
        banner_temp = st.slider(
            'Creativity', 0.01, 2.1, value=0.4,
            key='banner_temp',
            help="With a decrease in creativity, correctness grows, "
            "with an increase in creativity, diversity grows"
        )
    with c2:
        st.subheader('Keyword generation parameters')
        keywords_temp = st.slider(
            'Creativity', 0.01, 2.1, value=0.8,
            key='kw_temp',
            help="With a decrease in creativity, correctness grows, "
            "with an increase in creativity, diversity grows"
        )

    process(url, additional_info, keywords_temp, banner_temp)


if __name__ == '__main__':
    main()

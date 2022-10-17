from dataclasses import dataclass, field
from typing import List, Dict
import requests

import lxml.html
import re

from bs4 import BeautifulSoup
import cloudscraper


@dataclass
class Doc:
    pos: int
    url: str
    html: str
    title: str
    text: str
    toc: 'Toc'


@dataclass
class Toc:
    title: str
    own_segments: List['Segment']
    children: List['Toc']
    features: Dict = field(default_factory=dict)

    @property
    def all_segments(self):
        result = self.own_segments[:]
        for child in self.children:
            result.extend(child.all_segments)
        return result

    @property
    def all(self):
        result = [self]
        for child in self.children:
            result.extend(child.all)
        return result

    @property
    def leaves(self):
        return [toc for toc in self.all if not toc.children]

    def walk(self):
        """
        Example: print a toc tree.

            for tocs in toc.walk():
                print('  ' * len(tocs), tocs[-1].title)
        """
        yield [self]
        for child in self.children:
            for tocs in child.walk():
                yield [self] + tocs

    def __getitem__(self, key):
        return self.features[key]

    def __setitem__(self, key, value):
        self.features[key] = value


@dataclass
class Segment:
    text: str
    features: Dict = field(default_factory=dict)

    def __getitem__(self, key):
        return self.features[key]

    def __setitem__(self, key, value):
        self.features[key] = value


def parse_title(doc) -> str:
    """
    Depends on:

    - doc.html
    """
    if not doc.html:
        return ''
    try:
        return lxml.html.fromstring(doc.html).findtext('.//title') or ''
    except UnicodeDecodeError:
        return ''


def parse_content(doc) -> Toc:
    """
    Depends on:

    - doc.title
    - doc.html
    """
    # Toc tree.
    toc = Toc(title=doc.title, own_segments=[], children=[])

    # Find all paragraphs and headers.
    document = BeautifulSoup(doc.html, "lxml")
    simple_text = document.get_text(' ')

    titles = []
    descriptions = []

    for meta in document.find_all('meta'):
        prop = meta.attrs.get('property', '')
        name = meta.attrs.get('name', '')
        text = meta.attrs.get('content', '')
        for tp in [prop, name]:
            if 'title' in tp:
                titles.append(text)
            if 'site_name' in tp:
                titles.append(text)
            if 'description' in tp:
                descriptions.append(text)
    meta_title = '. '.join(titles)
    meta_descr = ' '.join(descriptions)

    all_nodes = document.find_all(re.compile("^h[1-6]$|^p$"))

    # Collect.
    current_toc = [toc]
    current_toc_level = [0]

    for node in all_nodes:
        # - Append paragraph.
        if node.name == 'p':
            seg = Segment(text=node.getText())
            current_toc[-1].own_segments.append(seg)

        # - Process title.
        else:
            level = int(node.name[1:])

            while current_toc_level[-1] >= level:
                del current_toc[-1]
                del current_toc_level[-1]

            child = Toc(
                title=node.getText().strip(),
                own_segments=[],
                children=[]
            )
            current_toc[-1].children.append(child)
            current_toc.append(child)
            current_toc_level.append(level)

    return toc, simple_text, meta_title, meta_descr


def download(url: str, timeout: int = 5) -> bytes:
    try:
        headers = {
            'User-Agent':
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_10_1) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/39.0.2171.95 '
                'Safari/537.36'
        }
        response = requests.get(url, timeout=timeout, headers=headers)
        if response.ok:
            return response.content
    except Exception:
        pass
    return None


def download_cloudscraper(url: str):
    scraper = cloudscraper.create_scraper()
    try:
        return scraper.get(url).text
    except Exception:
        return None


def cleanup(text):
    text = re.sub(r'\s+', ' ', text).strip()
    return text


def page_parser(url):
    variants = [url]
    if 'www.' not in url:
        if '://' in url:
            prot, dom = url.split('://')
            variants.append(prot + '://www.' + dom)
        else:
            variants.append('www.' + url)
    new_var = []
    for url in variants:
        if '://' not in url:
            new_var.append('https://' + url)
            new_var.append('http://' + url)
    new_var.extend(variants)
    variants = new_var

    for url in variants:
        try:
            html = download_cloudscraper(url)
            if html:
                break
        except Exception:
            pass
    doc = Doc(0, url, html, title='', text='', toc=None)
    doc.title = parse_title(doc)
    doc.toc, doc.text, meta_title, meta_descr = parse_content(doc)
    if not doc.title:
        doc.title = meta_title
    content = '\n'.join([s.text for s in doc.toc.all_segments])
    if not content:
        content = doc.text
    if meta_title or meta_descr:
        content = ' '.join([meta_title, meta_descr]) + ' ' + content
    return cleanup(doc.title), cleanup(content)

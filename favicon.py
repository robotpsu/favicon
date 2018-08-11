#!/usr/bin/env python3
from argparse import ArgumentParser
from io import BytesIO
import logging, os, os.path, re
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from PIL import Image
import requests


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 \
                   (KHTML, like Gecko) Chrome/47.0.2526.111 Safari/537.36'}


def get_favicon_uri_from_link(content: bytes, uri: str) -> (str, None):
    soup = BeautifulSoup(content, 'lxml')

    link = soup.find('link', rel='icon')
    if link and link.has_attr('href'):
        parsed_uri = urlparse(uri)
        favicon_uri = link['href']

        if favicon_uri.startswith('//'):  # Protocol-relative URI
            favicon_uri = parsed_uri.scheme + ':' + favicon_uri
        elif favicon_uri.startswith('/'):  # Absolute path (relative to the domain)
            favicon_uri = parsed_uri.scheme + '://' + parsed_uri.netloc + favicon_uri
        elif not favicon_uri.startswith('http'):  # Relative path
            path, filename = os.path.split(parsed_uri.path)
            favicon_uri = parsed_uri.scheme + '://' + parsed_uri.netloc + '/' + path + '/' + favicon_uri

        return favicon_uri

    return None


def get_favicon_uri(uri: str) -> (str, None):
    parsed_uri = urlparse(uri)

    response = requests.get(uri, headers=HEADERS)
    if response.status_code == requests.codes.ok:
        # Try to get favicon URI from <link rel="shortcut icon" … />
        favicon_uri = get_favicon_uri_from_link(response.content, response.url)
        if favicon_uri:
            return favicon_uri

    # Try to get favicon from standard location
    favicon_uri = parsed_uri.scheme + '://' + parsed_uri.netloc + '/favicon.ico'
    response = requests.head(favicon_uri, headers=HEADERS)
    if response.status_code == requests.codes.ok:
        return favicon_uri

    # No favicon found
    return None


def get_filename(uri: str, favicon_uri: str, png: bool = False) -> str:
    ext = '.png' if png else os.path.splitext(urlparse(favicon_uri).path)[1]
    filename = re.sub(r'\W', '_', urlparse(uri).netloc, flags=re.ASCII) + ext
    return filename


def get_favicon(uri: str, filename: str = '', resize: int = 0) -> None:
    logging.debug("trying to get favicon from '%s'…", uri)
    response = requests.get(uri, headers=HEADERS)
    if response.status_code != requests.codes.ok:
        response.raise_for_status()

    favicon = Image.open(BytesIO(response.content))
    logging.debug("%s %d×%d at '%s'", favicon.format, favicon.width, favicon.height, response.url)
    if resize:
        size = (resize, resize)
        if favicon.format == 'ICO' and size in favicon.ico.sizes():
            favicon = favicon.ico.getimage(size)
        else:
            favicon = favicon.resize(size, resample=Image.BICUBIC)
        logging.debug("resized to %d×%d", favicon.width, favicon.height)

    favicon.save(filename)
    logging.debug("saved to '%s'", filename)


def get_dokuwiki_interwiki_icons(dokuwiki_root: str, force: bool = False) -> None:
    dokuwiki_root = os.path.abspath(dokuwiki_root)
    with open(os.path.join(dokuwiki_root, 'conf', 'interwiki.local.conf')) as f:
        images_dir = os.path.join(dokuwiki_root, 'lib', 'images', 'interwiki')
        os.makedirs(images_dir, mode=0o770, exist_ok=True)

        for line in f:
            try:
                m = re.fullmatch(r'([-0-9.a-z_]+)\s+(.*)', line.strip(), flags=re.ASCII)
                if not m:
                    continue
                name = m.group(1)
                filename = os.path.join(images_dir, name + '.png')
                if os.path.isfile(filename) and not force:
                    logging.info("%s: icon exists already - skip")
                    continue
                uri = '{uri.scheme}://{uri.netloc}/'.format(uri=urlparse(m.group(2)))
                favicon_uri = get_favicon_uri(uri)
                if not favicon_uri:
                    logging.error("%s: cannot find favicon for URI '%s'", name, uri)
                    continue
                get_favicon(favicon_uri, filename, 16)
            except Exception as ex:
                logging.error('%s', ex)
                continue
            logging.info("%s: icon saved to '%s'", name, filename)


if __name__ == '__main__':
    parser = ArgumentParser(description='Get favicon for a URI')
    parser.add_argument('uri', help='URI to get favicon for')
    parser.add_argument('-v', '--verbose', action='store_true', help='show info messages')
    parser.add_argument('-P', '--print', action='store_true', help='show favicon URI and exit')
    parser.add_argument('-d', '--dir', default='', help='save favicon in directory DIR')
    parser.add_argument('-f', '--filename', default='', help='save favicon as FILENAME')
    parser.add_argument('-r', '--resize', metavar='SIZE', type=int, default=0, help='resize favicon to SIZE×SIZE')
    parser.add_argument('-p', '--png', action='store_true', help='convert favicon to PNG format')
    parser.add_argument('-D', '--dokuwiki', metavar='PATH', help='get favicons for DokuWiki interwiki links')
    parser.add_argument('-F', '--force', action='store_true', help='force DokuWiki interwiki icons update')
    args = parser.parse_args()

    logging.basicConfig(
        format="favicon: %(levelname)s: %(message)s",
        level=(logging.INFO if args.verbose else logging.WARNING)
    )

    try:
        if args.dokuwiki:
            get_dokuwiki_interwiki_icons(args.dokuwiki, force=args.force)
        else:
            if not args.uri:
                raise Exception("empty URI")
            if not args.uri.startswith('http'):
                args.uri = 'http://' + args.uri

            favicon_uri = get_favicon_uri(args.uri)
            if not favicon_uri:
                raise Exception("cannot find favicon for URI '{}'".format(args.uri))

            if args.print:
                print(favicon_uri)
            else:
                if not args.filename:
                    args.filename = get_filename(args.uri, favicon_uri, args.png)
                args.filename = os.path.join(args.dir, args.filename)
                get_favicon(favicon_uri, args.filename, args.resize)

    except requests.ConnectionError:
        logging.error("cannot connect to '%s'", args.uri)

    except requests.RequestException as ex:
        logging.error("requests error: %s", ex)

    except Exception as ex:
        logging.error("error: %s", ex)

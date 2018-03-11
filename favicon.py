#!/usr/bin/env python3
from argparse import ArgumentParser
from io import BytesIO
import os.path, re, sys
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from PIL import Image
import requests


HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; WOW64) AppleWebKit/537.36 \
                   (KHTML, like Gecko) Chrome/47.0.2526.111 Safari/537.36'
}


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
            favicon_uri = parsed_uri.scheme + '://' + parsed_uri.netloc + '/' + os.path.join(path, favicon_uri)

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


if __name__ == '__main__':
    parser = ArgumentParser(description='Get favicon for a URIs')
    parser.add_argument('uri', nargs='+', help='URIs to get favicon for')
    parser.add_argument('-v', '--verbose', action='store_true', help='show info messages')
    parser.add_argument('-P', '--print', action='store_true', help='show favicon URI and exit')
    parser.add_argument('-p', '--path', default='', help='save favicon in directory PATH')
    parser.add_argument('-r', '--resize', metavar='SIZE', type=int, default=0, help='resize favicon to SIZE×SIZE')
    parser.add_argument('--png', action='store_true', help='convert favicon to PNG format')
    args = parser.parse_args()

    for uri in args.uri:
        try:
            if not uri:
                raise Exception('empty URI')
            if not uri.startswith('http'):
                uri = 'http://' + uri

            favicon_uri = get_favicon_uri(uri)
            if not favicon_uri:
                raise Exception("cannot find favicon for URI '{}'".format(uri))

            if args.print:
                print(favicon_uri)
                sys.exit(0)

            response = requests.get(favicon_uri, headers=HEADERS)
            if response.status_code != requests.codes.ok:
                response.raise_for_status()

            ext = os.path.splitext(urlparse(favicon_uri).path)[1]
            filename = re.sub(r'\W', '_', urlparse(uri).netloc, flags=re.ASCII) + ('.png' if args.png else ext)
            filename = os.path.join(args.path, filename)

            favicon = Image.open(BytesIO(response.content))
            if args.verbose:
                print("info: favicon for '{}': {}, {!s}".format(uri, favicon.format, favicon.info), file=sys.stderr)
            if args.resize:
                favicon = favicon.resize((args.resize, args.resize))
            favicon.save(filename)

            if args.verbose:
                print("info: favicon for '{}' saved to '{}'".format(uri, filename), file=sys.stderr)

        except requests.ConnectionError:
            print("error: cannot connect to '{}'".format(uri), file=sys.stderr)

        except requests.RequestException as ex:
            print('requests error: {!s}'.format(ex), file=sys.stderr)

        except Exception as ex:
            print('error: {!s}'.format(ex), file=sys.stderr)

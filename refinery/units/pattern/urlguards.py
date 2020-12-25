#!/usr/bin/env python3
import re

from base64 import urlsafe_b64decode
from functools import wraps
from html import unescape
from urllib.parse import unquote, urlparse, parse_qs

from .. import Unit
from ...lib.decorators import unicoded


def unguard(pattern, flags=re.IGNORECASE):
    def decorator(method):
        @wraps(method)
        def _method(self, data):
            return re.sub(pattern, lambda m: method(self, m), data, flags=flags)
        return _method
    return decorator


class urlguards(Unit):
    """
    Restores the original URLs from their 'protected' versions as generated by
    Outlook protection and ProofPoint.
    """

    _PP3RLENC = {
        letter: rl for rl, letter in enumerate(
            'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
            'abcdefghijklmnopqrstuvwxyz'
            '0123456789-_', 2
        )
    }

    @unguard(r'https?://urldefense(?:\.proofpoint)?\.com/v([12])/url\?([:;/_=!?#&.,\w\%\-\+|]+)')
    def _proofpointV2(self, match):
        version = int(match[1])
        self.log_info('proofpoint match:', version)
        argmatch = re.match(
            R'^u=(.+?)&(?:amp;)?{}='.format('k' if version == 1 else '[dc]'),
            match[2],
            flags=re.DOTALL
        )
        if not argmatch:
            self.log_warn('not able to translate unexpected proofpoint format:', match)
            return match[0]
        encoded = argmatch[1]
        if match[1] == '2':
            encoded = encoded.translate(str.maketrans('-_', '%/'))
        return unescape(unquote(encoded))

    @unguard(r'https?://urldefense(?:\.proofpoint)?\.com/v3/__(.+?)__;(.*?)![-\w!?$]+')
    def _proofpointV3(self, match):
        data = unquote(match[1])
        cmap = match[2] + '=' * (-len(match[2]) % 4)
        cmap = urlsafe_b64decode(cmap).decode('UTF-8')
        cursor = 0
        result = ''
        for k in range(len(cmap)):
            ast = data.find('*', cursor)
            if ast < 0:
                break
            result += data[cursor:ast]
            if data[ast + 1] == '*':
                end = self._PP3RLENC[data[ast + 2]]
                result += cmap[k:end]
                ast += 2
            else:
                result += cmap[k]
            cursor = ast + 1
        self.log_debug(result)
        self.log_debug(data[cursor:])
        return result + data[cursor:]

    @unguard(r'https?://\w+.safelinks\.protection\.outlook\.com/([:;/_=!?#&.,\w\%\-\+|]+)')
    def _outlook(self, match):
        result = match[0]
        self.log_info('outlook match:', result)
        parsed = urlparse(result)
        params = parse_qs(parsed.query)
        try:
            result = unquote(params['url'][0])
        except Exception:
            pass
        return result

    @unguard(r'https?://outlook.office.com/actions/ei\?u=([:;/_=!?#&.,\w\%\-\+|]+)')
    def _outlook_image_proxy(self, match):
        return unquote(match[1])

    @unguard(r'https?://(?:[\w-]+\.)?trendmicro.com(?::\d+)?/wis/clicktime/v[12]/(?:query|clickthrough)[:;/_=!?#&.,\w\%\-\+|]+')
    def _trendmicro(self, match):
        result = match[0]
        self.log_info('trendmicro match:', result)
        parsed = urlparse(result)
        params = parse_qs(parsed.query)
        try:
            result = unquote(params['url'][0])
        except Exception:
            pass
        return result

    @unicoded
    def process(self, data: str) -> str:
        newsize, size = 0, len(data)
        while newsize != size:
            for handler in (
                self._proofpointV2,
                self._proofpointV3,
                self._outlook,
                self._outlook_image_proxy,
                self._trendmicro
            ):
                data = handler(data)
            size = newsize
            newsize = len(data)
        return data

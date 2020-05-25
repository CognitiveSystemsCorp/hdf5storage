# Copyright (c) 2016-2020, Freja Nordsiek
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are
# met:
#
# 1. Redistributions of source code must retain the above copyright
# notice, this list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright
# notice, this list of conditions and the following disclaimer in the
# documentation and/or other materials provided with the distribution.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR
# A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT
# HOLDER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL,
# SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT
# LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE,
# DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY
# THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
# (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

""" Module for handling paths. """


import collections.abc
import posixpath
import re


# For escaping and unescaping unicode paths, we need compiled regular
# expressions to finding sequences of one or more dots, find slashes,
# and hex escapes. In addition, we need a dict to lookup the slash
# conversions. Compiling the regular expressions here at initialization
# will help performance by not having to compile new ones every time a
# path is processed.
_find_dots_re = re.compile('\\.+')
_find_invalid_escape_re = re.compile(
    '(^|[^\\\\])\\\\(\\\\\\\\)*($|[^xuU\\\\]'
    '|x[0-9a-fA-F]?($|[^0-9a-fA-F])'
    '|u[0-9a-fA-F]{0,3}($|[^0-9a-fA-F])'
    '|U[0-9a-fA-F]{0,7}($|[^0-9a-fA-F]))')
_find_fslashnull_re = re.compile('[\\\\/\x00]')
_find_escapes_re = re.compile(
    '\\\\+(x[0-9a-fA-F]{2}|u[0-9a-fA-F]{4}|U[0-9a-fA-F]{8})')
_char_escape_conversions = {'\x00': '\\x00',
                            '/': '\\x2f',
                            '\\': '\\\\'}


def _replace_fun_escape(m):
    """ Hex/unicode escape single characters found in regex matches.

    Supports single hex/unicode escapes of the form ``'\\xYY'``,
    ``'\\uYYYY'``, and ``'\\UYYYYYYYY'`` where Y is a hex digit and
    converting single backslashes to double backslashes.

    Only supports forward slash, backward slash, and null for now,
    which are done by lookup.

    .. versionadded:: 0.2

    Parameters
    ----------
    m : regex match

    Returns
    -------
    s : str
        The hex excaped version of the character.

    """
    return _char_escape_conversions[m.group(0)]


def _replace_fun_unescape(m):
    """ Decode single hex/unicode escapes found in regex matches.

    Supports single hex/unicode escapes of the form ``'\\xYY'``,
    ``'\\uYYYY'``, and ``'\\UYYYYYYYY'`` where Y is a hex digit. Only
    decodes if there is an odd number of backslashes.

    .. versionadded:: 0.2

    Parameters
    ----------
    m : regex match

    Returns
    -------
    c : str
        The unescaped character.

    """
    slsh = b'\\'.decode('ascii')
    s = m.group(0)
    count = s.count(slsh)
    if count % 2 == 0:
        return s
    else:
        c = chr(int(s[(count + 1):], base=16))
        return slsh * (count - 1) + c


def escape_path(pth):
    """ Hex/unicode escapes a path.

    Escapes a path so that it can be represented faithfully in an HDF5
    file without changing directories. This means that leading ``'.'``
    must be escaped. ``'/'`` and null must be escaped to. Backslashes
    are escaped as double backslashes. Other escaped characters are
    replaced with ``'\\xYY'``, ``'\\uYYYY', or ``'\\UYYYYYYYY'`` where Y
    are hex digits depending on the unicode numerical value of the
    character. for ``'.'``, both slashes, and null; this will be the
    former (``'\\xYY'``).

    .. versionadded:: 0.2

    Parameters
    ----------
    pth : str or bytes
        The path to escape.

    Returns
    -------
    epth : str
        The escaped path.

    Raises
    ------
    TypeError
        If `pth` is not the right type.

    See Also
    --------
    unescape_path

    """
    if isinstance(pth, bytes):
        pth = pth.decode('utf-8')
    if not isinstance(pth, str):
        raise TypeError('pth must be str or bytes.')
    match = _find_dots_re.match(pth)
    if match is None:
        prefix = ''
        s = pth
    else:
        prefix = '\\x2e' * match.end()
        s = pth[match.end():]
    return prefix + _find_fslashnull_re.sub(_replace_fun_escape, s)


def unescape_path(pth):
    """ Hex/unicode unescapes a path.

    Unescapes a path. Valid escapeds are ``'\\xYY'``, ``'\\uYYYY', or
    ``'\\UYYYYYYYY'`` where Y are hex digits giving the character's
    unicode numerical value and double backslashes which are the escape
    for single backslashes.

    .. versionadded:: 0.2

    Parameters
    ----------
    pth : str
        The path to unescape.

    Returns
    -------
    unpth : str
        The unescaped path.

    Raises
    ------
    TypeError
        If `pth` is not the right type.
    ValueError
        If an invalid escape is found.

    See Also
    --------
    escape_path

    """
    if isinstance(pth, bytes):
        pth = pth.decode('utf-8')
    if not isinstance(pth, str):
        raise TypeError('pth must be str or bytes.')
    # Look for invalid escapes.
    if _find_invalid_escape_re.search(pth) is not None:
        raise ValueError('Invalid escape found.')
    # Do all hex/unicode escapes.
    s = _find_escapes_re.sub(_replace_fun_unescape, pth)
    # Do all double backslash escapes.
    return s.replace(b'\\\\'.decode('ascii'), b'\\'.decode('ascii'))


def process_path(pth):
    """ Processes paths.

    Processes the provided path and breaks it into it Group part
    (`groupname`) and target part (`targetname`). ``bytes`` paths are
    converted to ``str``. Separated paths are given as an iterable of
    ``str`` and ``bytes``. Each part of a separated path is escaped
    using ``escape_path``. Otherwise, the path is assumed to be already
    escaped. Escaping is done so that targets with a part that starts
    with one or more periods, contain slashes, and/or contain nulls can
    be used without causing the wrong Group to be looked in or the wrong
    target to be looked at. It essentially allows one to make a Dataset
    named ``'..'`` or ``'a/a'`` instead of moving around in the Dataset
    hierarchy.

    All paths are POSIX style.

    .. versionadded:: 0.2

    Parameters
    ----------
    pth : str or bytes or iterable of str or bytes
        The POSIX style path as a ``str`` or ``bytes`` or the
        separated path in an iterable with the elements being ``str``
        and ``bytes``. For separated paths, escaping will be done
        on each part.

    Returns
    -------
    groupname : str
        The path to the Group containing the target `pth` was pointing
        to.
    targetname : str
        The name of the target pointed to by `pth` in the Group
        `groupname`.

    Raises
    ------
    TypeError
        If `pth` is not of the right type.

    See Also
    --------
    escape_path

    """
    # Do conversions and possibly escapes.
    if isinstance(pth, bytes):
        p = pth.decode('utf-8')
    elif isinstance(pth, str):
        p = pth
    elif not isinstance(pth, collections.abc.Iterable):
        raise TypeError('p must be str, bytes, or an iterable '
                        + 'solely of one of those two.')
    else:
        # Check that all elements are unicode or bytes.
        if not all([isinstance(s, (bytes, str)) for s in pth]):
            raise TypeError('Elements of p must be str or bytes.')

        # Escape (and possibly convert to unicode) each element and then
        # join them all together.
        parts = [None] * len(pth)
        for i, s in enumerate(pth):
            if isinstance(s, bytes):
                s = s.decode('utf-8')
            parts[i] = escape_path(s)
        parts = tuple(parts)
        p = posixpath.join(*parts)

    # Remove double slashes and a non-root trailing slash.
    path = posixpath.normpath(p)

    # Extract the group name and the target name (will be a dataset if
    # data can be mapped to it, but will end up being made into a group
    # otherwise. As HDF5 files use posix path, conventions, posixpath
    # will do everything.
    groupname = posixpath.dirname(path)
    targetname = posixpath.basename(path)

    # If groupname got turned into blank, then it is just root.
    if len(groupname) == 0:
        groupname = b'/'.decode('ascii')

    # If targetname got turned blank, then it is the current directory.
    if len(targetname) == 0:
        targetname = b'.'.decode('ascii')

    return groupname, targetname

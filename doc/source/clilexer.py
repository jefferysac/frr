
import pygments
from pygments.formatters import HtmlFormatter

from pygments.lexer import RegexLexer
from pygments.token import *

class DefunLexer(RegexLexer):
    name = 'Defun'
    aliases = ['defun']
    filenames = []

    tokens = {
        'root': [
            (r'(-|\+)?[a-z0-9\*][-+_a-zA-Z0-9\*]*', Literal),
            (r'A\.B\.C\.D(\/M)?', String),
            (r'X:X::X:X(\/M)?', String),
            (r'[A-Z][-_a-zA-Z:0-9]+', Name.Variable),
            (r'\((-|\+)?[0-9]{1,20}[ ]?-[ ]?(-|\+)?[0-9]{1,20}\)', Number),
            (r'[\|]', Operator),
            (r'[\[\]<>\{\}]', Keyword),
            (r'\.\.\.', Operator),
            (r'\s+', Text),
        ]
    }

if __name__ == '__main__':
    import sys
    cdef = r'clear [ip] bgp ipv6 <unicast|multicast> prefix X:X::X:X/M WORD'
    pygments.highlight(cdef, DefunLexer(), HtmlFormatter(full = True), sys.stdout)


import clippy, traceback, sys, os
from collections import OrderedDict
from functools import reduce
from pprint import pprint
from string import Template
from io import StringIO

def graph_iterate(graph):
    queue = [(graph.first(), frozenset(), 0)]
    while len(queue) > 0:
        node, stop, depth = queue.pop(0)
        yield node, depth

        join = node.join()
        if join is not None:
            queue.insert(0, (join, stop.union(frozenset([node])), depth))
            join = frozenset([join])

        stop = join or stop
        nnext = node.next()
        for n in reversed(nnext):
            if n not in stop and n is not node:
                queue.insert(0, (n, stop, depth + 1))

def dump(graph):
    for i, depth in graph_iterate(graph):
        print('\t%s%s %r' % ('  ' * (depth * 2), i.type, i.text))

class RenderHandler(object):
    def __init__(self, token):
        pass
    def combine(self, other):
        if type(self) == type(other):
            return other
        return StringHandler(None)

    deref = ''
    drop_str = False

class StringHandler(RenderHandler):
    argtype = 'const char *'
    decl = Template('const char *$varname = NULL;')
    code = Template('$varname = argv[_i]->arg;')
    drop_str = True

class LongHandler(RenderHandler):
    argtype = 'long'
    decl = Template('long $varname = 0;')
    code = Template('''\
char *_end;
$varname = strtol(argv[_i]->arg, &_end, 10);
_fail = (_end == argv[_i]->arg) || (*_end != '\\0');''')

class PrefixBase(RenderHandler):
    def combine(self, other):
        if type(self) == type(other):
            return other
        if type(other) in [Prefix4Handler, Prefix6Handler, PrefixGenHandler]:
            return PrefixGenHandler(None)
        return StringHandler(None)
    deref = '&'
class Prefix4Handler(PrefixBase):
    argtype = 'const struct prefix_ipv4 *'
    decl = Template('struct prefix_ipv4 $varname = { };')
    code = Template('_fail = !str2prefix_ipv4(argv[_i]->arg, &$varname);')
class Prefix6Handler(PrefixBase):
    argtype = 'const struct prefix_ipv6 *'
    decl = Template('struct prefix_ipv6 $varname = { };')
    code = Template('_fail = !str2prefix_ipv6(argv[_i]->arg, &$varname);')
class PrefixGenHandler(PrefixBase):
    argtype = 'const struct prefix *'
    decl = Template('struct prefix $varname = { };')
    code = Template('_fail = !str2prefix(argv[_i]->arg, &$varname);')

class IPBase(RenderHandler):
    def combine(self, other):
        if type(self) == type(other):
            return other
        if type(other) in [IP4Handler, IP6Handler, IPGenHandler]:
            return IPGenHandler(None)
        return StringHandler(None)
class IP4Handler(IPBase):
    argtype = 'struct in_addr'
    decl = Template('struct in_addr $varname = { INADDR_ANY };')
    code = Template('_fail = !inet_aton(argv[_i]->arg, &$varname);')
class IP6Handler(IPBase):
    argtype = 'struct in6_addr'
    decl = Template('struct in6_addr $varname = IN6ADDR_ANY_INIT;')
    code = Template('_fail = !inet_pton(AF_INET6, argv[_i]->arg, &$varname);')
class IPGenHandler(IPBase):
    argtype = 'const union sockunion *'
    decl = Template('''union sockunion s__$varname = { .sa.sa_family = AF_UNSPEC }, *$varname = NULL;''')
    code = Template('''\
if (argv[_i]->text[0] == 'X') {
	s__$varname.sa.sa_family = AF_INET6;
	_fail = !inet_pton(AF_INET6, argv[_i]->arg, &s__$varname.sin6.sin6_addr);
	$varname = &s__$varname;
} else {
	s__$varname.sa.sa_family = AF_INET;
	_fail = !inet_aton(argv[_i]->arg, &s__$varname.sin.sin_addr);
	$varname = &s__$varname;
}''')

def mix_handlers(handlers):
    def combine(a, b):
        if a is None:
            return b
        return a.combine(b)
    return reduce(combine, handlers, None)

handlers = {
    'WORD_TKN':         StringHandler,
    'VARIABLE_TKN':     StringHandler,
    'RANGE_TKN':        LongHandler,
    'IPV4_TKN':         IP4Handler,
    'IPV4_PREFIX_TKN':  Prefix4Handler,
    'IPV6_TKN':         IP6Handler,
    'IPV6_PREFIX_TKN':  Prefix6Handler,
}

templ = Template('''/* $fnname => "$cmddef" */
DEFUN_CMD_FUNC_DECL($fnname)
#define funcdecl_$fnname static int ${fnname}_magic(\\
	const struct cmd_element *self __attribute__ ((unused)),\\
	struct vty *vty __attribute__ ((unused)),\\
	int argc __attribute__ ((unused)),\\
	struct cmd_token *argv[] __attribute__ ((unused))$argdefs)
funcdecl_$fnname;
DEFUN_CMD_FUNC_TEXT($fnname)
{
	int _i;
	unsigned _fail = 0, _failcnt = 0;
$argdecls
	for (_i = 0; _i < argc; _i++) {
		if (!argv[_i]->varname)
			continue;
		_fail = 0;$argblocks
		if (_fail)
			vty_out (vty, "%% invalid input for %s: %s%s",
				argv[_i]->varname, argv[_i]->arg, VTY_NEWLINE);
		_failcnt += _fail;
	}
	if (_failcnt)
		return CMD_WARNING;
	return ${fnname}_magic(self, vty, argc, argv$arglist);
}

''')
argblock = Template('''
		if (!strcmp(argv[_i]->varname, \"$varname\")) {$strblock
			$code
		}''')

def process_file(fn, ofd, dumpfd, all_defun):
    filedata = clippy.parse(fn)

    for entry in filedata['data']:
        if entry['type'] == 'DEFPY' or (all_defun and entry['type'].startswith('DEFUN')):
            cmddef = entry['args'][2]
            for i in cmddef:
                assert i.startswith('"') and i.endswith('"')
            cmddef = ''.join([i[1:-1] for i in cmddef])

            graph = clippy.Graph(cmddef)
            args = OrderedDict()
            for token, depth in graph_iterate(graph):
                if token.type not in handlers:
                    continue
                if token.varname is None:
                    continue
                arg = args.setdefault(token.varname, [])
                arg.append(handlers[token.type](token))

            #print('-' * 76)
            #pprint(entry)
            #dump(graph)
            #pprint(args)

            params = { 'cmddef': cmddef, 'fnname': entry['args'][0][0] }
            argdefs = []
            argdecls = []
            arglist = []
            argblocks = []
            doc = []

            def do_add(handler, varname, attr = ''):
                argdefs.append(',\\\n\t%s %s%s' % (handler.argtype, varname, attr))
                argdecls.append('\t%s\n' % (handler.decl.substitute({'varname': varname}).replace('\n', '\n\t')))
                arglist.append(', %s%s' % (handler.deref, varname))
                if attr == '':
                    at = handler.argtype
                    if not at.startswith('const '):
                        at = '. . . ' + at
                    doc.append('\t%-26s %s' % (at, varname))

            for varname in args.keys():
                handler = mix_handlers(args[varname])
                #print(varname, handler)
                if handler is None: continue
                do_add(handler, varname)
                code = handler.code.substitute({'varname': varname}).replace('\n', '\n\t\t\t')
                strblock = ''
                if not handler.drop_str:
                    do_add(StringHandler(None), '%s_str' % (varname), ' __attribute__ ((unused))')
                    strblock = '\n\t\t\t%s_str = argv[_i]->arg;' % (varname)
                argblocks.append(argblock.substitute({'varname': varname, 'strblock': strblock, 'code': code}))

            if dumpfd is not None:
                if len(arglist) > 0:
                    dumpfd.write('"%s":\n%s\n\n' % (cmddef, '\n'.join(doc)))
                else:
                    dumpfd.write('"%s":\n\t---- no magic arguments ----\n\n' % (cmddef))

            params['argdefs'] = ''.join(argdefs)
            params['argdecls'] = ''.join(argdecls)
            params['arglist'] = ''.join(arglist)
            params['argblocks'] = ''.join(argblocks)
            ofd.write(templ.substitute(params))

def wrdiff(filename, buf):
    expl = ''
    if hasattr(buf, 'getvalue'):
        buf = buf.getvalue()
    old = None
    try:    old = open(filename, 'r').read()
    except: pass
    if old == buf:
        # sys.stderr.write('%s unchanged, not written\n' % (filename))
        return
    with open('.new.' + filename, 'w') as out:
        out.write(buf)
    os.rename('.new.' + filename, filename)

if __name__ == '__main__':
    import argparse

    argp = argparse.ArgumentParser(description = 'FRR CLI preprocessor in Python')
    argp.add_argument('--all-defun', action = 'store_const', const = True)
    argp.add_argument('--dump', action = 'store_const', const = True)
    argp.add_argument('-o', type = str)
    argp.add_argument('cfile', type = str)
    args = argp.parse_args()

    dumpfd = None
    if args.o is not None:
        ofd = StringIO()
        if args.dump:
            dumpfd = sys.stdout
    else:
        ofd = sys.stdout
        if args.dump:
            dumpfd = sys.stderr

    process_file(args.cfile, ofd, dumpfd, args.all_defun)

    if args.o is not None:
        wrdiff(args.o, ofd)

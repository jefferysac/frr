# -*- coding: utf-8 -*-

__version__ = "0.0"
release = __version__
version = release.rsplit('.', 1)[0]

import re
from collections import OrderedDict

from docutils import nodes
from docutils.parsers.rst import directives

from sphinx import addnodes
from sphinx.roles import XRefRole
from sphinx.locale import l_, _
from sphinx.domains import Domain, ObjType, Index
from sphinx.directives import ObjectDescription, DescDirective
from sphinx.util.nodes import make_refnode
from sphinx.util.docfields import Field, GroupedField, TypedField

class FRRBase(ObjectDescription):
    def add_target_and_index(self, name_cls, sig, signode):
        objects = self.env.domaindata['frrcli']['objects']

        name = name_cls[0]
        if name in objects:
            return

        signode['names'].append(name)
        signode['ids'].append(self.objtype + '-' + name.strip('$'))

        self.state.document.note_explicit_target(signode)
        objects[name] = (self.env.docname, self.objtype)

        indextext = _('%s') % (name)
        self.indexnode['entries'].append(('single', indextext,
                                         name, name))

    def get_index_text(self, objectname, name):
        return _('%s (%s)' % (name, objectname))

class FRRCLITokenField(Field):
    is_grouped = False #True

    def __init__(self):
        super(FRRCLITokenField, self).__init__('token', label=l_('X'), has_arg=True, names=('token', ))

    def make_entry(self, fieldarg, content):
        ftype, varname = fieldarg.split(None, 1)

        assert type(content[0]) == nodes.inline
        text = '?'
        if '$$' in content[0].rawsource:
            text, remain = content[0].rawsource.split('$$', 1)
            newnode = nodes.inline(remain, remain)
            content = [newnode] + content[1:]

        return (ftype, varname, text, content)

    def make_field(self, types, domain, items):
        ftype, varname, text, content = items

        field_body = nodes.field_body('', nodes.paragraph('', '', *content))
        field_name = nodes.field_name('', text)
        return nodes.field('', field_name, field_body)

    def unused0(self):
        args = OrderedDict()
        for item in items:
            ftype, varname, content = item
            args.setdefault(varname, []).append((ftype, content))

        fields = []
        for varname, specs in args.items():
            bodies = []
            for spec in specs:
                bodies.append(nodes.paragraph('', '', *spec[1])) #, *[s[1][0] for s in specs]))

            #field_items = nodes.paragraph('', '', *[s[1][0] for s in specs])

            field_body = nodes.field_body('', *bodies)
            field_name = nodes.field_name('', varname)
            fields.append(nodes.field('', field_name, field_body))
        fl = nodes.field_list('', *fields)

        field_body = nodes.field_body('', fl)
        field_name = nodes.field_name('', 'Parameters')
        return nodes.field('', field_name, field_body)

class FRRCLIFunction(FRRBase):
    doc_field_types = [
        FRRCLITokenField(),
    ]
    def handle_signature(self, sig, signode):
        desc_name = '%s' % sig
        signode += addnodes.desc_name(desc_name, desc_name)
        #if len(args) > 0:
        #    signode += addnodes.desc_addname(args, args)
        return desc_name

class FRRCLIDomain(Domain):
    '''FRR CLI Domain'''
    name = 'frrcli'
    label = "FRR CLI"

    object_types = {
        'function':   ObjType(l_('function'),   'dir'),
    }
    directives = {
        'function':   FRRCLIFunction,
    }
    roles = {
        'func':  XRefRole(),
    }
    initial_data = {
        'objects': {},
    }

    def clear_doc(self, docname):
        for name, (doc, typ) in self.data['objects'].items():
            if doc == docname:
                del self.data['objects'][name]
    def resolve_xref(self, env, fromdocname, builder, typ, target, node,
                     contnode):
        objects = self.data['objects']
        if target in objects:
            docname, objtype = objects[target]
            return make_refnode(builder, fromdocname,
                                docname,
                                objtype + '-' + target,
                                contnode, target + ' ' + objtype)

    def get_objects(self):
        for name, (docname, typ) in self.data['objects'].iteritems():
            yield name, name, typ, docname, typ + '-' + name, 1

def setup(app):
    from clilexer import DefunLexer
    app.add_lexer("frrcli", DefunLexer())
    app.add_domain(FRRCLIDomain)


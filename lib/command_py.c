
#include <Python.h>
#include "structmember.h"
#include <string.h>
#include <stdlib.h>

#include "command_graph.h"
#include "clippy.h"

struct wrap_graph;
static PyObject *graph_to_pyobj(struct wrap_graph *graph, struct graph_node *gn);

struct wrap_graph_node {
	PyObject_HEAD

	bool allowrepeat;
	const char *type;

	bool deprecated;
	bool hidden;
	const char *text;
	const char *desc;
	const char *varname;
	long long min, max;

	struct graph_node *node;
	struct wrap_graph *wgraph;
	size_t idx;
};

struct wrap_graph {
	PyObject_HEAD

	char *definition;
	struct graph *graph;
	struct wrap_graph_node **nodewrappers;
};

static PyObject *refuse_new(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
	PyErr_SetString(PyExc_ValueError, "cannot create instances of this type");
	return NULL;
}

#define member(name, type) {(char *)#name, type, offsetof(struct wrap_graph_node, name), READONLY, \
	(char *)#name " (" #type ")"}
static PyMemberDef members_graph_node[] = {
	member(allowrepeat, T_BOOL),
	member(type, T_STRING),
	member(deprecated, T_BOOL),
	member(hidden, T_BOOL),
	member(text, T_STRING),
	member(desc, T_STRING),
	member(min, T_LONGLONG),
	member(max, T_LONGLONG),
	member(varname, T_STRING),
	{},
};
#undef member

static PyObject *graph_node_next(PyObject *self, PyObject *args)
{
	struct wrap_graph_node *wrap = (struct wrap_graph_node *)self;
	PyObject *pylist;

	if (wrap->node->data
		&& ((struct cmd_token *)wrap->node->data)->type == END_TKN)
		return PyList_New(0);
	pylist = PyList_New(vector_active(wrap->node->to));
	for (ssize_t i = 0; i < vector_active(wrap->node->to); i++) {
		struct graph_node *gn = vector_slot(wrap->node->to, i);
		PyList_SetItem(pylist, i, graph_to_pyobj(wrap->wgraph, gn));
	}
	return pylist;
};

static PyObject *graph_node_join(PyObject *self, PyObject *args)
{
	struct wrap_graph_node *wrap = (struct wrap_graph_node *)self;

	if (wrap->node->data
		&& ((struct cmd_token *)wrap->node->data)->type == END_TKN)
		Py_RETURN_NONE;

	struct cmd_token *tok = wrap->node->data;
	if (tok->type != FORK_TKN)
		Py_RETURN_NONE;

	return graph_to_pyobj(wrap->wgraph, tok->forkjoin);
};

static PyMethodDef methods_graph_node[] = {
	{"next", graph_node_next, METH_NOARGS, "outbound graph edge list"},
	{"join", graph_node_join, METH_NOARGS, "outbound join node"},
	{}
};

static void graph_node_wrap_free(void *arg)
{
	struct wrap_graph_node *wrap = arg;
	wrap->wgraph->nodewrappers[wrap->idx] = NULL;
	Py_DECREF(wrap->wgraph);
}

static PyTypeObject typeobj_graph_node = {
	PyVarObject_HEAD_INIT(NULL, 0)
	.tp_name	= "clippy.GraphNode",
	.tp_basicsize	= sizeof(struct wrap_graph_node),
	.tp_flags	= Py_TPFLAGS_DEFAULT,
	.tp_doc		= "struct graph_node *",
	.tp_new		= refuse_new,
	.tp_free	= graph_node_wrap_free,
	.tp_members	= members_graph_node,
	.tp_methods	= methods_graph_node,
};

static PyObject *graph_to_pyobj(struct wrap_graph *wgraph, struct graph_node *gn)
{
	struct wrap_graph_node *wrap;
	size_t i;

	for (i = 0; i < vector_active(wgraph->graph->nodes); i++)
		if (vector_slot(wgraph->graph->nodes, i) == gn)
			break;
	if (i == vector_active(wgraph->graph->nodes)) {
		PyErr_SetString(PyExc_ValueError, "cannot find node in graph");
		return NULL;
	}
	if (wgraph->nodewrappers[i]) {
		PyObject *obj = (PyObject *)wgraph->nodewrappers[i];
		Py_INCREF(obj);
		return obj;
	}

	wrap = (struct wrap_graph_node *)typeobj_graph_node.tp_alloc(&typeobj_graph_node, 0);
	if (!wrap)
		return NULL;
	wgraph->nodewrappers[i] = wrap;
	Py_INCREF(wgraph);

	wrap->idx = i;
	wrap->wgraph = wgraph;
	wrap->node = gn;
	wrap->type = "NULL";
	wrap->allowrepeat = false;
	if (gn->data) {
		struct cmd_token *tok = gn->data;
		switch (tok->type) {
#define item(x) case x: wrap->type = #x; break;
		item(WORD_TKN)          // words
		item(VARIABLE_TKN)      // almost anything
		item(RANGE_TKN)         // integer range
		item(IPV4_TKN)          // IPV4 addresses
		item(IPV4_PREFIX_TKN)   // IPV4 network prefixes
		item(IPV6_TKN)          // IPV6 prefixes
		item(IPV6_PREFIX_TKN)   // IPV6 network prefixes

		/* plumbing types */
		item(FORK_TKN)
		item(JOIN_TKN)
		item(START_TKN)
		item(END_TKN)
		default:
			wrap->type = "???";
		}

		wrap->deprecated = (tok->attr == CMD_ATTR_DEPRECATED);
		wrap->hidden = (tok->attr == CMD_ATTR_HIDDEN);
		wrap->text = tok->text;
		wrap->desc = tok->desc;
		wrap->varname = tok->varname;
		wrap->min = tok->min;
		wrap->max = tok->max;
		wrap->allowrepeat = tok->allowrepeat;
	}

	return (PyObject *)wrap;
}

#define member(name, type) {(char *)#name, type, offsetof(struct wrap_graph, name), READONLY, \
	(char *)#name " (" #type ")"}
static PyMemberDef members_graph[] = {
	member(definition, T_STRING),
	{},
};
#undef member

static PyObject *graph_first(PyObject *self, PyObject *args)
{
	struct wrap_graph *gwrap = (struct wrap_graph *)self;
	struct graph_node *gn = vector_slot(gwrap->graph->nodes, 0);
	return graph_to_pyobj(gwrap, gn);
};

static PyMethodDef methods_graph[] = {
	{"first", graph_first, METH_NOARGS, "first graph node"},
	{}
};

static PyObject *graph_parse(PyTypeObject *type, PyObject *args, PyObject *kwds);

static void graph_wrap_free(void *arg)
{
	struct wrap_graph *wgraph = arg;
	free(wgraph->nodewrappers);
	free(wgraph->definition);
}

static PyTypeObject typeobj_graph = {
	PyVarObject_HEAD_INIT(NULL, 0)
	.tp_name	= "clippy.Graph",
	.tp_basicsize	= sizeof(struct wrap_graph),
	.tp_flags	= Py_TPFLAGS_DEFAULT,
	.tp_doc		= "struct graph *",
	.tp_new		= graph_parse,
	.tp_free	= graph_wrap_free,
	.tp_members	= members_graph,
	.tp_methods	= methods_graph,
};

static PyObject *graph_parse(PyTypeObject *type, PyObject *args, PyObject *kwds)
{
	const char *def, *doc = NULL;
	struct wrap_graph *gwrap;
	static const char *kwnames[] = { "cmddef", "doc", NULL };

	gwrap = (struct wrap_graph *)typeobj_graph.tp_alloc(&typeobj_graph, 0);
	if (!gwrap)
		return NULL;

	if (!PyArg_ParseTupleAndKeywords(args, kwds, "s|s", (char **)kwnames, &def, &doc))
		return NULL;

	struct graph *graph = graph_new ();
	struct cmd_token *token = cmd_token_new (START_TKN, 0, NULL, NULL);
	graph_new_node (graph, token, (void (*)(void *)) &cmd_token_del);

	struct cmd_element cmd = { .string = def, .doc = doc };
	cmd_graph_parse (graph, &cmd);
	cmd_graph_names (graph);

	gwrap->graph = graph;
	gwrap->definition = strdup(def);
	gwrap->nodewrappers = calloc(vector_active(graph->nodes), sizeof (PyObject *));
	return (PyObject *)gwrap;
}

static PyMethodDef clippy_methods[] = {
	{"parse", clippy_parse, METH_VARARGS, "Parse a C file"},
	{NULL, NULL, 0, NULL}
};

#if PY_MAJOR_VERSION >= 3
static struct PyModuleDef pymoddef_clippy = {
	PyModuleDef_HEAD_INIT,
	"clippy",
	NULL, /* docstring */
	-1,
	clippy_methods,
};
#define modcreate() PyModule_Create(&pymoddef_clippy)
#define initret(val) return val;
#else
#define modcreate() Py_InitModule("clippy", clippy_methods)
#define initret(val) do { \
	if (!val) Py_FatalError("initialization failure"); \
	return; } while (0)
#endif

PyMODINIT_FUNC command_py_init(void)
{
	PyObject* pymod;

	if (PyType_Ready(&typeobj_graph_node) < 0)
		initret(NULL);
	if (PyType_Ready(&typeobj_graph) < 0)
		initret(NULL);

	pymod = modcreate();
	if (!pymod)
		initret(NULL);

	Py_INCREF(&typeobj_graph_node);
	PyModule_AddObject(pymod, "GraphNode", (PyObject *)&typeobj_graph_node);
	Py_INCREF(&typeobj_graph);
	PyModule_AddObject(pymod, "Graph", (PyObject *)&typeobj_graph);
	initret(pymod);
}

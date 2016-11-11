%{
#include "config.h"
#include <Python.h>
#include <string.h>
#include <stdlib.h>

#include "command_graph.h"
#include "clippy.h"

#define ID		258
#define PREPROC		259
#define OPERATOR	260
#define STRING		261
#define COMMENT		262
#define SPECIAL		263

#define DEFUNNY		270
#define INSTALL		271
#define TARGETS		272

int comment_link;
char string_end;

char *value;

static void extendbuf(char **what, const char *arg)
{
	if (!*what)
		*what = strdup(arg);
	else {
		size_t vall = strlen(*what), argl = strlen(arg);
		*what = realloc(*what, vall + argl + 1);
		memcpy(*what + vall, arg, argl);
		(*what)[vall + argl] = '\0';
	}
}
#define extend(x) extendbuf(&value, x)

%}

ID		[A-Za-z0-9_]+
OPERATOR	[!%&/\[\]{}=?:^|\*.;><~'\\+-]
SPECIAL		[(),]

%pointer
%option yylineno
%option noyywrap
%option noinput
%option nounput
%option outfile="defun_lex.c"
%option prefix="def_yy"
%option 8bit

%s linestart
%x comment
%x linecomment
%x preproc
%x rstring
%%
				BEGIN(linestart);

\n				BEGIN(linestart);

<INITIAL,linestart,preproc>"/*"	comment_link = YY_START; extend(yytext); BEGIN(comment);
<comment>[^*\n]*		extend(yytext);
<comment>"*"+[^*/\n]*		extend(yytext);
<comment>\n			extend(yytext);
<comment>"*"+"/"		extend(yytext); BEGIN(comment_link); return COMMENT;

<INITIAL,linestart,preproc>"//"	comment_link = YY_START; extend(yytext); BEGIN(linecomment);
<linecomment>[^\n]*		extend(yytext);
<linecomment>\n			BEGIN((comment_link == INITIAL) ? linestart : comment_link); return COMMENT;

<linestart>#			BEGIN(preproc);
<preproc>\n			BEGIN(INITIAL); return PREPROC;
<preproc>[^\n\\]+		extend(yytext);
<preproc>\\\n			extend(yytext);
<preproc>\\+[^\n]		extend(yytext);

[\"\']				string_end = yytext[0]; extend(yytext); BEGIN(rstring);
<rstring>[\"\']			{
					extend(yytext);
					if (yytext[0] == string_end) {
						BEGIN(INITIAL);
						return STRING;
					}
				}
<rstring>\\\n			/* ignore */
<rstring>\\.			extend(yytext);
<rstring>[^\\\"\']+		extend(yytext);

"DEFUN"				value = strdup(yytext); return DEFUNNY;
"DEFUN_NOSH"			value = strdup(yytext); return DEFUNNY;
"DEFUN_HIDDEN"			value = strdup(yytext); return DEFUNNY;
"DEFPY"				value = strdup(yytext); return DEFUNNY;
"ALIAS"				value = strdup(yytext); return DEFUNNY;
"ALIAS_HIDDEN"			value = strdup(yytext); return DEFUNNY;
"install_element"		value = strdup(yytext); return INSTALL;
"VTYSH_TARGETS"			value = strdup(yytext); return TARGETS;

[ \t\n]+			/* ignore */
\\				/* ignore */
{ID}				BEGIN(INITIAL); value = strdup(yytext); return ID;
{OPERATOR}			BEGIN(INITIAL); value = strdup(yytext); return OPERATOR;
{SPECIAL}			BEGIN(INITIAL); value = strdup(yytext); return SPECIAL;
.				/* printf("-- '%s' in init\n", yytext); */ BEGIN(INITIAL); return yytext[0];

%%

static int yylex_clr(char **retbuf)
{
	int rv = def_yylex();
	*retbuf = value;
	value = NULL;
	return rv;
}

static PyObject *get_args(void)
{
	PyObject *pyObj = PyList_New(0);
	PyObject *pyArg = NULL;

	char *tval;
	int depth = 1;
	int token;

	while ((token = yylex_clr(&tval)) != YY_NULL) {
		if (token == SPECIAL && tval[0] == '(')
			break;
		if (token == COMMENT)
			continue;
		fprintf(stderr, "invalid input!\n");
		exit(1);
	}

	while ((token = yylex_clr(&tval)) != YY_NULL) {
		if (token == COMMENT)
			continue;
		if (token == SPECIAL) {
			if (depth == 1 && (tval[0] == ',' || tval[0] == ')')) {
				if (pyArg)
					PyList_Append(pyObj, pyArg);
				pyArg = NULL;
				if (tval[0] == ')')
					break;
				continue;
			}
			if (tval[0] == '(')
				depth++;
			if (tval[0] == ')')
				depth--;
		}
		if (!pyArg)
			pyArg = PyList_New(0);
		PyList_Append(pyArg, PyUnicode_FromString(tval));
	}
	return pyObj;
}

PyObject *clippy_parse(PyObject *self, PyObject *args)
{
	const char *filename;
	if (!PyArg_ParseTuple(args, "s", &filename))
		return NULL;
	
	FILE *fd = fopen(filename, "r");
	if (!fd)
		return PyErr_SetFromErrnoWithFilename(PyExc_IOError, filename);

	char *tval;
	int token;
	yyin = fd;
	value = NULL;

	PyObject *pyCont = PyDict_New();
	PyObject *pyObj = PyList_New(0);
	PyDict_SetItemString(pyCont, "filename", PyUnicode_FromString(filename));
	PyDict_SetItemString(pyCont, "data", pyObj);

	while ((token = yylex_clr(&tval)) != YY_NULL) {
                int lineno = yylineno;
		PyObject *pyItem = NULL, *pyArgs;
		switch (token) {
		case DEFUNNY:
		case INSTALL:
		case TARGETS:
			pyArgs = get_args();
			pyItem = PyDict_New();
			PyDict_SetItemString(pyItem, "type", PyUnicode_FromString(tval));
			PyDict_SetItemString(pyItem, "args", pyArgs);
			break;
		case COMMENT:
                        if (strncmp(tval, "//~", 3) && strncmp(tval, "/*~", 3))
                                break;
			pyItem = PyDict_New();
			PyDict_SetItemString(pyItem, "type", PyUnicode_FromString("COMMENT"));
			PyDict_SetItemString(pyItem, "line", PyUnicode_FromString(tval));
			break;
		case PREPROC:
			pyItem = PyDict_New();
			PyDict_SetItemString(pyItem, "type", PyUnicode_FromString("PREPROC"));
			PyDict_SetItemString(pyItem, "line", PyUnicode_FromString(tval));
			break;
		}
		if (pyItem) {
			PyDict_SetItemString(pyItem, "lineno", PyLong_FromLong(lineno));
			PyList_Append(pyObj, pyItem);
		}
	}
	def_yylex_destroy();
	fclose(fd);
	return pyCont;
}
#ifndef _FRR_CLIPPY_H
#define _FRR_CLIPPY_H

#include <Python.h>

extern PyObject *clippy_parse(PyObject *self, PyObject *args);
extern PyMODINIT_FUNC command_py_init(void);

#endif /* _FRR_CLIPPY_H */

"""Decorators for integrating pandera into existing data pipelines."""

import inspect
import warnings

from collections import OrderedDict

import wrapt

from . import errors


def _get_fn_argnames(fn):
    arg_spec_args = inspect.getfullargspec(fn).args

    if inspect.ismethod(fn) and arg_spec_args[0] == "self":
        # don't include "self" argument
        arg_spec_args = arg_spec_args[1:]
    return arg_spec_args


def check_input(
        schema,
        obj_getter=None,
        head=None,
        tail=None,
        sample=None,
        random_state=None):
    """Validate function argument when function is called.

    This is a decorator function that validates the schema of a dataframe
    argument in a function. Note that if a transformer is specified by the
    schema, the decorator will return the transformed dataframe, which will be
    passed into the decorated function.

    :param schema: dataframe/series schema object
    :type schema: DataFrameSchema|SeriesSchema
    :param obj_getter:  (Default value = None) if int, obj_getter refers to the
        the index of the pandas dataframe/series to be validated in the args
        part of the function signature. If str, obj_getter refers to the
        argument name of the pandas dataframe/series in the function signature.
        This works even if the series/dataframe is passed in as a positional
        argument when the function is called. If None, assumes that the
        dataframe/series is the first argument of the decorated function
    :type obj_getter: int|str|None
    :param head: validate the first n rows. Rows overlapping with `tail` or
        `sample` are de-duplicated.
    :type head: int
    :param tail: validate the last n rows. Rows overlapping with `head` or
        `sample` are de-duplicated.
    :type tail: int
    :param sample: validate a random sample of n rows. Rows overlapping
        with `head` or `tail` are de-duplicated.
    """

    @wrapt.decorator
    def _wrapper(fn, instance, args, kwargs):
        args = list(args)
        if isinstance(obj_getter, int):
            try:
                args[obj_getter] = schema.validate(args[obj_getter])
            except IndexError as e:
                raise errors.SchemaError(
                        "error in check_input decorator of function '%s': the "
                        "index '%s' was supplied to the check but this "
                        "function accepts '%s' arguments, so the maximum "
                        "index is '%s'. The full error is: '%s'" %
                        (fn.__name__,
                         obj_getter,
                         len(_get_fn_argnames(fn)),
                         max(0, len(_get_fn_argnames(fn))-1),
                         e
                         )
                        )
        elif isinstance(obj_getter, str):
            if obj_getter in kwargs:
                kwargs[obj_getter] = schema.validate(kwargs[obj_getter])
            else:
                arg_spec_args = _get_fn_argnames(fn)
                args_dict = OrderedDict(
                    zip(arg_spec_args, args))
                args_dict[obj_getter] = schema.validate(args_dict[obj_getter])
                args = list(args_dict.values())
        elif obj_getter is None:
            try:
                args[0] = schema.validate(
                    args[0], head, tail, sample, random_state)
            except errors.SchemaError as e:
                raise errors.SchemaError(
                    "error in check_input decorator of function '%s': %s" %
                    (fn.__name__, e))
        else:
            raise ValueError(
                "obj_getter is unrecognized type: %s" % type(obj_getter))
        return fn(*args, **kwargs)

    return _wrapper


def check_output(
        schema,
        obj_getter=None,
        head=None,
        tail=None,
        sample=None,
        random_state=None):
    """Validate function output.

    Similar to input validator, but validates the output of the decorated
    function. Note that the `transformer` function supplied to the
    DataFrameSchema will not have an effect in the check_output schema
    validator.

    :param schema: dataframe/series schema object
    :type schema: DataFrameSchema|SeriesSchema
    :param obj_getter:  (Default value = None) if int, assumes that the output
        of the decorated function is a list-like object, where obj_getter is
        the index of the pandas data dataframe/series to be validated. If str,
        expects that the output is a dict-like object, and obj_getter is the
        key pointing to the dataframe/series to be validated. If a callable is
        supplied, it expects the output of decorated function and should return
        the dataframe/series to be validated.
    :type obj_getter: int|str|callable|None
    :param head: validate the first n rows. Rows overlapping with `tail` or
        `sample` are de-duplicated.
    :type head: int
    :param tail: validate the last n rows. Rows overlapping with `head` or
        `sample` are de-duplicated.
    :type tail: int
    :param sample: validate a random sample of n rows. Rows overlapping
        with `head` or `tail` are de-duplicated.
    """

    @wrapt.decorator
    def _wrapper(fn, instance, args, kwargs):
        if schema.transformer is not None:
            warnings.warn(
                "The schema transformer function has no effect in a "
                "check_output decorator. Please perform the necessary "
                "transformations in the '%s' function instead." % fn.__name__)
        out = fn(*args, **kwargs)
        if obj_getter is None:
            obj = out
        elif isinstance(obj_getter, (int, str)):
            obj = out[obj_getter]
        elif callable(obj_getter):
            obj = obj_getter(out)
        else:
            raise ValueError(
                "obj_getter is unrecognized type: %s" % type(obj_getter))
        try:
            schema.validate(obj, head, tail, sample, random_state)
        except errors.SchemaError as e:
            raise errors.SchemaError(
                "error in check_output decorator of function '%s': %s" %
                (fn.__name__, e))

        return out

    return _wrapper
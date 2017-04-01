import itertools
import logging

l = logging.getLogger('claripy.operations')

def op(name, arg_types, return_type, extra_check=None, calc_length=None, do_coerce=True, bound=True): #pylint:disable=unused-argument
    if type(arg_types) in (tuple, list): #pylint:disable=unidiomatic-typecheck
        expected_num_args = len(arg_types)
    elif type(arg_types) is type: #pylint:disable=unidiomatic-typecheck
        expected_num_args = None
    else:
        raise ClaripyOperationError("op {} got weird arg_types".format(name))

    def _type_fixer(args):
        num_args = len(args)
        if expected_num_args is not None and num_args != expected_num_args:
            raise ClaripyTypeError("Operation {} takes exactly "
                                   "{} arguments ({} given)".format(name, len(arg_types), len(args)))

        if type(arg_types) is type: #pylint:disable=unidiomatic-typecheck
            actual_arg_types = (arg_types,) * num_args
        else:
            actual_arg_types = arg_types
        matches = [ isinstance(arg, argty) for arg,argty in zip(args, actual_arg_types) ]

        # heuristically, this works!
        thing = args[matches.index(True)] if True in matches else None

        for arg, argty, matches in zip(args, actual_arg_types, matches):
            if not matches:
                if do_coerce and hasattr(argty, '_from_' + type(arg).__name__):
                    convert = getattr(argty, '_from_' + type(arg).__name__)
                    yield convert(thing, arg)
                else:
                    yield NotImplemented
                    return
            else:
                yield arg

    def _op(*args):
        fixed_args = tuple(_type_fixer(args))
        for i in fixed_args:
            if i is NotImplemented:
                return NotImplemented

        if extra_check is not None:
            success, msg = extra_check(*fixed_args)
            if not success:
                raise ClaripyOperationError(msg)

        #pylint:disable=too-many-nested-blocks
        kwargs = {}
        if calc_length is not None:
            kwargs['length'] = calc_length(*fixed_args)

        ast_args = [ a for a in args if isinstance(a, ast.Base) ]
        kwargs['filters'] = max(ast_args, key=lambda a:len(a.filters)).filters if ast_args else ()
        kwargs['uninitialized'] = any(a.uninitialized is True for a in ast_args) or None

        if name in preprocessors:
            args, kwargs = preprocessors[name](*args, **kwargs)

        new_ast = return_type(name, fixed_args, **kwargs)
        for f in new_ast.filters:
            try:
                l.debug("Running filter %s.", f)
                new_ast = f(new_ast) if hasattr(f, '__call__') else f.convert(new_ast)
            except BackendError:
                l.warning("Ignoring BackendError during AST filter application.")

        return new_ast


    _op.calc_length = calc_length
    return _op

def reversed_op(op_func):
    def _reversed_op(*args):
        return op_func(*args[::-1])
    return _reversed_op

#
# Extra processors
#

union_counter = itertools.count()
def preprocess_union(*args, **kwargs):

    #
    # When we union two values, we implicitly create a new symbolic, multi-valued
    # variable, because a union is essentially an ITE with an unconstrained
    # "choice" variable.
    #

    new_name = 'union_%d' % next(union_counter)
    kwargs['add_variables'] = frozenset((new_name,))
    return args, kwargs

preprocessors = {
    'union': preprocess_union,
    #'intersection': preprocess_intersect
}

#
# Length checkers
#

def length_same_check(*args):
    return all(a.length == args[0].length for a in args), "args' length must all be equal"

def basic_length_calc(*args):
    return args[0].length

def extract_check(high, low, bv):
    if high < 0 or low < 0:
        return False, "Extract high and low must be nonnegative"
    elif low > high:
        return False, "Extract low must be <= high"
    elif high >= bv.size():
        return False, "Extract bound must be less than BV size"

    return True, ""

def extract_length_calc(high, low, _):
    return high - low + 1

def ext_length_calc(ext, orig):
    return orig.length + ext

def concat_length_calc(*args):
    return sum(arg.size() for arg in args)

#
# Operation lists
#

expression_arithmetic_operations = {
    # arithmetic
    '__add__', '__radd__',
    '__div__', '__rdiv__',
    '__truediv__', '__rtruediv__',
    '__floordiv__', '__rfloordiv__',
    '__mul__', '__rmul__',
    '__sub__', '__rsub__',
    '__pow__', '__rpow__',
    '__mod__', '__rmod__',
    '__divmod__', '__rdivmod__',
    'SDiv', 'SMod',
    '__neg__',
    '__pos__',
    '__abs__',
}

bin_ops = {
    '__add__', '__radd__',
    '__mul__', '__rmul__',
    '__or__', '__ror__',
    '__and__', '__rand__',
    '__xor__', '__rxor__',
}

expression_comparator_operations = {
    # comparisons
    '__eq__',
    '__ne__',
    '__ge__', '__le__',
    '__gt__', '__lt__',
}

# expression_comparator_operations = {
#     'Eq',
#     'Ne',
#     'Ge', 'Le',
#     'Gt', 'Lt',
# }

expression_bitwise_operations = {
    # bitwise
    '__invert__',
    '__or__', '__ror__',
    '__and__', '__rand__',
    '__xor__', '__rxor__',
    '__lshift__', '__rlshift__',
    '__rshift__', '__rrshift__',
}

expression_set_operations = {
    # Set operations
    'union',
    'intersection',
    'widen'
}

expression_operations = expression_arithmetic_operations | expression_comparator_operations | expression_bitwise_operations | expression_set_operations

backend_comparator_operations = {
    'SGE', 'SLE', 'SGT', 'SLT', 'UGE', 'ULE', 'UGT', 'ULT',
}

backend_bitwise_operations = {
    'RotateLeft', 'RotateRight', 'LShR', 'Reverse',
}

backend_boolean_operations = {
    'And', 'Or', 'Not'
}

backend_bitmod_operations = {
    'Concat', 'Extract', 'SignExt', 'ZeroExt'
}

backend_creation_operations = {
    'BoolV', 'BVV', 'FPV'
}

backend_symbol_creation_operations = {
    'BoolS', 'BVS', 'FPS'
}

backend_vsa_creation_operations = {
    'TopStridedInterval', 'StridedInterval', 'ValueSet', 'AbstractLocation'
}

backend_other_operations = { 'If' }

backend_arithmetic_operations = {'SDiv', 'SMod'}

backend_operations = backend_comparator_operations | backend_bitwise_operations | backend_boolean_operations | \
                     backend_bitmod_operations | backend_creation_operations | backend_other_operations | backend_arithmetic_operations
backend_operations_vsa_compliant = backend_bitwise_operations | backend_comparator_operations | backend_boolean_operations | backend_bitmod_operations
backend_operations_all = backend_operations | backend_operations_vsa_compliant | backend_vsa_creation_operations

backend_fp_cmp_operations = {
    'fpLT', 'fpLEQ', 'fpGT', 'fpGEQ', 'fpEQ',
}

backend_fp_operations = {
    'FP', 'fpToFP', 'fpToIEEEBV', 'fpFP', 'fpToSBV', 'fpToUBV',
    'fpNeg', 'fpSub', 'fpAdd', 'fpMul', 'fpDiv', 'fpAbs'
} | backend_fp_cmp_operations

opposites = {
    '__add__': '__radd__', '__radd__': '__add__',
    '__div__': '__rdiv__', '__rdiv__': '__div__',
    '__truediv__': '__rtruediv__', '__rtruediv__': '__truediv__',
    '__floordiv__': '__rfloordiv__', '__rfloordiv__': '__floordiv__',
    '__mul__': '__rmul__', '__rmul__': '__mul__',
    '__sub__': '__rsub__', '__rsub__': '__sub__',
    '__pow__': '__rpow__', '__rpow__': '__pow__',
    '__mod__': '__rmod__', '__rmod__': '__mod__',
    '__divmod__': '__rdivmod__', '__rdivmod__': '__divmod__',

    '__eq__': '__eq__',
    '__ne__': '__ne__',
    '__ge__': '__le__', '__le__': '__ge__',
    '__gt__': '__lt__', '__lt__': '__gt__',
    'ULT': 'UGT', 'UGT': 'ULT',
    'ULE': 'UGE', 'UGE': 'ULE',
    'SLT': 'SGT', 'SGT': 'SLT',
    'SLE': 'SGE', 'SGE': 'SLE',

    #'__neg__':
    #'__pos__':
    #'__abs__':
    #'__invert__':
    '__or__': '__ror__', '__ror__': '__or__',
    '__and__': '__rand__', '__rand__': '__and__',
    '__xor__': '__rxor__', '__rxor__': '__xor__',
    '__lshift__': '__rlshift__', '__rlshift__': '__lshift__',
    '__rshift__': '__rrshift__', '__rrshift__': '__rshift__',
}

reversed_ops = {
    '__radd__': '__add__',
    '__rand__': '__and__',
    '__rdiv__': '__div__',
    '__rdivmod__': '__divmod__',
    '__rfloordiv__': '__floordiv__',
    '__rlshift__': '__lshift__',
    '__rmod__': '__mod__',
    '__rmul__': '__mul__',
    '__ror__': '__or__',
    '__rpow__': '__pow__',
    '__rrshift__': '__rshift__',
    '__rsub__': '__sub__',
    '__rtruediv__': '__truediv__',
    '__rxor__': '__xor__'
}

inverse_operations = {
    '__eq__': '__ne__',
    '__ne__': '__eq__',
    '__gt__': '__le__',
    '__lt__': '__ge__',
    '__ge__': '__lt__',
    '__le__': '__gt__',
    'ULT': 'UGE', 'UGE': 'ULT',
    'UGT': 'ULE', 'ULE': 'UGT',
    'SLT': 'SGE', 'SGE': 'SLT',
    'SLE': 'SGT', 'SGT': 'SLE',
}

length_same_operations = expression_arithmetic_operations | backend_bitwise_operations | expression_bitwise_operations | backend_other_operations | expression_set_operations | {'Reversed'}
length_none_operations = backend_comparator_operations | expression_comparator_operations | backend_boolean_operations | backend_fp_cmp_operations
length_change_operations = backend_bitmod_operations
length_new_operations = backend_creation_operations

leaf_operations = backend_symbol_creation_operations | backend_creation_operations
leaf_operations_concrete = backend_creation_operations
leaf_operations_symbolic = backend_symbol_creation_operations

#
# Reversibility
#

not_invertible = {'Identical', 'union'}
reverse_distributable = { 'widen', 'union', 'intersection',
    '__invert__', '__or__', '__ror__', '__and__', '__rand__', '__xor__', '__rxor__',
}

extract_distributable = {
    '__and__', '__rand__',
    '__or__', '__ror__',
    '__xor__', '__rxor__',
}

infix = {
    '__add__': '+',
    '__sub__': '-',
    '__mul__': '*',
    '__div__': '/',
    '__floordiv__': '/',
#    '__truediv__': 'does this come up?',
    '__pow__': '**',
    '__mod__': '%',
#    '__divmod__': "don't think this is used either",

    '__eq__': '==',
    '__ne__': '!=',
    '__ge__': '>=',
    '__le__': '<=',
    '__gt__': '>',
    '__lt__': '<',

    'UGE': '>=',
    'ULE': '<=',
    'UGT': '>',
    'ULT': '<',

    'SGE': '>=s',
    'SLE': '<=s',
    'SGT': '>s',
    'SLT': '<s',

    'SDiv': "/s",
    'SMod': "%s",

    '__or__': '|',
    '__and__': '&',
    '__xor__': '^',
    '__lshift__': '<<',
    '__rshift__': '>>',

    'And': '&&',
    'Or': '||',

    'Concat': '..',
}

commutative_operations = { '__and__', '__or__', '__xor__', '__add__', '__mul__', 'And', 'Or', 'Xor', }

from .errors import ClaripyOperationError, ClaripyTypeError, BackendError
from . import ast

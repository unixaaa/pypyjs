#!/usr/bin/env python
# -*- coding: utf-8 -*-

from test import test_support
import marshal
import sys
import unittest
import os

class HelperMixin:
    def helper(self, sample, *extra, **kwargs):
        expected = kwargs.get('expected', sample)
        new = marshal.loads(marshal.dumps(sample, *extra))
        self.assertEqual(expected, new)
        self.assertEqual(type(expected), type(new))
        try:
            with open(test_support.TESTFN, "wb") as f:
                marshal.dump(sample, f, *extra)
            with open(test_support.TESTFN, "rb") as f:
                new = marshal.load(f)
            self.assertEqual(expected, new)
            self.assertEqual(type(expected), type(new))
        finally:
            test_support.unlink(test_support.TESTFN)


class IntTestCase(unittest.TestCase, HelperMixin):
    def test_ints(self):
        # Test the full range of Python ints.
        n = sys.maxint
        while n:
            for expected in (-n, n):
                self.helper(expected)
            n = n >> 1

    def test_int64(self):
        # Simulate int marshaling on a 64-bit box.  This is most interesting if
        # we're running the test on a 32-bit box, of course.

        def to_little_endian_string(value, nbytes):
            bytes = []
            for i in range(nbytes):
                bytes.append(chr(value & 0xff))
                value >>= 8
            return ''.join(bytes)

        maxint64 = (1L << 63) - 1
        minint64 = -maxint64-1

        for base in maxint64, minint64, -maxint64, -(minint64 >> 1):
            while base:
                s = 'I' + to_little_endian_string(base, 8)
                got = marshal.loads(s)
                self.assertEqual(base, got)
                if base == -1:  # a fixed-point for shifting right 1
                    base = 0
                else:
                    base >>= 1

    def test_bool(self):
        for b in (True, False):
            self.helper(b)

class FloatTestCase(unittest.TestCase, HelperMixin):
    def test_floats(self):
        # Test a few floats
        small = 1e-25
        n = sys.maxint * 3.7e250
        while n > small:
            for expected in (-n, n):
                self.helper(expected)
            n /= 123.4567

        f = 0.0
        s = marshal.dumps(f, 2)
        got = marshal.loads(s)
        self.assertEqual(f, got)
        # and with version <= 1 (floats marshalled differently then)
        s = marshal.dumps(f, 1)
        got = marshal.loads(s)
        self.assertEqual(f, got)

        n = sys.maxint * 3.7e-250
        while n < small:
            for expected in (-n, n):
                f = float(expected)
                self.helper(f)
                self.helper(f, 1)
            n *= 123.4567

class StringTestCase(unittest.TestCase, HelperMixin):
    def test_unicode(self):
        for s in [u"", u"Andrè Previn", u"abc", u" "*10000]:
            self.helper(s)

    def test_string(self):
        for s in ["", "Andrè Previn", "abc", " "*10000]:
            self.helper(s)

    def test_buffer(self):
        for s in ["", "Andrè Previn", "abc", " "*10000]:
            with test_support.check_py3k_warnings(("buffer.. not supported",
                                                     DeprecationWarning)):
                b = buffer(s)
            self.helper(b, expected=s)

class ExceptionTestCase(unittest.TestCase):
    def test_exceptions(self):
        new = marshal.loads(marshal.dumps(StopIteration))
        self.assertEqual(StopIteration, new)

class CodeTestCase(unittest.TestCase):
    def test_code(self):
        co = ExceptionTestCase.test_exceptions.func_code
        new = marshal.loads(marshal.dumps(co))
        self.assertEqual(co, new)

class ContainerTestCase(unittest.TestCase, HelperMixin):
    d = {'astring': 'foo@bar.baz.spam',
         'afloat': 7283.43,
         'anint': 2**20,
         'ashortlong': 2L,
         'alist': ['.zyx.41'],
         'atuple': ('.zyx.41',)*10,
         'aboolean': False,
         'aunicode': u"Andrè Previn"
         }
    def test_dict(self):
        self.helper(self.d)

    def test_list(self):
        lst = self.d.items()
        self.helper(lst)

    def test_tuple(self):
        t = tuple(self.d.keys())
        self.helper(t)

    def test_sets(self):
        for constructor in (set, frozenset):
            t = constructor(self.d.keys())
            self.helper(t)

class BugsTestCase(unittest.TestCase):
    def test_bug_5888452(self):
        # Simple-minded check for SF 588452: Debug build crashes
        marshal.dumps([128] * 1000)

    def test_patch_873224(self):
        self.assertRaises(Exception, marshal.loads, '0')
        self.assertRaises(Exception, marshal.loads, 'f')
        self.assertRaises(Exception, marshal.loads, marshal.dumps(5L)[:-1])

    def test_version_argument(self):
        # Python 2.4.0 crashes for any call to marshal.dumps(x, y)
        self.assertEqual(marshal.loads(marshal.dumps(5, 0)), 5)
        self.assertEqual(marshal.loads(marshal.dumps(5, 1)), 5)

    def test_fuzz(self):
        # simple test that it's at least not *totally* trivial to
        # crash from bad marshal data
        for c in [chr(i) for i in range(256)]:
            try:
                marshal.loads(c)
            except Exception:
                pass

    def test_loads_recursion(self):
        s = 'c' + ('X' * 4*4) + '{' * 2**20
        self.assertRaises(ValueError, marshal.loads, s)

    @test_support.impl_detail('specific recursion check')
    def test_recursion_limit(self):
        # Create a deeply nested structure.
        head = last = []
        # The max stack depth should match the value in Python/marshal.c.
        MAX_MARSHAL_STACK_DEPTH = 2000
        for i in range(MAX_MARSHAL_STACK_DEPTH - 2):
            last.append([0])
            last = last[-1]

        # Verify we don't blow out the stack with dumps/load.
        data = marshal.dumps(head)
        new_head = marshal.loads(data)
        # Don't use == to compare objects, it can exceed the recursion limit.
        self.assertEqual(len(new_head), len(head))
        self.assertEqual(len(new_head[0]), len(head[0]))
        self.assertEqual(len(new_head[-1]), len(head[-1]))

        last.append([0])
        self.assertRaises(ValueError, marshal.dumps, head)

    def test_exact_type_match(self):
        # Former bug:
        #   >>> class Int(int): pass
        #   >>> type(loads(dumps(Int())))
        #   <type 'int'>
        for typ in (int, long, float, complex, tuple, list, dict, set, frozenset):
            # Note: str and unicode subclasses are not tested because they get handled
            # by marshal's routines for objects supporting the buffer API.
            subtyp = type('subtyp', (typ,), {})
            self.assertRaises(ValueError, marshal.dumps, subtyp())

    # Issue #1792 introduced a change in how marshal increases the size of its
    # internal buffer; this test ensures that the new code is exercised.
    def test_large_marshal(self):
        size = int(1e6)
        testString = 'abc' * size
        marshal.dumps(testString)

    def test_invalid_longs(self):
        # Issue #7019: marshal.loads shouldn't produce unnormalized PyLongs
        invalid_string = 'l\x02\x00\x00\x00\x00\x00\x00\x00'
        self.assertRaises(ValueError, marshal.loads, invalid_string)

LARGE_SIZE = 2**31
character_size = 4 if sys.maxunicode > 0xFFFF else 2
pointer_size = 8 if sys.maxsize > 0xFFFFFFFF else 4

@unittest.skipIf(LARGE_SIZE > sys.maxsize, "test cannot run on 32-bit systems")
class LargeValuesTestCase(unittest.TestCase):
    def check_unmarshallable(self, data):
        f = open(test_support.TESTFN, 'wb')
        self.addCleanup(test_support.unlink, test_support.TESTFN)
        with f:
            self.assertRaises(ValueError, marshal.dump, data, f)

    @test_support.precisionbigmemtest(size=LARGE_SIZE, memuse=1, dry_run=False)
    def test_string(self, size):
        self.check_unmarshallable('x' * size)

    @test_support.precisionbigmemtest(size=LARGE_SIZE,
            memuse=character_size, dry_run=False)
    def test_unicode(self, size):
        self.check_unmarshallable(u'x' * size)

    @test_support.precisionbigmemtest(size=LARGE_SIZE,
            memuse=pointer_size, dry_run=False)
    def test_tuple(self, size):
        self.check_unmarshallable((None,) * size)

    @test_support.precisionbigmemtest(size=LARGE_SIZE,
            memuse=pointer_size, dry_run=False)
    def test_list(self, size):
        self.check_unmarshallable([None] * size)

    @test_support.precisionbigmemtest(size=LARGE_SIZE,
            memuse=pointer_size*12,  # + sys.getsizeof(LARGE_SIZE-1),
            dry_run=False)
    def test_set(self, size):
        self.check_unmarshallable(set(range(size)))

    @test_support.precisionbigmemtest(size=LARGE_SIZE,
            memuse=pointer_size*12,  # + sys.getsizeof(LARGE_SIZE-1),
            dry_run=False)
    def test_frozenset(self, size):
        self.check_unmarshallable(frozenset(range(size)))

    @test_support.precisionbigmemtest(size=LARGE_SIZE, memuse=1, dry_run=False)
    def test_bytearray(self, size):
        self.check_unmarshallable(bytearray(size))


def test_main():
    test_support.run_unittest(IntTestCase,
                              FloatTestCase,
                              StringTestCase,
                              CodeTestCase,
                              ContainerTestCase,
                              ExceptionTestCase,
                              BugsTestCase,
                              LargeValuesTestCase,
                             )

if __name__ == "__main__":
    test_main()

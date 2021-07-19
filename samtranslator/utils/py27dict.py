import ctypes
import copy
import json
import sys
import logging


from py27hash.dict import Dict
from py27hash.key import Keys
from py27hash.hash import Hash
from six import string_types


LOG = logging.getLogger(__name__)


class Py27UniStr(str):
    """
    A str subclass to allow string be recognized as Py27 unicode string by Py27Dict
    """
    def __add__(self, other):
        return Py27UniStr(super(Py27UniStr, self).__add__(other))

    def __repr__(self):
        if sys.version_info.major >= 3:
            return super(Py27UniStr, self).__repr__()
        return "u" + super(Py27UniStr, self).__repr__() + ""

    def upper(self):
        return Py27UniStr(super(Py27UniStr, self).upper())

    def lower(self):
        return Py27UniStr(super(Py27UniStr, self).lower())

class Py27Keys(object):
    """
    A subclass of Keys from py27hash
    Difference from Keys - In Keys, hashes are only calculated and cached when keys() method is
    invoked. This is fine if the dictionary is not manipulated at all between creation and keys()
    is invoked for the first time. However, in Swagger Editor, the swagger body is manipulated
    (adding/removing keys & values) without calling keys(). 
    Therefore, when adding
    The main change is to keep a cache of calculated hash id for existing keys
    """
    def __init__(self):
        super(Py27Keys, self).__init__()
        self.debug = True
        self.keyorder = dict()
        # current size of the keys
        self.size = 0
        # Python 2 dict default size
        self.mask = Keys.MINSIZE - 1
        self.printstate('__init__')

    def printstate(self, k):
        if not self.debug:
            return
        print('py27k {k} => mask {mask} size {size} keyorder {keyorder}'.format(
            k=k,
            mask=self.mask,
            size=self.size,
            keyorder=self.keyorder
        ))

    # get insert location for k
    def _get_key_idx(self, k):
        # C API uses unsigned values
        h = ctypes.c_size_t(Hash.hash(k)).value
        i = h & self.mask

        walker = i
        perturb = h
        while i in self.keyorder and self.keyorder[i] != k:
            walker = (walker << 2) + walker + perturb + 1
            i = walker & self.mask
            perturb >>= Keys.PERTURB_SHIFT
            # todo some sort of check for infinite loop
        return i

    def _setMask(self, request=None):
        """
        Key based on the total size of this dict. Matches ma_mask in Python 2.7's dict.
        Method: static int dictresize(PyDictObject *mp, Py_ssize_t minused)
        """

        if not request:
            # Python 2 dict increases by a factor of 4 for small dicts, 2 for larger ones
            request = self.size * (2 if self.size > 50000 else 4)

        newsize = Keys.MINSIZE
        while newsize <= request:
            newsize <<= 1

        self.mask = newsize - 1        

    def remove(self, key):
        i = self._get_key_idx(key)
        if i in self.keyorder:
            del self.keyorder[i]
            self.size -= 1
        self.printstate('remove({key})'.format(key=key))

    def add(self, key):
        i = self._get_key_idx(key)
        if i not in self.keyorder:
            self.keyorder[i] = key
            self.size += 1

        # Resize dict if 2/3 capacity
        # todo before or after we insert into keyorder???
        if self.size * 3 >= ((self.mask + 1) * 2):
            self.printstate('upsize')
            # Reset key list to simulate the dict resize + copy operation
            oldkeyorder = copy.copy(self.keyorder)
            self._setMask()
            self.keyorder = dict()
            # now reinsert all the keys using the original order
            for idx in sorted(oldkeyorder.keys()):
                # todo recursion danger, we're counting on mask being big enough to not get into this if again
                self.add(oldkeyorder[idx]) 

        self.printstate('add({key})'.format(key=key))

    def keys(self):
        self.printstate('keys()')
        return [self.keyorder[key] for key in sorted(self.keyorder.keys())]
    
    def __setstate__(self, state):
        """
        Overrides default pickling object to force re-adding all keys and match Python 2.7 deserialization logic.
        Args:
            state: input state
        """

        self.__dict__ = state
        keys = self.keys()

        # Clear keys and re-add to match deserialization logic
        self.__init__()

        for k in keys:
            self.add(k)

    def __iter__(self):
        """
        Default iterator.
        Returns:
            iterator
        """

        return iter(self.keys())

    def merge(self, d):
        """
        Merges keys from an existing iterable into this key list.
        Method: int PyDict_Merge(PyObject *a, PyObject *b, int override)
        Args:
            d: input dict
        """

        # PyDict_Merge initial merge size is double the size of the current + incoming dict
        if ((self.size + len(d)) * 3) >= ((self.mask + 1) * 2):
            self._setMask((self.size + len(d)) * 2)

        # Copy actual keys
        for k in d:
            self.add(k)

        self.printstate('merge')

    def copy(self):
        """
        Makes a copy of self.
        Method: PyObject *PyDict_Copy(PyObject *o)
        Returns:
            copy of self
        """

        # Copy creates a new object and merges keys in
        new = Py27Keys()
        new.merge(self.keys())
        new.printstate('copy')
        return new

    def pop(self):
        """
        Pops the top element from the sorted keys if it exists. Returns None otherwise.
        Method: static PyObject *dict_popitem(PyDictObject *mp)
        Return:
            top element or None if Keys is empty
        """

        if self.keylist:
            # Pop the top element
            value = self.keys()[0]
            self.remove(value)
            return value

        return None

class Py27Dict(dict):
    """
    Compatibility class to support Python 2.7 style iteration in Python 3.X+
    """

    def __init__(self, *args, **kwargs):
        """
        Overrides dict logic to always call set item. This allows Python 2.7 style iteration.

        Args:
            *args: args
            *kwargs: keyword args
        """

        super(Py27Dict, self).__init__()

        # Initialize iteration key list
        self.keylist = Py27Keys()

        # Initialize base arguments
        self.update(*args, **kwargs)

    def __reduce__(self):
        """
        Method necessary to fully pickle Python 3 subclassed dict objects with attribute fields.
        """

        # pylint: disable = W0235
        return super(Py27Dict, self).__reduce__()

    def __setitem__(self, key, value):
        """
        Override of __setitem__ to track keys and simulate Python 2.7 dict.

        Args:
            key: key
            value: value
        """

        super(Py27Dict, self).__setitem__(key, value)

        self.keylist.add(key)

    def __delitem__(self, key):
        """
        Override of __delitem__ to track keys and simulate Python 2.7 dict.

        Args:
            key: key
        """

        super(Py27Dict, self).__delitem__(key)

        self.keylist.remove(key)

    def update(self, *args, **kwargs):
        """
        Overrides dict logic to always call set item. This allows Python 2.7 style iteration.

        Args:
            *args: args
            *kwargs: keyword args
        """
        print(self.keys())
        print(self.keylist.keyorder)

        for arg in args:
            # Cast to dict if applicable. Otherwise, assume it's an iterable of (key, value) pairs.
            if isinstance(arg, dict):
                # Merge incoming keys into keylist
                self.keylist.merge(arg.keys())
                print(self.keylist.keyorder)

                arg = arg.items()

            for k, v in arg:
                self[k] = v

        for k, v in dict(**kwargs).items():
            self[k] = v

    def clear(self):
        """
        Clears the dict along with it's backing Python 2.7 keylist.
        """

        super(Py27Dict, self).clear()

        self.keylist = Keys()

    def copy(self):
        """
        Copies the dict along with it's backing Python 2.7 keylist.

        Returns:
            copy of self
        """

        new = Py27Dict()

        # First copy the keylist to the new object
        new.keylist = self.keylist.copy()

        # Copy keys into backing dict
        for (k, v) in self.items():
            new[k] = v

        return new

    def pop(self, key, default=None):
        """
        Pops the value at key from the dict if it exists, returns default otherwise.

        Args:
            key: key to remove
            default: value to return if key is not found

        Returns:
            value of key if found or default
        """

        value = super(Py27Dict, self).pop(key, default)
        self.keylist.remove(key)

        return value

    def popitem(self):
        """
        Pops an element from the dict and returns the item.

        Returns:
            (key, value) of an element if found or None if dict is empty
        """

        if self:
            key = self.keylist.pop()
            value = self[key] if key else None

            del self[key]

            return (key, value)

        return None

    def __iter__(self):
        """
        Default iterator.

        Returns:
            iterator
        """

        return self.keylist.__iter__()

    def __str__(self):
        """
        Override to minic exact py27 str(dict_obj)
        """
        string = "{"

        for x, k in enumerate(self):
            string += ", " if x > 0 else ""
            if isinstance(k, Py27UniStr):
                string += "u"
            string += "'%s': " % k

            if isinstance(self[k], string_types):
                if isinstance(self[k], Py27UniStr):
                    string += "u"
                string += "'%s'" % self[k]
            else:
                string += "%s" % self[k]

        string += "}"

        return string


    def __repr__(self):
        """
        Creates a string version of this Dict.

        Returns:
            string
        """

        return self.__str__()

    def keys(self):
        """
        Returns keys ordered using Python 2.7's iteration algorithm.

        Returns:
          list of keys
        """

        return self.keylist.keys()

    def values(self):
        """
        Returns values ordered using Python 2.7's iteration algorithm.

        Returns:
          list of values
        """

        return [self[k] for k in self.keys()]

    def items(self):
        """
        Returns items ordered using Python 2.7's iteration algorithm.

        Returns:
          list of items
        """

        return [(k, self[k]) for k in self.keys()]

    # Backwards compat methods removed in Python 3.X
    def has_key(self, key):
        """
        Backwards compat method for Python 2 dict's

        Args:
            key: key to lookup

        Returns:
            True if key exists, False otherwise
        """

        return key in self

    def viewkeys(self):
        """
        Backwards compat method for Python 2 dict

        Returns:
            keys
        """

        return self.keys()

    def viewvalues(self):
        """
        Backwards compat method for Python 2 dict

        Returns:
            values
        """

        return self.values()

    def viewitems(self):
        """
        Backwards compat method for Python 2 dict

        Returns:
            items
        """

        return self.items()

    def iterkeys(self):
        """
        Backwards compat method for Python 2 dict

        Returns:
            iter(keys)
        """

        return iter(self.keys())

    def itervalues(self):
        """
        Backwards compat method for Python 2 dict

        Returns:
            iter(values)
        """

        return iter(self.values())

    def iteritems(self):
        """
        Backwards compat method for Python 2 dict

        Returns:
            iter(items)
        """

        return iter(self.items())

    def setdefault(self, __key, __default):
        if __key not in self:
            self[__key] = __default
        return self[__key]


def to_py27dict(original_dict):
    # print("original: %s" % original_dict)
    if isinstance(original_dict, dict):
        py27_dict = copy.deepcopy(original_dict)
        if not isinstance(original_dict, Py27Dict):
            py27_dict = Py27Dict(**py27_dict)
        # else:
        #     py27_dict = original_dict
        # py27_dict = Py27Dict(**original_dict)
        for k in py27_dict.keys():
            py27_dict[k] = to_py27dict(py27_dict[k])
        return py27_dict
    elif isinstance(original_dict, list):
        return [to_py27dict(item) for item in original_dict]
    else:
        return original_dict


def _object_pairs_hook(pairs):
    original_dict = {
        Py27UniStr(k): Py27UniStr(v) if isinstance(v, string_types) else v
        for k, v in pairs
    }
    return dict(**original_dict)

def mark_unicode_str_in_template(template_dict):
    """
    In Python2, 
    """
    return json.loads(json.dumps(template_dict), object_pairs_hook=_object_pairs_hook)

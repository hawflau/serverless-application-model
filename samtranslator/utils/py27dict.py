import ctypes
import copy
import logging


from py27hash.dict import Dict
from py27hash.key import Keys
from py27hash.hash import Hash
from six import string_types


LOG = logging.getLogger(__name__)


class Py27Str(str):
    """
    A str subclass to 
    """
    def __add__(self, other):
        if isinstance(other, Py27Str):
            return Py27Str(super(Py27Str, self).__add__(other)) 
        return super(Py27Str, self).__add__(other)

    def __mul__(self, n):
        return Py27Str(super(Py27Str, self).__mul__(n))

    def format(self, *args, **kwargs):
        """
        """
        return Py27Str(super(Py27Str, self).format(*args, **kwargs))

    def join(self, iterable):
        joined = super(Py27Str, self).join(iterable)
        if all(isinstance(item, Py27Str) for item in iterable):
            return Py27Str(joined)
        return joined

    def upper(self):
        return Py27Str(super(Py27Str, self).upper())


class Py27Keys(Keys):
    """
    A subclass of Keys from py27hash
    The main change is to keep a cache of calculated hash id for existing keys
    """
    def __init__(self):
        super(Py27Keys, self).__init__()
        self.keyhash = dict()

    def remove(self, key):
        """
        Override original to not reset cache
        """
        if key in self.keylist:
            # Remove key from list
            self.keylist.remove(key)
            del self.keyhash[key]
            # Clear cached keys
            self.keysort = None

    def keys(self):
        if not self.keysort:
            keys = []
            hids = set(self.keyhash.values())

            for k in self.keylist:
                if k in self.keyhash:
                    hid = self.keyhash[k]
                else:
                    # C API uses unsigned values
                    h = ctypes.c_size_t(Hash.hash(k)).value
                    i = h & self.mask

                    hid = i
                    perturb = h

                    while hid in hids:
                        i = (i << 2) + i + perturb + 1
                        hid = i & self.mask
                        perturb >>= Keys.PERTURB_SHIFT

                self.keyhash[k] = hid
                keys.append((hid, k))
                hids.add(hid)

            # Cache result - performance - clear if more keys added
            self.keysort = [v for (k, v) in sorted(keys, key=lambda x: x[0])]

        return self.keysort

    

class Py27Dict(Dict):
    def __init__(self, *args, **kwargs):
        """
        Override to use custom Py27Keys
        """
        super(Py27Dict, self).__init__()
        self.keylist = Py27Keys()
        self.update(*args, **kwargs)

    def __str__(self):
        """
        Override to minic exact py27 str(dict_obj)
        """
        string = "{"

        for x, k in enumerate(self):
            string += ", " if x > 0 else ""
            if not isinstance(k, Py27Str):
                string += "u"
            string += "'%s': " % k

            if isinstance(self[k], string_types):
                if not isinstance(self[k], Py27Str):
                    string += "u"
                string += "'%s'" % self[k]
            else:
                string += "%s" % self[k]

        string += "}"

        return string

def to_py27dict(original_dict):
    if isinstance(original_dict, dict):
        py27_dict = Py27Dict(copy.deepcopy(original_dict))
        for k in py27_dict.keys():
            py27_dict[k] = to_py27dict(py27_dict[k])
        return py27_dict
    elif isinstance(original_dict, list):
        return [to_py27dict(item) for item in original_dict]
    else:
        return original_dict

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

class Py27Keys(Keys):
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
        self.keyhash = dict()

    def remove(self, key):
        """
        Override original to not reset cache
        """
        if key in self.keylist:
            # Remove key from list
            self.keylist.remove(key)
            if key in self.keyhash:
                del self.keyhash[key]
            # Clear cached keys
            self.keysort = None

    def add(self, key):
        """
        Calculate hash of the new key every
        """
        if key and key not in self.keylist:
            # Append key to list
            self.keylist.append(key)

            # Update keysort
            self._update_keysort()

            # Resize dict if 2/3 capacity
            if len(self.keylist) * 3 >= ((self.mask + 1) * 2):
                # Reset key list to simulate the dict resize + copy operation
                self.keylist = self.keys()
                self.keysort = None

                self.setMask()

    def keys(self):
        if not self.keysort:
            self._update_keysort()
        return self.keysort

    def _update_keysort(self):
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

    def setdefault(self, __key, __default):
        if __key not in self:
            self[__key] = __default
        return self[__key]


def to_py27dict(original_dict):
    if isinstance(original_dict, dict):
        py27_dict = Py27Dict(copy.deepcopy(original_dict))
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
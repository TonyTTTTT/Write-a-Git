import collections
import configparser
import os
from utils import *

class GitRepository(object):
    """A git repository."""

    worktree = None
    gitdir = None
    conf = None

    def __init__(self, path, force=False) -> None:
        self.worktree = path
        self.gitdir = os.path.join(path, ".git")

        if not (force or os.path.isdir(self.gitdir)):
            raise Exception("Not a Git repository %s" % path)
        
        # Read configuration file in .git/config
        self.conf = configparser.ConfigParser()
        cf = repo_file(self, "config")

        if cf and os.path.exists(cf):
            self.conf.read([cf])
        elif not force:
            raise Exception("Configuration file missing")
        
        if not force:
            vers = int(self.conf.get("core", "repositoryformatversion"))
            if vers != 0:
                raise Exception("Unsupported repositoryformatversion %s" % vers)
    
    @staticmethod
    def repo_default_config():
        ret = configparser.ConfigParser()

        ret.add_section("core")
        ret.set("core", "repositoryformatversion", "0")
        ret.set("core", "filemode", "false")
        ret.set("core", "bare", "false")

        return ret

    @staticmethod
    def repo_create(path):
        """Create a new repository at path."""

        repo = GitRepository(path, True)

        # First, we make sure the path either doesn't exist or is an empty dir.
        if os.path.exists(repo.worktree):
            if not os.path.isdir(repo.worktree):
                raise Exception("%s is not a directory!" % path)
            if os.path.exists(repo.gitdir) and os.listdir(repo.gitdir):
                raise Exception("%s is not empty!" % path)
        else:
            os.makedirs(repo.worktree)

        assert repo_dir(repo, "branches", mkdir=True)
        assert repo_dir(repo, "objects", mkdir=True)
        assert repo_dir(repo, "refs", "tags", mkdir=True)
        assert repo_dir(repo, "refs", "heads", mkdir=True)

        # .git/description
        with open(repo_file(repo, "description"), "w") as f:
            f.write("Unnamed repository; edit this file 'description' to name the repository.\n")

        # .git/HEAD
        with open(repo_file(repo, "HEAD"), "w") as f:
            f.write("ref: refs/heads/master\n")
        
        with open(repo_file(repo, "config"), "w") as f:
            config = GitRepository.repo_default_config()
            config.write(f)

        return repo


class GitObject(object):
    def __init__(self, data=None) -> None:
        if data != None:
            self.deserialize(data)
        else:
            self.init()
        
    def serialize(self, repo):
        """
        This function MUST be implemented by subclasses. It must read the object's
        contents from self.data, a byte string, and do whatever it takes to convert
        it into a meaningful representation. What exactly that means depend on each
        subclass.
        """
        raise Exception("Unimplemented serialize()!")
    
    def deserialize(self, data):
        raise Exception("Unimplemented deserialize()!")
    
    def init(self):
        pass


class GitBlob(GitObject):
    fmt = b'blob'

    def serialize(self):
        return self.blobdata
    
    def deserialize(self, data):
        self.blobdata = data


class GitCommit(GitObject):
    fmt = b"commit"

    def deserialize(self, data):
        self.kvlm = self.kvlm_parse(data)

    def serialize(self):
        return self.kvlm_serialize(self.kvlm)

    def init(self):
        self.kvlm = dict()

    def kvlm_serialize(self, kvlm):
        ret = b''

        # Output fields
        for k in kvlm.keys():
            # Skip the message itself
            if k == None: continue
            val = kvlm[k]

            # Normalize to a list
            if type(val) != list:
                val = [val]

            for v in val:
                ret += k + b' ' + (v.replace(b'\n', b'\n')) + b'\n'

        # Append message
        ret += b'\n' + kvlm[None] + b'\n'

        return ret

    def kvlm_parse(self, raw, start=0, dct=None):
        if not dct:
            dct = collections.OrderedDict()
            # You CANNOT declare the argument as dect = OrderedDict() or all call to the functions will endlessly grow the same dict
        
        # This function is recursive: it reads a key/value pair, then call itself back with the new position.
        # So we first need to know where we are: at a keyword, or already in the messageQ

        # We search for the next space and the next newline.
        spc = raw.find(b' ', start)
        nl = raw.find(b'\n', start)

        # If space apprears before neline, we have a keyword. Otherwise, it's the final message, which we just read to the end of the file.

        # Base case
        # ==========
        # If newline appears first (or there's no space at all, in which case find returns -1), we assume a bliank line.
        # A blank line means the remainder of the data is the message. We store it in the dictionary, with Non as the key, and return.
        if (spc < 0) or (nl < spc):
            assert nl == start
            dct[None] = raw[start+1:]

            return dct


        # Recursive case
        # ==============
        # we read a key-value pair and recurse fo the next.
        key = raw[start:spc]

        # Find the end of the value. Continuation lines begin with a space, so we loop until we find a '\n' not followed by a space
        end = start
        while True:
            end = raw.find(b'\n', end+1)
            if raw[end+1] != ord(' '): break

        # Grab the value, also, drop the leading space on continuation lines
        value = raw[spc+1:end].replace(b'\n', b'\n')

        # Don't overwrite existing data contents
        if key in dct:
            if type(dct[key]) == list:
                dct[key].sppend(value)
            else:
                dct[key] = [dct[key], value]
        else:
            dct[key] = value

        return self.kvlm_parse(raw, start=end+1, dct=dct)


class GitTreeLeaf(object):
    def __init__(self, mode, path, sha):
        self.mode = mode
        self.path = path
        self.sha = sha


class GitTree(GitObject):
    fmt = b"tree"

    def deserialize(self, data):
        self.items = self.tree_parse(data)

    def serialize(self):
        return self.tree_serialize(self)
    
    def init(self):
        self.items = list()

    def tree_parse(self, raw):
        pos = 0
        max = len(raw)
        ret = list()

        while pos < max:
            pos, data = self.tree_parse_one(raw, pos)
            ret.append(data)
        
        return ret
    
    def tree_parse_one(self, raw, start=0):
        # Find the space terminator of the mode

        x = raw.find(b' ', start)
        assert x - start == 5 or x - start == 6

        # Read the mode
        mode = raw[start: x]
        if len(mode) == 5:
            # Normalize to six bytes
            mode = b" " + mode

        # Find the NULL terminator of the path
        y = raw.find(b'\x00', x)
        # and read the path
        path = raw[x+1: y]
        
        # Read the SHA and convert to a hex string
        sha = format(int.from_bytes(raw[y+1: y+21], "big"), "040x")
        
        return y+21, GitTreeLeaf(mode, path.decode("utf8"), sha)
    
    def tree_serialize(self, obj):
        obj.items.sort(key=self.tree_leaf_sort_key)
        ret = b''

        for i in obj.items:
            ret += i.mode
            ret += b' '
            ret += i.path.encode("utf8")
            ret += b"\x00"
            sha = int(i.sha, 16)
            ret += sha.to_bytes(20, byteorder="big")

        return ret
    
    # Notice this isn't a coparison function, but a conversion function.
    # Python's default sort doesn't accept a custom comparison function like in most languages,
    # but a 'key arguments that returns a new value, which is compared using the default rules.
    # So we just return the leaf name, with an extra / if it's a directory.
    def tree_leaf_sort_key(self, leaf):
        if leaf.mode.startswith(b"10"):
            return leaf.path
        else:
            return leaf.path + "/"
        

class GitTag(GitCommit):
    fmt = b"tag"


class GitIgnore(object):
    absolute = None
    scoped = None
    
    def __init__(self, absolute, scoped):
        self.absolute = absolute
        self.scoped = scoped


class GitIndexEntry(object):
    def __init__(self, ctime=None, mtime=None, dev=None, ino=None,
                 mode_type=None, mode_perms=None, uid=None, gid=None,
                 fsize=None, sha=None, flag_assume_valid=None, flag_stage=None, name=None):
        # The Last time a file's metadata changed. This is a pair
        # (timestamp in seconds, nanoseconds)
        self.ctime = ctime

        # The last time a file's data changed. This is a pair
        # (timestamp in seconds, nanoseconds)
        self.mtime = mtime

        # The ID of device containing this file
        self.dev = dev

        # The file's inode number
        self.ino = ino

        # The object type, either b1000(regular), b1010(symlink), b1110(gitlink)
        self.mode_type = mode_type

        # The object permissions, an integer.
        self.mode_perms = mode_perms

        # User Id of owner
        self.uid = uid

        # Group ID of owner
        self.gid = gid

        # Size of this object, in bytes
        self.fsize = fsize

        # The object's SHA
        self.sha = sha

        self.flag_assume_valid = flag_assume_valid
        self.flag_stage = flag_stage

        # Name of the object (full path this time!)
        self.name = name


class GitIndex(object):
    version = None
    entries = [GitIndexEntry]
    # ext = None
    # sha = None

    def __init__(self, version=2, entries=None):
        if not entries:
            entries = list()

        self.version = version
        self.entries = entries
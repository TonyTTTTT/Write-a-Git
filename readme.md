- This is a project which follow the tutorial in [https://wyag.thb.lt/](https://wyag.thb.lt/) which built a simple version of Git.

## Features not present
- object find function
    - HEAD~~
- detect rename in ./wyag status
- if there's no commit(after init), some cmd(status, log, etc.) will occur error

## Issue
- can't use startswith() in ignore compare
- same sha may occur when tree_from_index() -> object_write()
- After commit
    - the HEAD file will be empty (solved)
        - in cmd_commit() fd.write() shoud contain commit on the last line
    - status will print some wrong info. at Changes to be committed:
        - should use "04" instead of " 4" when refer to tree mode
- the mode refer to tree still have to be both ' 4' and '04' in tree_to_dict() in order status cmd to function correctly with the commit fire by git and wyag respectively
- error when push to github
    - remote: fatal: fsck error in packed object
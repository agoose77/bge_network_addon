from _mainloop import *

from bge import logic

import sys
import re


if __name__ == "__main__":
    main()

else:
    class Interface:

        def __init__(self):
            self.get_arguments = re.compile('\((.*)\)\Z')
            self.get_function_name = re.compile('.*?(?=\()')

        def __getattr__(self, name):
            match = re.search(self.get_function_name, name)

            if match is None:
                if name == "__all__":
                    return [k for k in globals().keys() if not k.startswith("_")]

                try:
                    return globals()[name]

                except KeyError:
                    raise AttributeError(name)

            function_name = match.group(0)
            if function_name not in globals():
                raise AttributeError(function_name)

            argument_match = re.search(self.get_arguments, name)
            if argument_match is None:
                arguments = ""

            else:
                arguments = argument_match.group(1)

            data = globals().copy()
            data["cont"] = logic.getCurrentController()

            return lambda: exec("{}(cont, {})".format(function_name, arguments), data)


    sys.modules[__name__] = Interface()

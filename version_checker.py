# Check module is up to date
from contextlib import contextmanager
from queue import Queue
from threading import Thread
from json import loads
from urllib.request import urlopen
from urllib.parse import urlencode

from os import path


def version_to_tuple(string):
    return tuple([int(c) for c in string.split(".")])


class SafeQueue(Queue):

    @contextmanager
    def get(self, block=False, timeout=None):
        try:
            yield super().get(block, timeout)

        finally:
            self.task_done()


class RemoteVersionChecker(Thread):

    def __init__(self):
        super().__init__()

        self._requests = SafeQueue()
        self._results = SafeQueue()

    @property
    def results(self):
        results = self._results
        while not results.empty():
            with results.get() as result:
                yield result

    def check_version(self, url, local_version):
        self._requests.put_nowait((url, local_version))

    def run(self):
        while True:
            with self._requests.get(block=True) as (address, local_version):
                data = {'version': local_version}

                modified_address = "{}?{}".format(address, urlencode(data))
                result_ = urlopen(modified_address)
                result = loads(result_.read().decode())

                self._results.put(result, block=True)

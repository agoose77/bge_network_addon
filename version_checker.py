# Check module is up to date
from contextlib import contextmanager
from queue import Queue
from threading import Thread
from urllib.request import urlopen

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

    def check_version(self, name, remote_path, local_path, filename):
        remote_filepath = path.join(remote_path, filename)
        local_filepath = path.join(local_path, filename)
        
        with open(local_filepath, "r") as local_file:
            local_version = version_to_tuple(local_file.read())
            
        self._requests.put_nowait((name, remote_filepath, local_version))

    def run(self):
        while True:
            with self._requests.get(block=True) as (name, address, local_version):
                data = urlopen(address)
                remote_version = version_to_tuple(data.read().decode())

                result = (name, remote_version <= local_version)
                self._results.put(result, block=True)
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
        
        self.queue = SafeQueue()

    def check_version(self, remote_path, local_path, filename):
        remote_filepath = path.join(remote_path, filename)
        local_filepath = path.join(local_path, filename)
        
        with open(local_filepath, "r") as local_file:
            local_version = version_to_tuple(local_file.read())
            
        self.queue.put_nowait((remote_filepath, local_version))

    def run(self):
        while True:
            with self.queue.get(block=True) as (address, local_version):
                print("Checking remote version file at {} to compare with local version {}".format(address, local_version))
                data = urlopen(address)
                remote_version = version_to_tuple(data.read().decode())

                if remote_version != local_version:
                    print("Error: Remote and local versions do not match!")

                else:
                    print("Success: Remote and local versions match!")


def check_all_dependencies():
    version_checker = RemoteVersionChecker()
    
    remote_path = "https://raw.githubusercontent.com/agoose77/PyAuthServer/master/network/"
    local_path = __import__("network").__path__[0]
    version_checker.check_version(remote_path, local_path, "version.txt")

    remote_path = "https://raw.githubusercontent.com/agoose77/bge_network_addon/master/"
    local_path = path.dirname(__file__)
    version_checker.check_version(remote_path, local_path, "version.txt")
        
    version_checker.start()
from diskcache_community import Cache, SafeDisk  # type: ignore


class ServerGroupCache(object):
    """
    Cache server group ids by project id and server group name

    It uses diskcache to cache the server group ids. We can replace it with dogpile or whatever
    if we need.
    """

    def __init__(self, ttl: int = 300):
        self._cache = Cache(disk=SafeDisk.with_options(on_error="miss"))
        self._ttl = ttl

    def get(self, project_id, server_group_name):
        return self._cache.get((project_id, server_group_name))

    def set(self, project_id, server_group_name, server_group_id):
        self._cache.set((project_id, server_group_name), server_group_id, self._ttl)

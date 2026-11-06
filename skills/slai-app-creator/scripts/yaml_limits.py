"""Shared byte and complexity limits for manifest parsing workers."""
import os
import stat

MAX_INPUT_BYTES = 4 * 1024 * 1024
MAX_OUTPUT_BYTES = 8 * 1024 * 1024
MAX_DOCUMENTS = 32
MAX_DEPTH = 40
MAX_NODES = 50000
MEMORY_BYTES = 256 * 1024 * 1024
MAX_BASELINE_BYTES = 4 * 1024 * 1024 * 1024
CPU_SECONDS = 5
WALL_SECONDS = 10


class YamlLimitError(ValueError):
    pass


def apply_resource_limits():
    try:
        import resource
    except ImportError:
        # Windows retains byte/node limits and the parent's hard wall timeout.
        return
    # Distribution libraries may reserve more than 256 MiB before this worker
    # starts parsing. Bound additional address space rather than placing the
    # limit below existing mappings, which makes even normal imports fail.
    baseline = 0
    if os.path.isfile('/proc/self/statm'):
        with open('/proc/self/statm', 'r') as source:
            pages = int(source.read(128).split()[0])
        baseline = pages * os.sysconf('SC_PAGE_SIZE')
        if baseline < 0 or baseline > MAX_BASELINE_BYTES:
            raise YamlLimitError('worker baseline address space exceeds supported limit')
    limit = baseline + MEMORY_BYTES
    _, inherited_hard = resource.getrlimit(resource.RLIMIT_AS)
    if inherited_hard != resource.RLIM_INFINITY:
        limit = min(limit, inherited_hard)
    resource.setrlimit(resource.RLIMIT_AS, (limit, limit))
    resource.setrlimit(resource.RLIMIT_CPU, (CPU_SECONDS, CPU_SECONDS))


def read_file_bytes(path):
    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_NONBLOCK', 0)
    fd = os.open(path, flags)
    with os.fdopen(fd, 'rb') as source:
        info = os.fstat(source.fileno())
        if not stat.S_ISREG(info.st_mode):
            raise YamlLimitError('manifest must be a regular file')
        if info.st_size > MAX_INPUT_BYTES:
            raise YamlLimitError('manifest exceeds file-size limit')
        data = source.read(MAX_INPUT_BYTES + 1)
    if len(data) > MAX_INPUT_BYTES:
        raise YamlLimitError('manifest exceeds file-size limit')
    return data


def bounded_loader(data):
    import yaml

    class BoundedLoader(yaml.SafeLoader):
        def __init__(self, stream):
            self.depth = 0
            self.nodes = 0
            super().__init__(stream)

        def construct_mapping(self, node, deep=False):
            if not isinstance(node, yaml.MappingNode):
                return super().construct_mapping(node, deep=deep)
            self.flatten_mapping(node)
            mapping = {}
            for key_node, value_node in node.value:
                key = self.construct_object(key_node, deep=deep)
                if not isinstance(key, str):
                    raise YamlLimitError("YAML mapping keys must be strings")
                try:
                    if key in mapping:
                        raise YamlLimitError('duplicate YAML mapping keys are not accepted')
                    mapping[key] = self.construct_object(value_node, deep=deep)
                except TypeError:
                    raise YamlLimitError('YAML mapping keys must be hashable') from None
            # PyYAML 3.x delegates to collections.Hashable, removed in Python
            # 3.10. String keys above are already hashable; build the bounded
            # mapping directly rather than invoking that obsolete constructor.
            return mapping

        def compose_node(self, parent, index):
            if self.check_event(yaml.AliasEvent):
                raise YamlLimitError('YAML aliases are not accepted')
            self.depth += 1
            self.nodes += 1
            try:
                if self.depth > MAX_DEPTH or self.nodes > MAX_NODES:
                    raise YamlLimitError('YAML complexity exceeded')
                return super().compose_node(parent, index)
            finally:
                self.depth -= 1

    return BoundedLoader(data)
